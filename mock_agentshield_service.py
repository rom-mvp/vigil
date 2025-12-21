#!/usr/bin/env python3
"""
Mock AgentShield Service
Provides Ed25519 signing for Vigil testing without full TEE setup
"""

from flask import Flask, request, jsonify
import hashlib
import time
import json
from datetime import datetime

app = Flask(__name__)

# Mock Ed25519 key (for testing only)
MOCK_PRIVATE_KEY = "mock_ed25519_private_key_for_testing_only"
MOCK_PUBLIC_KEY = "mock_ed25519_public_key_for_testing_verification"

def generate_mock_signature(payload: str) -> str:
    """Generate a mock Ed25519 signature"""
    # In production, this would use actual Ed25519 signing
    # For testing, we create a deterministic hash-based signature
    signature_data = f"{payload}{MOCK_PRIVATE_KEY}{time.time()}"
    signature = hashlib.sha256(signature_data.encode()).hexdigest()
    return f"ed25519_{signature[:64]}"

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'service': 'mock-agentshield',
        'version': '1.0.0'
    }), 200

@app.route('/api/v1/sign', methods=['POST'])
def sign_request():
    """Sign a request payload"""
    try:
        data = request.get_json()
        
        # Extract payload
        payload = data.get('payload', '')
        agent_id = request.headers.get('X-Agent-ID', 'unknown')
        
        # Generate signature
        signature = generate_mock_signature(payload)
        
        # Mock decision (always ALLOW for testing, real AgentShield would evaluate)
        decision = data.get('decision', 'ALLOW')
        
        response = {
            'signature': signature,
            'decision': decision,
            'public_key': MOCK_PUBLIC_KEY,
            'timestamp': datetime.utcnow().isoformat(),
            'agent_id': agent_id,
            'audit_id': f"audit_{hashlib.md5(payload.encode()).hexdigest()[:16]}"
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/v1/verify', methods=['POST'])
def verify_signature():
    """Verify a signature"""
    try:
        data = request.get_json()
        signature = data.get('signature', '')
        payload = data.get('payload', '')
        
        # Mock verification (always valid for testing)
        is_valid = signature.startswith('ed25519_')
        
        return jsonify({
            'valid': is_valid,
            'public_key': MOCK_PUBLIC_KEY,
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/v1/attestation', methods=['POST'])
def get_attestation():
    """Provide mock TEE attestation"""
    return jsonify({
        'attestation': 'mock_tee_attestation_report',
        'enclave_id': 'mock_enclave_sgx',
        'measurement': hashlib.sha256(b'mock_measurement').hexdigest(),
        'timestamp': datetime.utcnow().isoformat()
    }), 200

if __name__ == '__main__':
    print("🛡️  Starting Mock AgentShield Service on port 5000...")
    print("   Health: http://localhost:5000/health")
    print("   Sign:   POST /api/v1/sign")
    print("   Verify: POST /api/v1/verify")
    print("   TEE:    POST /api/v1/attestation")
    print("")
    app.run(host='0.0.0.0', port=5000, debug=False)
