#!/usr/bin/env python3
"""
Mock AgentShield server with Priority 1 fields implementation.
This simulates the updated AgentShield backend for testing.
"""

from flask import Flask, request, jsonify
import time
import hashlib
import json
import base64

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "mock-agentshield"})

@app.route('/v1/keys/jwks', methods=['GET'])
def jwks():
    """Return mock JWKS keys."""
    return jsonify({
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "kid": "k1",
                "x": "mock-public-key-data",
                "use": "sig"
            }
        ]
    })

@app.route('/v1/enforce', methods=['POST'])
def enforce():
    """Mock enforcement endpoint with Priority 1 fields."""
    request_data = request.json
    
    # Extract request fields
    request_id = request_data.get("request_id", "unknown")
    tenant_id = request_data.get("tenant_id", "unknown")
    agent_id = request_data.get("agent_id", "unknown")
    policy_id = request_data.get("policy_id", "default-policy")
    policy_version = request_data.get("policy_version", 1)
    input_hash = request_data.get("input_hash", "")
    timestamp_ms = request_data.get("timestamp_ms", int(time.time() * 1000))
    ttl_ms = request_data.get("ttl_ms", 300000)
    environment = request_data.get("environment", "test")
    messages = request_data.get("messages", [])
    
    # Make decision (always ALLOW for testing)
    decision = {
        "schema_version": "as_decision_v1",  # ⭐ NEW
        "action": "ALLOW",
        "risk_score": 0.05,
        "reasons": ["mock-allow"],
        "issued_at": int(time.time()),
        "ttl_ms": ttl_ms,  # ⭐ NEW - Echo back or use default
        "context_echo": {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "policy_id": policy_id,  # ⭐ NEW - Echo back
            "policy_version": policy_version,
            "input_hash": input_hash,  # ⭐ NEW - Echo back (critical!)
            "timestamp_ms": timestamp_ms,
            "environment": environment
        },
        "audit_event_id": f"evt-mock-{int(time.time())}"
    }
    
    # Create canonical payload for signing
    canonical_payload = {
        "action": decision["action"],
        "risk_score": decision["risk_score"],
        "reasons": decision["reasons"],
        "context_echo": decision["context_echo"],
        "audit_event_id": decision["audit_event_id"],
        "issued_at": decision["issued_at"]
    }
    
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':'))
    payload_hash = hashlib.sha256(canonical_json.encode()).digest()
    
    # Mock signature (in real system, this would be Ed25519 signature)
    mock_signature = hashlib.sha256(f"mock-sig-{canonical_json}".encode()).digest()
    
    decision["signature"] = base64.urlsafe_b64encode(mock_signature).decode().rstrip('=')
    decision["signature_key_id"] = "k1"
    decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip('=')
    
    print(f"✅ Mock AgentShield: Processed request {request_id}")
    print(f"   - schema_version: {decision['schema_version']}")
    print(f"   - ttl_ms: {decision['ttl_ms']}")
    print(f"   - policy_id: {policy_id}")
    print(f"   - input_hash: {input_hash[:32]}...")
    
    return jsonify(decision)

if __name__ == '__main__':
    print("🛡️  Mock AgentShield running on http://0.0.0.0:9000")
    print("   (With Priority 1 fields: schema_version, ttl_ms, policy_id, input_hash)")
    app.run(host='0.0.0.0', port=9000, debug=False)
