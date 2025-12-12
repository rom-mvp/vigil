from flask import Flask, request, jsonify
import sys
import os
import threading
import requests
import json
import datetime

sys.path.append(os.getcwd())
from firewall_engine import FirewallEngine
from pii_engine import PIIEngine
from merkle_log_store import MerkleLogStore
from agentshield_client import AgentShieldClient

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

# Simple per-API-key token buckets (in-memory)
_rate_buckets = {}
_seq_id = 0

def _rate_check(api_key: str) -> bool:
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

@app.route('/api/v1/audit/logs', methods=['GET'])
def get_audit_logs():
    """Return recent audit logs from local append-only cache (tail)."""
    path = os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl')
    limit = int(request.args.get('limit', '100'))
    logs = []
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 65536), os.SEEK_SET)  # read last chunk
            lines = f.read().splitlines()
            for line in lines[-limit:]:
                try:
                    logs.append(json.loads(line.decode('utf-8')))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return jsonify({"logs": logs})

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

@app.route('/v1/chat/completions', methods=['POST'])
def transparent_proxy():
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
    enforcement_req = {
        "request_id": f"req_{datetime.datetime.now().timestamp()}",
        "tenant_id": request.headers.get('X-Tenant-ID', 'local-docker'),
        "agent_id": agent_id,
        "policy_version": int(request.headers.get('X-Policy-Version', app._policy_versions.get(agent_id, -1) or 0)),
        "environment": VIGIL_ENVIRONMENT,
        "messages": messages,
        "metadata": body.get('metadata', {})
    }
    try:
        decision = agentshield.enforce(enforcement_req)
    except Exception as e:
        if not FALLBACK:
            return jsonify({"error": {"message": "AgentShield unavailable or decision verification failed", "code": 503}}), 503
        # Fallback path: run local firewall + PII
        fallback_used = True
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                check = firewall.scan_input(content)
                if not check['safe']:
                    ship_log_async({
                        "request_id": enforcement_req["request_id"],
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "seq_id": _seq_id,
                        "status": "BLOCK",
                        "agent_id": agent_id,
                        "tenant_id": enforcement_req['tenant_id'],
                        "details": {"reason": check['reason'], "redacted": False, "FALLBACK_USED": True}
                    })
                    return jsonify({"error": {"message": f"Blocked (fallback): {check['reason']}", "code": 403}}), 403
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

    # Structured log + local append-only cache
    ship_log_async({
        "request_id": enforcement_req["request_id"],
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "seq_id": _seq_id,
        "status": action,
        "agent_id": agent_id,
        "tenant_id": enforcement_req['tenant_id'],
        "policy_version": enforcement_req.get('policy_version'),
        "environment": enforcement_req.get('environment'),
        "risk_score": risk_score,
        "signature_hash": signature_hash,
        "audit_event_id": audit_event_id,
        "reasons": reasons,
        "sig_verified": sig_verified,
        "sig_key_id": sig_key_id
    })

    if action == 'BLOCK':
        return jsonify({"error": {"message": ", ".join(reasons) or "Blocked", "code": 403, "signature_hash": signature_hash, "audit_event_id": audit_event_id}}), 403
    if action in ('SANITIZE', 'REWRITE'):
        sanitized = decision.get('sanitized') or messages
        # Provide a simple response indicating sanitation and the new content
        return jsonify({
            "id": "chatcmpl-vigil-sanitized",
            "action": action,
            "risk_score": risk_score,
            "signature_hash": signature_hash,
            "audit_event_id": audit_event_id,
            "reasons": reasons,
            "sanitized_preview": {"before": messages, "after": sanitized},
            "choices": [{"index": 0, "message": {"role": "assistant", "content": sanitized[-1]['content'] if sanitized else ''}}]
        })

    # ALLOW: proceed (mock)
    return jsonify({
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
