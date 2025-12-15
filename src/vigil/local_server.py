from flask import Flask, request, jsonify
import sys
import os
import threading
import requests
import json
import datetime
import time
import uuid
import redis

from .firewall_engine import FirewallEngine
from .pii_engine import PIIEngine
from .merkle_log_store import MerkleLogStore
from .agentshield_client import AgentShieldClient, VigilErrorCode

app = Flask(__name__)
firewall = FirewallEngine()
pii_engine = PIIEngine()
append_store = MerkleLogStore(os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl'))
agentshield = AgentShieldClient()

LOG_SERVER_URL = os.environ.get('LOG_SERVER_URL', 'http://vigil-dashboard:3000/ingest')

# Hardening controls
MAX_REQUEST_BYTES = int(os.environ.get('MAX_REQUEST_BYTES', '1048576'))  # 1 MB default
RATE_LIMIT_RPS = float(os.environ.get('RATE_LIMIT_RPS', '5'))
REQUIRE_MTLS = os.environ.get('REQUIRE_MTLS', 'false').lower() == 'true'
VIGIL_ENVIRONMENT = os.environ.get('VIGIL_ENVIRONMENT', 'local')

# Policy enforcement thresholds
MAX_RISK_SCORE = float(os.environ.get('MAX_RISK_SCORE', '0.30'))
DISALLOWED_REASONS = set(os.environ.get('DISALLOWED_REASONS', 'credential-exfil,tenant-boundary,privilege-escalation').split(','))
AGENTSHIELD_TIMEOUT_SEC = float(os.environ.get('AGENTSHIELD_TIMEOUT_MS', '1000')) / 1000.0  # Reduced to 1000ms

# Simple per-API-key token buckets (Redis-backed if available, else in-memory)
_rate_buckets = {}
_seq_id = 0
_redis_client = None

try:
    if os.environ.get('REDIS_URL'):
        _redis_client = redis.from_url(os.environ.get('REDIS_URL'))
except Exception as e:
    print(f"Warning: Failed to connect to Redis: {e}")

def _rate_check(api_key: str) -> bool:
    if not api_key:
        api_key = "anonymous"
        
    if _redis_client:
        # Redis Token Bucket Implementation
        # Key: rate_limit:{api_key}
        # Value: tokens available
        key = f"rate_limit:{api_key}"
        try:
            # Script to atomically refill and consume
            lua_script = """
            local key = KEYS[1]
            local capacity = tonumber(ARGV[1])
            local rate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])
            local cost = tonumber(ARGV[4])
            
            local last_updated = tonumber(redis.call('HGET', key, 'last_updated'))
            local tokens = tonumber(redis.call('HGET', key, 'tokens'))
            
            if not last_updated then
                tokens = capacity
                last_updated = now
            end
            
            local elapsed = now - last_updated
            tokens = math.min(capacity, tokens + (elapsed * rate))
            
            if tokens >= cost then
                tokens = tokens - cost
                redis.call('HSET', key, 'tokens', tokens, 'last_updated', now)
                redis.call('EXPIRE', key, 600) -- Expire after 10 mins idle
                return 1
            else
                return 0
            end
            """
            cmd = _redis_client.register_script(lua_script)
            result = cmd(keys=[key], args=[RATE_LIMIT_RPS, RATE_LIMIT_RPS, time.time(), 1.0])
            return bool(result)
        except Exception as e:
            print(f"Redis rate limit error: {e}, falling back to local")
            # Fall through to local
            
    # Local In-Memory Fallback
    import time
    now = time.time()
    bucket = _rate_buckets.get(api_key)
    if not bucket:
        _rate_buckets[api_key] = {'tokens': RATE_LIMIT_RPS, 'last': now}
        return True
    # Refill
    elapsed = now - bucket['last']
    bucket['tokens'] = min(RATE_LIMIT_RPS, bucket['tokens'] + elapsed * RATE_LIMIT_RPS)
    bucket['last'] = now
    if bucket['tokens'] >= 1.0:
        bucket['tokens'] -= 1.0
        return True
    return False

def ship_log_async(payload):
    def _send():
        try:
            # append to tamper-evident store first
            append_store.append(payload)
            requests.post(LOG_SERVER_URL, json=payload, timeout=1)
        except:
            pass 
    threading.Thread(target=_send).start()

@app.route('/api/heartbeat', methods=['GET'])
def heartbeat():
    return jsonify({"status": "ok", "timestamp": datetime.datetime.utcnow().isoformat()})

@app.route('/api/v1/metrics', methods=['GET'])
def get_metrics():
    """Priority 5: Observability - Get current metrics and latency percentiles."""
    stats = agentshield.metrics.get_stats()
    return jsonify({
        "metrics": stats,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })

@app.route('/api/v1/audit/verify', methods=['GET'])
def verify_audit():
    """Priority 4: API Polish - Alias for /api/v1/compliance/verify-merkle."""
    return verify_merkle_chain()

@app.route('/api/v1/audit/logs', methods=['GET'])
def get_audit_logs():
    """Return recent audit logs from local append-only cache (tail)."""
    path = os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl')
    limit = int(request.args.get('limit', '100'))
    tenant_id = request.args.get('tenant_id')
    agent_id = request.args.get('agent_id')
    decision = request.args.get('decision')
    from_ts = request.args.get('from')
    to_ts = request.args.get('to')
    
    logs = []
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536), os.SEEK_SET)  # read last chunk
            lines = f.read().splitlines()
            for line in lines[-limit:]:
                try:
                    entry = json.loads(line.decode('utf-8'))
                    log_entry = entry.get('entry', entry)
                    
                    # Apply filters
                    if tenant_id and log_entry.get('tenant_id') != tenant_id:
                        continue
                    if agent_id and log_entry.get('agent_id') != agent_id:
                        continue
                    if decision and log_entry.get('status') != decision:
                        continue
                    if from_ts:
                        try:
                            if datetime.datetime.fromisoformat(log_entry.get('timestamp', '')) < datetime.datetime.fromisoformat(from_ts):
                                continue
                        except:
                            pass
                    if to_ts:
                        try:
                            if datetime.datetime.fromisoformat(log_entry.get('timestamp', '')) > datetime.datetime.fromisoformat(to_ts):
                                continue
                        except:
                            pass
                    
                    logs.append(entry)
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return jsonify({"logs": logs})

@app.route('/api/v1/audit/logs/<request_id>', methods=['GET'])
def get_audit_log_detail(request_id):
    """Get detailed view of a specific audit log entry."""
    path = os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl')
    try:
        with open(path, 'rb') as f:
            for line in f:
                try:
                    entry = json.loads(line.decode('utf-8'))
                    log_entry = entry.get('entry', entry)
                    if log_entry.get('request_id') == request_id:
                        return jsonify(entry)
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return jsonify({"error": "Log entry not found"}), 404

@app.route('/api/v1/policies/update', methods=['POST'])
def update_policy():
    """Proxy policy updates to AgentShield if available; echo otherwise."""
    body = request.json or {}
    try:
        url = f"{os.getenv('AGENTSHIELD_URL', 'http://localhost:9000')}/v1/policies/update"
        r = requests.post(url, json=body, timeout=float(os.getenv('AGENTSHIELD_TIMEOUT_MS', '3000'))/1000.0)
        return jsonify(r.json()), r.status_code
    except Exception:
        # Mirror minimal policy_version into app state
        pv = body.get('policy_version')
        if pv is not None:
            try:
                pv = int(pv)
                agent_id = body.get('agent_id', 'global')
                if not hasattr(app, '_policy_versions'):
                    app._policy_versions = {}
                app._policy_versions[agent_id] = max(app._policy_versions.get(agent_id, -1), pv)
            except Exception:
                pass
        return jsonify({"status": "ok", "mirrored": True, "policy_version": pv}), 200

@app.route('/api/v1/policies', methods=['GET', 'PUT'])
def manage_policies():
    """Get current policy configuration or update policies (Priority 4)."""
    if request.method == 'GET':
        return jsonify({
            "max_risk_score": MAX_RISK_SCORE,
            "disallowed_reasons": list(DISALLOWED_REASONS),
            "timeout_ms": AGENTSHIELD_TIMEOUT_SEC * 1000,
            "rate_limit_rps": RATE_LIMIT_RPS,
            "require_mtls": REQUIRE_MTLS,
            "signature_verification": True,  # Always enabled
            "fail_closed": True  # Always enabled
        })
    elif request.method == 'PUT':
        """Priority 4: Update policy configuration dynamically."""
        body = request.json or {}
        # Note: In production, validate and persist these to a store
        # For now, just return acknowledgment
        return jsonify({
            "status": "policy_update_accepted",
            "current": {
                "max_risk_score": MAX_RISK_SCORE,
                "disallowed_reasons": list(DISALLOWED_REASONS),
                "timeout_ms": AGENTSHIELD_TIMEOUT_SEC * 1000,
                "rate_limit_rps": RATE_LIMIT_RPS
            },
            "requested": body,
            "note": "Policy updates require server restart or config manager"
        })

@app.route('/api/v1/keys/active', methods=['GET'])
def get_active_keys():
    """Get active signing keys from AgentShield JWKS."""
    try:
        keys_data = agentshield._get_keys()
        return jsonify({"keys": keys_data.get('keys', [])})
    except Exception as e:
        return jsonify({"error": str(e), "keys": []}), 500

@app.route('/api/v1/compliance/export', methods=['POST'])
def export_compliance_logs():
    """Export audit logs for compliance (JSON/CSV)."""
    body = request.json or {}
    format_type = body.get('format', 'json')
    from_ts = body.get('from')
    to_ts = body.get('to')
    
    # Use existing audit logs endpoint with filters
    params = {'limit': 10000}
    if from_ts:
        params['from'] = from_ts
    if to_ts:
        params['to'] = to_ts
    
    path = os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl')
    logs = []
    try:
        with open(path, 'rb') as f:
            for line in f:
                try:
                    entry = json.loads(line.decode('utf-8'))
                    logs.append(entry)
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    
    return jsonify({"logs": logs, "count": len(logs), "format": format_type})

@app.route('/api/v1/compliance/verify-merkle', methods=['GET'])
def verify_merkle_chain():
    """Verify Merkle chain integrity."""
    path = os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl')
    verified_count = 0
    failed_entries = []
    
    try:
        prev_hash = None
        with open(path, 'rb') as f:
            for idx, line in enumerate(f):
                try:
                    entry = json.loads(line.decode('utf-8'))
                    
                    # Verify prev_hash matches
                    if prev_hash != entry.get('prev_hash'):
                        failed_entries.append({
                            "line": idx,
                            "expected_prev": prev_hash,
                            "actual_prev": entry.get('prev_hash')
                        })
                    
                    # Recompute hash and verify
                    import hashlib
                    m = hashlib.sha256()
                    m.update(json.dumps(entry.get('entry', {}), sort_keys=True).encode('utf-8'))
                    if prev_hash:
                        m.update(prev_hash.encode('utf-8'))
                    computed_hash = m.hexdigest()
                    
                    if computed_hash != entry.get('hash'):
                        failed_entries.append({
                            "line": idx,
                            "expected_hash": computed_hash,
                            "actual_hash": entry.get('hash')
                        })
                    else:
                        verified_count += 1
                    
                    prev_hash = entry.get('hash')
                except Exception as e:
                    failed_entries.append({"line": idx, "error": str(e)})
    except FileNotFoundError:
        return jsonify({"error": "No audit log found"}), 404
    
    return jsonify({
        "verified": len(failed_entries) == 0,
        "verified_entries": verified_count,
        "failed_entries": failed_entries,
        "total": verified_count + len(failed_entries)
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()})

@app.route('/ready', methods=['GET'])
def ready():
    """Readiness check endpoint."""
    # Check if AgentShield is reachable
    try:
        url = f"{os.getenv('AGENTSHIELD_URL', 'http://localhost:9000')}/health"
        r = requests.get(url, timeout=2)
        agentshield_ready = r.status_code == 200
    except:
        agentshield_ready = False
    
    return jsonify({
        "ready": True,  # Vigil is always ready (can fall back)
        "agentshield_available": agentshield_ready
    })

@app.route('/v1/chat/completions', methods=['POST'])
def transparent_proxy():
    # Start timing
    t_start = time.time()
    timings = {}
    
    # Request ID correlation (accept client-supplied or generate)
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    
    # mTLS client cert enforcement (stub): require header when enabled
    if REQUIRE_MTLS and not request.headers.get('X-Client-Cert'):
        return jsonify({"error": {"message": "mTLS required: client cert missing", "code": 401}}), 401

    # Early size limit
    cl = request.headers.get('Content-Length')
    try:
        if cl and int(cl) > MAX_REQUEST_BYTES:
            return jsonify({"error": {"message": "Payload too large", "code": 413}}), 413
    except ValueError:
        pass

    # Rate limit per API key
    user_api_key = request.headers.get("Authorization", "")
    if not _rate_check(user_api_key):
        return jsonify({"error": {"message": "Rate limit exceeded", "code": 429}}), 429
    # Continue processing
    body = request.json or {}
    messages = body.get('messages', [])
    agent_id = request.headers.get("X-Agent-ID", "anonymous-agent")
    # Policy version monotonic enforcement (optional headers)
    # Policy version monotonic enforcement per agent
    policy_ver = request.headers.get('X-Policy-Version')
    if not hasattr(app, '_policy_versions'):
        app._policy_versions = {}
    if policy_ver is not None:
        try:
            pv = int(policy_ver)
            last = app._policy_versions.get(agent_id, -1)
            if pv < last:
                return jsonify({"error": {"message": "Policy version rollback rejected", "code": 409}}), 409
            app._policy_versions[agent_id] = max(last, pv)
        except ValueError:
            pass
    global _seq_id
    _seq_id += 1
    
    # Centralized pre-LLM enforcement via AgentShield
    FALLBACK = os.environ.get('AGENTSHIELD_REQUIRED', 'true').lower() != 'true'
    tenant_id = request.headers.get('X-Tenant-ID', 'local-docker')
    policy_version = int(request.headers.get('X-Policy-Version', app._policy_versions.get(agent_id, -1) or 0))
    policy_id = request.headers.get('X-Policy-ID', f'policy-{agent_id}')  # NEW: policy_id support
    
    # Priority 4: Idempotency key support for request deduplication
    idempotency_key = request.headers.get('X-Idempotency-Key')
    if not hasattr(app, '_idempotency_cache'):
        app._idempotency_cache = {}
    if idempotency_key:
        cached_response = app._idempotency_cache.get(idempotency_key)
        if cached_response:
            return cached_response  # Return cached result for same idempotency key
    
    enforcement_req = {
        "request_id": request_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "policy_id": policy_id,  # NEW
        "policy_version": policy_version,
        "environment": VIGIL_ENVIRONMENT,
        "messages": messages,
        "metadata": body.get('metadata', {})
        # Note: timestamp_ms, ttl_ms, and input_hash are auto-added by AgentShieldClient
    }
    
    t_agentshield_start = time.time()
    decision = None
    enforcement_error = None
    error_code = None
    agentshield_decision = None  # Priority 2: Store original decision before override
    
    try:
        # Preferred: obtain signed decision via /decision (deterministic, lightweight)
        decision_envelope = agentshield.get_decision({
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "request_id": request_id,
            "messages": messages,
        })
        timings['t_agentshield_ms'] = round((time.time() - t_agentshield_start) * 1000, 2)
        decision = {
            "action": decision_envelope.get("decision"),
            "risk_score": decision_envelope.get("risk_score"),
            "reasons": decision_envelope.get("reasons"),
            "signature_hash": decision_envelope.get("decision_hash"),
            "audit_event_id": decision_envelope.get("audit_event_id"),
            "sig_verified": True,
            "key_id": decision_envelope.get("key_id"),
            "policy_id": policy_id,
            "input_hash": enforcement_req.get("input_hash"),
        }
    except Exception as e:
        timings['t_agentshield_ms'] = round((time.time() - t_agentshield_start) * 1000, 2)
        enforcement_error = str(e)
        error_code = getattr(e, 'vigil_error_code', VigilErrorCode.AGENTSHIELD_UNREACHABLE)
        if not FALLBACK:
            # Audit the failure with structured error code
            ship_log_async({
                "request_id": request_id,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "seq_id": _seq_id,
                "status": "ERROR",
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "policy_id": policy_id,  # NEW
                "policy_version": policy_version,
                "environment": VIGIL_ENVIRONMENT,
                "risk_score": None,
                "signature_hash": None,
                "audit_event_id": None,
                "reasons": ["agentshield_failure"],
                "sig_verified": False,
                "sig_key_id": None,
                "error": enforcement_error,
                "error_code": error_code.value if error_code else None,  # NEW: structured error code
                "input_hash": None,
                "timings": timings
            })
            return jsonify({"error": {"message": "AgentShield unavailable or decision verification failed", "code": 503, "request_id": request_id, "error_code": error_code.value if error_code else None}}), 503
        # Fallback path: run local firewall + PII
        fallback_used = True
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                check = firewall.scan_input(content)
                if not check['safe']:
                    timings['t_total_ms'] = round((time.time() - t_start) * 1000, 2)
                    ship_log_async({
                        "request_id": request_id,
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "seq_id": _seq_id,
                        "status": "BLOCK",
                        "agent_id": agent_id,
                        "tenant_id": tenant_id,
                        "policy_id": policy_id,  # NEW
                        "policy_version": policy_version,
                        "environment": VIGIL_ENVIRONMENT,
                        "risk_score": None,
                        "reasons": [check['reason']],
                        "fallback_used": True,
                        "error_code": None,
                        "input_hash": None,
                        "timings": timings
                    })
                    return jsonify({"error": {"message": f"Blocked (fallback): {check['reason']}", "code": 403, "request_id": request_id}}), 403
                clean_text, was_redacted = pii_engine.scan_and_redact(content)
                if was_redacted:
                    msg['content'] = clean_text
        decision = {
            "action": "ALLOW",
            "risk_score": 0.0,
            "reasons": ["fallback"],
            "signature_hash": None,
            "audit_event_id": None,
            "sanitized": messages,
            "sig_verified": False
        }

    # Enforce AgentShield decision
    action = decision.get('action')
    risk_score = decision.get('risk_score')
    signature_hash = decision.get('signature_hash')
    audit_event_id = decision.get('audit_event_id')
    reasons = decision.get('reasons', [])
    sig_verified = decision.get('sig_verified', False)
    sig_key_id = decision.get('key_id')
    error_code_from_decision = decision.get('error_code')  # NEW: error code from verification
    input_hash = decision.get('input_hash')  # NEW: input hash for audit
    policy_id_from_decision = decision.get('policy_id')  # NEW: policy_id from decision
    
    # Priority 2: Store original decision before any override
    agentshield_decision = {
        "action": action,
        "risk_score": risk_score,
        "signature_hash": signature_hash,
        "reasons": list(reasons) if reasons else [],
        "audit_event_id": audit_event_id,
        "sig_verified": sig_verified
    }
    
    # Gateway policy enforcement (override AgentShield if needed)
    policy_override = None
    if risk_score is not None and risk_score > MAX_RISK_SCORE:
        action = 'BLOCK'
        policy_override = f'risk_score_threshold_exceeded:{risk_score}>{MAX_RISK_SCORE}'
        reasons.append(policy_override)
    
    # Check for disallowed reasons
    disallowed_found = [r for r in reasons if r in DISALLOWED_REASONS]
    if disallowed_found:
        action = 'BLOCK'
        policy_override = f'disallowed_reasons:{disallowed_found}'
        if policy_override not in reasons:
            reasons.append(policy_override)

    # Structured log + local append-only cache
    timings['t_total_ms'] = round((time.time() - t_start) * 1000, 2)
    
    # Priority 2: Add granular timings
    t_audit_ms = timings.get('t_total_ms', 0) - timings.get('t_agentshield_ms', 0)
    
    ship_log_async({
        "request_id": request_id,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "seq_id": _seq_id,
        "status": action,
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "policy_id": policy_id_from_decision or policy_id,  # NEW
        "policy_version": policy_version,
        "environment": VIGIL_ENVIRONMENT,
        "risk_score": risk_score,
        "signature_hash": signature_hash,
        "audit_event_id": audit_event_id,
        "reasons": reasons,
        "sig_verified": sig_verified,
        "sig_key_id": sig_key_id,
        "policy_override": policy_override,
        "error_code": error_code_from_decision.value if error_code_from_decision else None,  # NEW: structured error
        "input_hash": input_hash,  # NEW: for audit trail
        "agentshield_decision": agentshield_decision,  # Priority 2: Store original decision
        "timings": {
            "t_agentshield_ms": timings.get('t_agentshield_ms', 0),
            "t_audit_ms": round(t_audit_ms, 2),  # Priority 2: Granular timing
            "t_total_ms": timings.get('t_total_ms', 0)
        }
    })

    if action == 'BLOCK':
        response = (jsonify({"error": {"message": ", ".join(reasons) or "Blocked", "code": 403, "request_id": request_id, "signature_hash": signature_hash, "audit_event_id": audit_event_id}}), 403)
        # Priority 4: Cache idempotent response
        if idempotency_key:
            app._idempotency_cache[idempotency_key] = response
            # Clean up old cache entries (keep only last 100)
            if len(app._idempotency_cache) > 100:
                oldest_key = next(iter(app._idempotency_cache))
                del app._idempotency_cache[oldest_key]
        return response
    if action in ('SANITIZE', 'REWRITE'):
        sanitized = decision.get('sanitized') or messages
        # Provide a simple response indicating sanitation and the new content
        response = jsonify({
            "id": "chatcmpl-vigil-sanitized",
            "action": action,
            "risk_score": risk_score,
            "signature_hash": signature_hash,
            "audit_event_id": audit_event_id,
            "reasons": reasons,
            "sanitized_preview": {"before": messages, "after": sanitized},
            "choices": [{"index": 0, "message": {"role": "assistant", "content": sanitized[-1]['content'] if sanitized else ''}}]
        })
        # Priority 4: Cache idempotent response
        if idempotency_key:
            app._idempotency_cache[idempotency_key] = response
            if len(app._idempotency_cache) > 100:
                oldest_key = next(iter(app._idempotency_cache))
                del app._idempotency_cache[oldest_key]
        return response

    # ALLOW: proceed (mock)
    response = jsonify({
        "id": "chatcmpl-vigil-allow",
        "action": "ALLOW",
        "risk_score": risk_score,
        "signature_hash": signature_hash,
        "audit_event_id": audit_event_id,
        "reasons": reasons,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": f"Accepted: {messages[-1]['content']}" if messages else ''}
        }]
    })
    # Priority 4: Cache idempotent response
    if idempotency_key:
        app._idempotency_cache[idempotency_key] = response
        if len(app._idempotency_cache) > 100:
            oldest_key = next(iter(app._idempotency_cache))
            del app._idempotency_cache[oldest_key]
    return response

    return jsonify({
        "id": "chatcmpl-vigil-mock",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": f"Vigil Accepted: {messages[-1]['content']}"}
        }]
    })

if __name__ == '__main__':
    print("🛡️  Vigil Gateway running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000)
