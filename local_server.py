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

app = Flask(__name__)
firewall = FirewallEngine()
pii_engine = PIIEngine()

LOG_SERVER_URL = os.environ.get('LOG_SERVER_URL', 'http://vigil-dashboard:3000/ingest')

def ship_log_async(payload):
    def _send():
        try:
            requests.post(LOG_SERVER_URL, json=payload, timeout=1)
        except:
            pass 
    threading.Thread(target=_send).start()

@app.route('/v1/chat/completions', methods=['POST'])
def transparent_proxy():
    user_api_key = request.headers.get("Authorization")
    body = request.json or {}
    messages = body.get('messages', [])
    agent_id = request.headers.get("X-Agent-ID", "anonymous-agent")
    
    for msg in messages:
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            
            # Security Scan
            check = firewall.scan_input(content)
            if not check['safe']:
                ship_log_async({
                    "request_id": f"req_{datetime.datetime.now().timestamp()}",
                    "timestamp": datetime.datetime.utcnow().isoformat(),
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
