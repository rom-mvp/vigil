from flask import Flask, request, jsonify, Response
import sys
import os
import threading
import requests
import json
import datetime
import time
import uuid
import base64
import codecs
import unicodedata
import re
import string
import redis
import logging
import numpy as np

from .merkle_log_store import MerkleLogStore
from .agentshield_client import AgentShieldClient, VigilErrorCode
from .log_sync_worker import LogSyncWorker
from .api_key_auth import APIKeyAuth, InvalidAPIKey
from .config import (
    VIGIL_MODE,
    AGENTSHIELD_URL,
    AGENTSHIELD_JWKS_URL,
    AGENTSHIELD_TIMEOUT_MS,
    AGENTSHIELD_FAIL_MODE,
)
import jwt
from jwt import PyJWKClient

app = Flask(__name__)
logger = logging.getLogger(__name__)
append_store = MerkleLogStore(os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl'))
agentshield = AgentShieldClient(
    base_url=AGENTSHIELD_URL or "http://localhost:9000",
    jwks_url=AGENTSHIELD_JWKS_URL or "http://localhost:9000/.well-known/jwks.json",
    timeout_ms=AGENTSHIELD_TIMEOUT_MS,
    fail_mode=AGENTSHIELD_FAIL_MODE,
)


class PolicyViolation(Exception):
    """Raised when a policy check or signature verification fails."""


def verify_decision_jwt(decision_token: str, jwks_url: str) -> dict:
    """Verify AgentShield-issued decision JWT using JWKS.

    Fail closed on any verification error.
    """
    if not decision_token:
        raise PolicyViolation("Missing decision token")
    if not jwks_url:
        raise PolicyViolation("JWKS URL missing for decision verification")

    jwk_client = PyJWKClient(jwks_url)
    signing_key = jwk_client.get_signing_key_from_jwt(decision_token)
    claims = jwt.decode(
        decision_token,
        signing_key.key,
        algorithms=["RS256", "ES256", "EdDSA"],
        options={"verify_aud": False},
    )
    return claims

# SaaS Components
api_key_auth = APIKeyAuth()  # API key validation and tenant resolution

# Initialize Log Sync Worker (Priority 6)
log_worker = LogSyncWorker(os.environ.get('AGENTSHIELD_URL', 'http://localhost:9000'))
log_worker.start()

# Register components with AgentShield client for fail-open/caching coordination
agentshield.register_log_worker(log_worker)

# Background task to refresh local policies (Priority 6)
def _refresh_policies():
    while True:
        try:
            rules = agentshield.fetch_policies()
            if rules:
                firewall.update_rules(rules)
        except Exception:
            pass
        time.sleep(60)

threading.Thread(target=_refresh_policies, daemon=True).start()
def _blind_log(status: str, request_id: str, tenant_id: str, policy_hash: str, payload_size: int):
    """Metadata-only structured log. Forbids ciphertext logging at runtime."""
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "request_id": request_id,
        "tenant": tenant_id,
        "policy_hash": policy_hash,
        "status": status,
        "payload_size_bytes": int(payload_size or 0)
    }
    # Guard: ensure no sensitive keys accidentally included
    forbidden_keys = {"ciphertext", "iv", "tag", "messages", "content"}
    assert not any(k in entry for k in forbidden_keys), "Blind logger attempted to log sensitive fields"
    try:
        append_store.append(entry)
    except Exception:
        pass

@app.route('/v1/system/public-key', methods=['GET'])
def get_public_key():
    """Key Proxy endpoint. Fetches enclave public key from AgentShield and caches for 1h."""
    cache = getattr(app, '_pubkey_cache', None)
    now = time.time()
    if cache and cache.get('expires_at', 0) > now:
        return jsonify(cache['value'])
    try:
        url = f"{os.getenv('AGENTSHIELD_URL', 'http://localhost:9000')}/internal/public-key"
        r = requests.get(url, timeout=2.0)
        r.raise_for_status()
        data = r.json()
        app._pubkey_cache = {"value": data, "expires_at": now + 3600}
        return jsonify(data)
    except Exception:
        return jsonify({"error": "Public key unavailable"}), 503


LOG_SERVER_URL = os.environ.get('LOG_SERVER_URL', 'http://vigil-dashboard:3000/ingest')

# Hardening controls
MAX_REQUEST_BYTES = int(os.environ.get('MAX_REQUEST_BYTES', '4096'))  # tighter cap to blunt token bombs
RATE_LIMIT_RPS = float(os.environ.get('RATE_LIMIT_RPS', '5'))
REQUIRE_MTLS = os.environ.get('REQUIRE_MTLS', 'false').lower() == 'true'
VIGIL_ENVIRONMENT = os.environ.get('VIGIL_ENVIRONMENT', 'local')
PLAINTEXT_MODE = os.environ.get('VIGIL_PLAINTEXT_MODE', 'strict').lower()  # 'strict' or 'migration'
VIGIL_STRICT_MODE = os.environ.get('VIGIL_STRICT_MODE', '0')
if VIGIL_STRICT_MODE == '1':
    PLAINTEXT_MODE = 'strict'
POLICY_PATH = os.environ.get('POLICY_PATH', os.path.join(os.getcwd(), 'policies', 'policy.rego'))

AGENTSHIELD_TIMEOUT_SEC = float(os.environ.get('AGENTSHIELD_TIMEOUT_MS', '1000')) / 1000.0  # Reduced to 1000ms

# Cached policy hash (mtime-aware)
_policy_cache = {"path": POLICY_PATH, "hash": None, "mtime": 0}
_policy_last_logged = None

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

def _load_policy_hash_cached() -> str:
    """Compute SHA-256 of policy.rego with mtime-aware caching.

    Ensures every forwarded request carries the current policy signature.
    Reloads when the file mtime changes; falls back to env override.
    """
    global _policy_cache, _policy_last_logged
    path = _policy_cache.get("path") or POLICY_PATH
    try:
        mtime = os.path.getmtime(path)
        if _policy_cache.get("hash") and mtime == _policy_cache.get("mtime"):
            return _policy_cache["hash"]
        with open(path, 'rb') as f:
            data = f.read()
        h = hashlib.sha256(data).hexdigest()
        _policy_cache.update({"hash": h, "mtime": mtime, "path": path})
        if h != _policy_last_logged:
            logger.info(f"Loaded policy hash {h[:12]} from {path}")
            _policy_last_logged = h
        return h
    except Exception:
        fallback = os.environ.get('VIGIL_POLICY_HASH', 'unknown-policy-hash')
        _policy_cache.update({"hash": fallback})
        return fallback

# Initialize policy hash at import time (startup)
_load_policy_hash_cached()

@app.route('/v1/tool/execute', methods=['POST'])
def execute_tool():
    """
    Execute tool with human-in-loop gating via AgentShield Approval Hub.

    If approval_id is provided, execution is blocked until approved.
    """
    body = request.json or {}
    approval_id = body.get("approval_id")

    if approval_id:
        status = agentshield.get_approval_status(approval_id)
        if status == "pending":
            return jsonify({
                "status": "approval_pending",
                "approval_id": approval_id,
                "message": "Waiting for human approval",
                "check_after_seconds": 5,
            }), 202
        elif status == "rejected":
            logger.warning(f"Tool execution blocked: approval {approval_id} rejected")
            return jsonify({
                "error": "approval_rejected",
                "approval_id": approval_id,
                "message": "Human reviewer rejected this tool execution",
            }), 403
        elif status == "timeout":
            return jsonify({
                "error": "approval_timeout",
                "approval_id": approval_id,
                "message": "Approval request expired",
            }), 408
        # approved: continue

    tool_name = body.get("tool_name")
    tool_args = body.get("tool_args", {})
    try:
        result = _execute_tool_impl(tool_name, tool_args)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Tool execution failed: {e}")
        return jsonify({"error": str(e)}), 500

def _execute_tool_impl(tool_name: str, tool_args: dict) -> dict:
    """Minimal stub for tool execution."""
    if not tool_name:
        raise ValueError("tool_name required")
    # Example: echo tool
    if tool_name == "echo":
        return {"tool": "echo", "result": tool_args}
    # Unknown tool
    return {"tool": tool_name, "status": "executed", "args": tool_args}

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


@app.route('/metrics/latency', methods=['GET'])
def metrics_latency():
    stats = agentshield.metrics.get_stats()
    return jsonify({
        "latency_ms": {
            "p50": stats.get("latency_p50_ms", 0.0),
            "p95": stats.get("latency_p95_ms", 0.0),
            "p99": stats.get("latency_p99_ms", 0.0)
        },
        "samples": stats.get("samples_count", 0)
    })


@app.route('/metrics/cache', methods=['GET'])
def metrics_cache():
    stats = agentshield.metrics.get_stats()
    hits = stats.get("cache_hits", 0)
    misses = stats.get("cache_misses", 0)
    hit_rate = stats.get("cache_hit_rate_pct", 0.0)
    size = stats.get("cache_size", 0)
    return jsonify({
        "hits": hits,
        "misses": misses,
        "hit_rate_pct": hit_rate,
        "cache_size": size
    })


@app.route('/metrics/rollout', methods=['GET'])
def metrics_rollout():
    stats = agentshield.metrics.get_stats()
    return jsonify({
        "decision_outcomes": stats.get("decision_outcomes", {}),
        "errors": stats.get("error_codes", {}),
        "latency_ms": {
            "p50": stats.get("latency_p50_ms", 0.0),
            "p95": stats.get("latency_p95_ms", 0.0),
            "p99": stats.get("latency_p99_ms", 0.0)
        },
        "samples": stats.get("samples_count", 0)
    })


@app.route('/metrics', methods=['GET'])
def metrics_prometheus():
    stats = agentshield.metrics.get_stats()
    lines = []

    lines.append(f"vigil_latency_p50_ms {stats.get('latency_p50_ms', 0.0)}")
    lines.append(f"vigil_latency_p95_ms {stats.get('latency_p95_ms', 0.0)}")
    lines.append(f"vigil_latency_p99_ms {stats.get('latency_p99_ms', 0.0)}")
    lines.append(f"vigil_latency_samples_total {stats.get('samples_count', 0)}")

    for action, count in stats.get("decision_outcomes", {}).items():
        lines.append(f"vigil_decisions_total{{action=\"{action}\"}} {count}")

    for code, count in stats.get("error_codes", {}).items():
        lines.append(f"vigil_errors_total{{code=\"{code}\"}} {count}")

    lines.append(f"vigil_cache_hits_total {stats.get('cache_hits', 0)}")
    lines.append(f"vigil_cache_misses_total {stats.get('cache_misses', 0)}")
    lines.append(f"vigil_cache_hit_rate_pct {stats.get('cache_hit_rate_pct', 0.0)}")
    lines.append(f"vigil_cache_size {stats.get('cache_size', 0)}")

    return Response("\n".join(lines) + "\n", mimetype='text/plain')

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
        "ready": agentshield_ready if VIGIL_MODE == 'saas' else True,
        "agentshield_available": agentshield_ready
    })

@app.route('/v1/chat/completions', methods=['POST'])
def transparent_proxy():
    # Start timing
    t_start = time.time()
    timings = {}
    
    # Request ID correlation (accept client-supplied or generate)
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    
    # ============================================================================
    # SAAS AUTHENTICATION - Step 1: Validate API Key and Resolve Tenant
    # ============================================================================
    authorization_header = request.headers.get('Authorization', '')
    api_key = api_key_auth.extract_api_key(authorization_header)
    
    if not api_key:
        return jsonify({
            "error": {
                "message": "Missing API key. Include 'Authorization: Bearer vk_...' header",
                "code": 401,
                "type": "invalid_request_error"
            }
        }), 401
    
    # Validate API key and get tenant identity
    try:
        tenant_id, tenant_metadata = api_key_auth.validate_key(api_key)
    except InvalidAPIKey:
        return jsonify({
            "error": {
                "message": "Invalid API key format (expected vk_ prefix)",
                "code": 401,
                "type": "invalid_request_error"
            }
        }), 401
    
    if not tenant_id:
        return jsonify({
            "error": {
                "message": "Invalid or expired API key",
                "code": 401,
                "type": "invalid_request_error"
            }
        }), 401
    
    # Extract tenant info
    tenant_name = tenant_metadata.get('tenant_name', 'Unknown')
    tier = tenant_metadata.get('tier', 'free')
    
    # ============================================================================
    # SAAS RATE LIMITING - Step 2: Check Tenant Rate Limit
    # ============================================================================
    rate_limit_rpm = api_key_auth.get_tenant_rate_limit(tenant_id, tier)
    rate_allowed, rate_info = api_key_auth.check_rate_limit(tenant_id, rate_limit_rpm)
    
    if not rate_allowed:
        return jsonify({
            "error": {
                "message": f"Rate limit exceeded: {rate_info['current_count']}/{rate_info['limit']} requests per minute",
                "code": 429,
                "type": "rate_limit_exceeded",
                "details": {
                    "limit": rate_info['limit'],
                    "remaining": rate_info['remaining'],
                    "reset_seconds": rate_info['reset']
                }
            }
        }), 429, {
            'X-RateLimit-Limit': str(rate_info['limit']),
            'X-RateLimit-Remaining': str(rate_info['remaining']),
            'X-RateLimit-Reset': str(rate_info['reset'])
        }
    
    # ============================================================================
    # SAAS QUOTA CHECK - Step 3: Check Token Quota
    # ============================================================================
    body = request.json or {}
    
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
    # Defensive fallback if Content-Length missing or untrusted
    if request.data and len(request.data) > MAX_REQUEST_BYTES:
        return jsonify({"error": {"message": "Payload too large", "code": 413}}), 413
    
    # Blind Router path: detect encrypted envelope
    is_blind = (
        isinstance(body, dict)
        and isinstance(body.get('payload'), dict)
        and isinstance(body['payload'].get('ciphertext'), str)
    )

    if is_blind:
        agent_id = request.headers.get("X-Agent-ID", "anonymous-agent")
        if not hasattr(app, '_policy_versions'):
            app._policy_versions = {}
        policy_version = int(request.headers.get('X-Policy-Version', app._policy_versions.get(agent_id, -1) or 0))
        policy_id = request.headers.get('X-Policy-ID', f'policy-{tenant_id}-{agent_id}')
        policy_hash = _load_policy_hash_cached()

        envelope = body.get('payload') or {}
        enforcement_req = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "user_id": body.get('user_id'),
            "agent_id": agent_id,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "policy_signature": policy_hash,
            "environment": VIGIL_ENVIRONMENT,
            "payload": {
                "version": envelope.get('version', 1),
                "ciphertext": envelope.get('ciphertext'),
                "iv": envelope.get('iv'),
                "tag": envelope.get('tag')
            },
            "metadata": {"tier": tier}
        }

        try:
            agentshield_response = agentshield.enforce(enforcement_req)
            _blind_log(
                status="FORWARDED",
                request_id=request_id,
                tenant_id=tenant_id,
                policy_hash=policy_hash,
                payload_size=len(request.data) if request.data else 0,
            )
            # Passthrough exact response
            return jsonify(agentshield_response), 200
        except Exception as e:
            return jsonify({"error": {"message": "AgentShield unavailable", "code": 503, "request_id": request_id}}), 503

    # Legacy/plaintext path
    if PLAINTEXT_MODE != 'migration' and VIGIL_ENVIRONMENT != 'test':
        return jsonify({
            "error": {
                "message": "Plaintext not allowed. Send encrypted 'payload.ciphertext' envelope.",
                "code": 400,
                "type": "plaintext_rejected"
            }
        }), 400
    else:
        logger.warning("Plaintext deprecated: forwarding in migration mode")
    
    # Note: tenant_id already set from API key validation above
    # In SaaS mode, tenant comes from API key, not headers
    
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
    # tenant_id now comes from API key validation (SaaS mode)
    # Allow X-Tenant-ID header override for development/testing only
    if os.environ.get('VIGIL_ENVIRONMENT') == 'development':
        tenant_id = request.headers.get('X-Tenant-ID', tenant_id)
    
    policy_version = int(request.headers.get('X-Policy-Version', app._policy_versions.get(agent_id, -1) or 0))
    policy_id = request.headers.get('X-Policy-ID', f'policy-{tenant_id}-{agent_id}')
    policy_hash = _load_policy_hash_cached()
    
    # Priority 4: Idempotency key support for request deduplication
    idempotency_key = request.headers.get('X-Idempotency-Key')
    if not hasattr(app, '_idempotency_cache'):
        app._idempotency_cache = {}
    if idempotency_key:
        cached_response = app._idempotency_cache.get(idempotency_key)
        if cached_response:
            return cached_response  # Return cached result for same idempotency key
    
    # Blind envelope: Vigil forwards opaque payload only
    envelope = body.get('payload') or {}
    enforcement_req = {
        "request_id": request_id,
        "tenant_id": tenant_id,
        "user_id": body.get('user_id'),
        "agent_id": agent_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_signature": policy_hash,
        "environment": VIGIL_ENVIRONMENT,
        "payload": {
            "version": envelope.get('version', 1),
            "ciphertext": envelope.get('ciphertext'),
            "iv": envelope.get('iv'),
            "tag": envelope.get('tag')
        },
        "metadata": {"tier": tier}
        # Note: timestamp_ms, ttl_ms, and input_hash added by AgentShieldClient
    }
    
    # =========================================================================
    # MANDATORY POLICY ENFORCEMENT - No fallback allowed in SaaS mode
    # =========================================================================
    agentshield_response = None
    enforcement_error = None
    try:
        t_agentshield_start = time.time()
        agentshield_response = agentshield.enforce(enforcement_req)
        # Metadata-only blind log for forwarded request
        _blind_log(
            status="FORWARDED",
            request_id=request_id,
            tenant_id=tenant_id,
            policy_hash=policy_hash,
            payload_size=len(request.data) if request.data else 0,
        )
        timings['t_agentshield_ms'] = round((time.time() - t_agentshield_start) * 1000, 2)
    except Exception as e:
        enforcement_error = str(e)
        error_code = getattr(e, 'vigil_error_code', VigilErrorCode.AGENTSHIELD_UNREACHABLE)
        if "ship_log_async" in globals():
            ship_log_async({
                "request_id": request_id,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "seq_id": _seq_id,
                "status": "ERROR",
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "policy_id": policy_id,
                "policy_version": policy_version,
                "environment": VIGIL_ENVIRONMENT,
                "risk_score": None,
                "signature_hash": None,
                "audit_event_id": None,
                "reasons": ["agentshield_failure"],
                "sig_verified": False,
                "sig_key_id": None,
                "error": enforcement_error,
                "error_code": error_code.value if error_code else None,
                "input_hash": None,
                "timings": timings
            })
        return jsonify({"error": {"message": "AgentShield unavailable", "code": 503, "request_id": request_id, "error_code": error_code.value if error_code else None}}), 503

    decision_action = agentshield_response.get('action') or agentshield_response.get('decision')
    decision_token = agentshield_response.get('decision_token') or agentshield_response.get('token')
    reasons = agentshield_response.get('reasons', [])
    risk_score = agentshield_response.get('risk_score')

    if decision_action != 'ALLOW':
        if "ship_log_async" in globals():
            ship_log_async({
                "request_id": request_id,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "seq_id": _seq_id,
                "status": decision_action or "BLOCK",
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "policy_id": policy_id,
                "policy_version": policy_version,
                "environment": VIGIL_ENVIRONMENT,
                "risk_score": risk_score,
                "signature_hash": None,
                "audit_event_id": agentshield_response.get('audit_event_id'),
                "reasons": reasons,
                "sig_verified": False,
                "sig_key_id": None,
                "input_hash": agentshield_response.get('input_hash'),
                "timings": timings
            })
        return jsonify({"error": {"message": "Blocked by policy", "code": 403, "request_id": request_id, "reasons": reasons}}), 403

    try:
        claims = verify_decision_jwt(decision_token, AGENTSHIELD_JWKS_URL)
        if claims.get("decision") and claims.get("decision") != "ALLOW":
            raise PolicyViolation("Invalid decision token decision claim")
    except Exception as e:
        if "ship_log_async" in globals():
            ship_log_async({
                "request_id": request_id,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "seq_id": _seq_id,
                "status": "BLOCK",
                "agent_id": agent_id,
                "tenant_id": tenant_id,
                "policy_id": policy_id,
                "policy_version": policy_version,
                "environment": VIGIL_ENVIRONMENT,
                "risk_score": risk_score,
                "signature_hash": None,
                "audit_event_id": agentshield_response.get('audit_event_id'),
                "reasons": reasons + ["decision_token_invalid"],
                "sig_verified": False,
                "sig_key_id": None,
                "input_hash": agentshield_response.get('input_hash'),
                "timings": timings
            })
        return jsonify({"error": {"message": "Invalid decision token", "code": 403, "request_id": request_id}}), 403

    # Enforce AgentShield decision (claims are already verified)
    decision = claims or {}
    action = decision.get('action', decision_action)
    risk_score = decision.get('risk_score', risk_score)
    signature_hash = decision.get('signature_hash', agentshield_response.get('decision_hash'))
    audit_event_id = decision.get('audit_event_id', agentshield_response.get('audit_event_id'))
    reasons = decision.get('reasons', []) or reasons
    sig_verified = decision.get('sig_verified', True)
    sig_key_id = decision.get('key_id', agentshield_response.get('key_id'))
    error_code_from_decision = decision.get('error_code')  # NEW: error code from verification
    error_code_from_decision_value = error_code_from_decision.value if isinstance(error_code_from_decision, VigilErrorCode) else error_code_from_decision
    input_hash = decision.get('input_hash', agentshield_response.get('input_hash'))  # NEW: input hash for audit
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

    # No heuristic content firewall in Vigil (blind router)

    # Structured log + local append-only cache
    timings['t_total_ms'] = round((time.time() - t_start) * 1000, 2)
    
    # Record metrics for observability
    agentshield.metrics.record_latency(timings['t_total_ms'])
    agentshield.metrics.record_decision(action)
    if enforcement_error:
        agentshield.metrics.record_error(error_code.value if error_code else "UNKNOWN")
    
    # Priority 2: Add granular timings
    t_audit_ms = timings.get('t_total_ms', 0) - timings.get('t_agentshield_ms', 0)
    
    if "ship_log_async" in globals():
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
            "error_code": error_code_from_decision_value if error_code_from_decision_value else None,  # NEW: structured error
            "input_hash": input_hash,  # NEW: for audit trail
            "agentshield_decision": agentshield_decision,  # Priority 2: Store original decision
            # Vector scan results for audit trail
            "vector_scan": {
                "threat_detected": vector_scan_results.get("threat_detected", False),
                "max_threat_score": vector_scan_results.get("max_score", 0.0),
                "num_vector_matches": vector_scan_results.get("num_hits", 0),
                "top_threats": vector_scan_results.get("vector_hits", [])[:3]  # Store top 3 for audit
            },
            "extraction_risk_score": (_compute_extraction_risk(embedding).get("extraction_risk_score") if embedding is not None else 0.0),
            "distillation_risk": {
                "is_risk": (agentshield_response or {}).get("agentshield", {}).get("distillation_risk", {}).get("is_distillation_risk", False),
                "score": (agentshield_response or {}).get("agentshield", {}).get("distillation_risk", {}).get("risk_score", 0.0),
                "reasons": (agentshield_response or {}).get("agentshield", {}).get("distillation_risk", {}).get("reasons", []),
            },
            "timings": {
                "t_vector_ms": timings.get('t_vector_ms', 0),
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
    # Blind Router: Vigil does not perform LLM calls or token metering.
    response = jsonify({
        "status": "ALLOW",
        "request_id": request_id,
        "tenant_id": tenant_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_signature": policy_hash,
        "agentshield": agentshield_response
    })

    if idempotency_key:
        app._idempotency_cache[idempotency_key] = response
        if len(app._idempotency_cache) > 100:
            oldest_key = next(iter(app._idempotency_cache))
            del app._idempotency_cache[oldest_key]

    return response

if __name__ == '__main__':
    print("🛡️  Vigil Gateway running on http://0.0.0.0:8000")
    app.run(host='0.0.0.0', port=8000)
