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

app = Flask(__name__)
firewall = FirewallEngine()
pii_engine = PIIEngine()
append_store = MerkleLogStore(os.environ.get('APPEND_LOG_PATH', 'logs_append_only.jsonl'))

LOG_SERVER_URL = os.environ.get('LOG_SERVER_URL', 'http://vigil-dashboard:3000/ingest')

# Hardening controls
MAX_REQUEST_BYTES = int(os.environ.get('MAX_REQUEST_BYTES', '1048576'))  # 1 MB default
RATE_LIMIT_RPS = float(os.environ.get('RATE_LIMIT_RPS', '5'))
REQUIRE_MTLS = os.environ.get('REQUIRE_MTLS', 'false').lower() == 'true'

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
    
    for msg in messages:
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            
            # Security Scan
            check = firewall.scan_input(content)
            if not check['safe']:
                ship_log_async({
                    "request_id": f"req_{datetime.datetime.now().timestamp()}",
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "seq_id": _seq_id,
                    "status": "BLOCKED_INPUT",
                    "agent_id": agent_id,
                    "tenant_id": "local-docker",
                    "details": {"reason": check['reason'], "redacted": False}
                })
                return jsonify({"error": {"message": f"Vigil Blocked: {check['reason']}", "code": 403}}), 403
            
            # PII Redaction
            clean_text, was_redacted = pii_engine.scan_and_redact(content)
            if was_redacted:
                msg['content'] = clean_text

            # Log Success
            ship_log_async({
                "request_id": f"req_{datetime.datetime.now().timestamp()}",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "seq_id": _seq_id,
                "status": "PROCESSED",
                "agent_id": agent_id,
                "tenant_id": "local-docker",
                "details": {"reason": "Allowed", "redacted": was_redacted}
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
