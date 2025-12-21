#!/usr/bin/env python3
"""
Vigil Enhanced Test Server with Full Threat Detection
Complete server with all security layers and AgentShield integration
"""

import sys
sys.path.insert(0, 'src')

from flask import Flask, request, jsonify
import json
import time
import os
import requests
import re
from vigil.advanced_threat_detector import AdvancedThreatDetector
from vigil.security_framework import SecurityFramework
from vigil.api_key_auth import APIKeyAuth
from vigil.pii_engine import PIIEngine
from vigil.firewall_engine import FirewallEngine

app = Flask(__name__)

# Get AgentShield URL from environment
AGENTSHIELD_URL = os.environ.get('AGENTSHIELD_URL', 'http://localhost:5000')

# Initialize ALL security components
detector = AdvancedThreatDetector()
framework = SecurityFramework()
api_auth = APIKeyAuth()
pii_engine = PIIEngine()
firewall = FirewallEngine()

print(f"🛡️  Vigil Enhanced Server Starting...")
print(f"   AgentShield URL: {AGENTSHIELD_URL}")
print(f"   Threat Detector: Initialized")
print(f"   Security Framework: Initialized")
print(f"   PII Engine: Initialized")
print(f"   Firewall Engine: Initialized")

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'server': 'vigil-test'}), 200


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """OpenAI-compatible endpoint with FULL threat detection"""
    
    # Check API key
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid authorization'}), 401
    
    api_key = auth_header.replace('Bearer ', '').strip()
    
    # Validate API key (skip validation for testing)
    # if not api_auth.validate_key(api_key):
    #     return jsonify({'error': 'Invalid API key'}), 401
    
    # Get request data
    data = request.get_json()
    if not data or 'messages' not in data:
        return jsonify({'error': 'Invalid request format'}), 400
    
    # Extract user message
    messages = data.get('messages', [])
    user_message = ''
    for msg in messages:
        if msg.get('role') == 'user':
            user_message = msg.get('content', '')
            break
    
    # Also check if message is nested in JSON
    if not user_message and isinstance(data, dict):
        # Check for nested injection patterns
        user_message = json.dumps(data)
    
    if not user_message:
        return jsonify({'error': 'No user message found'}), 400
    
    start_time = time.time()
    
    # LAYER 1: PII Detection (fast check for sensitive data)
    try:
        redacted_text, contains_pii = pii_engine.scan_and_redact(user_message)
        if contains_pii:
            signature = _get_agentshield_signature(user_message, 'BLOCK', 'PII_DETECTED')
            return jsonify({
                'error': 'PII detected in request',
                'threat_detected': 'PII_LEAK',
                'confidence': 0.95,
                'latency_ms': round((time.time() - start_time) * 1000, 2),
                'vigil_decision': 'BLOCK',
                'ed25519_signature': signature
            }), 403
    except Exception as e:
        print(f"⚠️  PII check failed: {e}")
    
    # LAYER 2: Firewall rules (fast pattern matching)
    firewall_result = firewall.scan_input(user_message)
    if not firewall_result.get('safe', True):
        signature = _get_agentshield_signature(user_message, 'BLOCK', 'FIREWALL_RULE')
        return jsonify({
            'error': 'Firewall rule violation',
            'threat_detected': 'FIREWALL_BLOCK',
            'reason': firewall_result.get('reason', 'BLOCKED'),
            'confidence': 0.90,
            'latency_ms': round((time.time() - start_time) * 1000, 2),
            'vigil_decision': 'BLOCK',
            'ed25519_signature': signature
        }), 403
    
    # LAYER 3: Advanced threat detection (comprehensive analysis)
    threat_result = detector.detect_threat(user_message)
    
    if threat_result['is_threat']:
        signature = _get_agentshield_signature(user_message, 'BLOCK', threat_result['threat_type'])
        latency_ms = (time.time() - start_time) * 1000
        return jsonify({
            'error': 'Request blocked by security policy',
            'threat_detected': threat_result['threat_type'],
            'confidence': threat_result['confidence'],
            'details': threat_result['details'],
            'latency_ms': round(latency_ms, 2),
            'vigil_decision': 'BLOCK',
            'ed25519_signature': signature
        }), 403
    
    # LAYER 4: Security framework analysis (for additional checks)
    framework_result = framework.analyze_request(user_message, context={'api_key': api_key})
    
    if framework_result['action'] == 'BLOCK':
        signature = _get_agentshield_signature(user_message, 'BLOCK', framework_result['threat_detected'])
        latency_ms = (time.time() - start_time) * 1000
        return jsonify({
            'error': 'Request blocked by security framework',
            'threat_detected': framework_result['threat_detected'],
            'risk_score': framework_result['risk_score'],
            'confidence': framework_result['confidence'],
            'latency_ms': round(latency_ms, 2),
            'vigil_decision': 'BLOCK',
            'ed25519_signature': signature
        }), 403
    
    latency_ms = (time.time() - start_time) * 1000
    
    # Allow - return mock response with signature
    signature = _get_agentshield_signature(user_message, 'ALLOW', None, framework_result['risk_score'])
    
    return jsonify({
        'id': f'chatcmpl-{int(time.time())}',
        'object': 'chat.completion',
        'created': int(time.time()),
        'model': data.get('model', 'gpt-4'),
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': 'This is a mock response from Vigil Enhanced Server. Your request passed all security checks.'
            },
            'finish_reason': 'stop'
        }],
        'usage': {
            'prompt_tokens': len(user_message.split()),
            'completion_tokens': 10,
            'total_tokens': len(user_message.split()) + 10
        },
        'vigil_decision': 'ALLOW',
        'ed25519_signature': signature,
        'latency_ms': round(latency_ms, 2)
    }), 200

def _get_agentshield_signature(payload: str, decision: str, threat_type: str = None, risk_score: float = 0.0) -> str:
    """Helper to get Ed25519 signature from AgentShield"""
    try:
        response = requests.post(
            f'{AGENTSHIELD_URL}/api/v1/sign',
            json={
                'payload': payload,
                'decision': decision,
                'threat_type': threat_type,
                'risk_score': risk_score
            },
            timeout=2
        )
        if response.status_code == 200:
            return response.json().get('signature')
    except Exception as e:
        print(f"⚠️  AgentShield signing failed: {e}")
    return None

@app.route('/api/v1/audit/logs', methods=['GET'])
def get_audit_logs():
    """Return audit logs"""
    logs = framework.attack_log[-50:]  # Last 50 logs
    return jsonify({'logs': logs, 'count': len(logs)}), 200

if __name__ == '__main__':
    print("🚀 Starting Vigil Test Server on port 8000...")
    print("   Health check: http://localhost:8000/health")
    print("   Endpoint: POST /v1/chat/completions")
    print("")
    app.run(host='0.0.0.0', port=8000, debug=False)
