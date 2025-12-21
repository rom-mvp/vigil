#!/usr/bin/env python3
"""
Simple Vigil test server for attack testing
"""
from flask import Flask, request, jsonify
import redis
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from vigil.guardrails import GuardrailsEngine
from vigil.api_key_auth import APIKeyAuth

app = Flask(__name__)

# Initialize components
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
api_key_auth = APIKeyAuth(redis_url=redis_url)
guardrails = GuardrailsEngine()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "vigil-test"}), 200

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """Process chat completion with security checks"""
    
    # 1. Extract API key
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Missing API key"}), 401
    
    api_key = auth_header.replace('Bearer ', '')
    
    # 2. Validate API key
    tenant_id, metadata = api_key_auth.validate_key(api_key)
    if not tenant_id:
        return jsonify({"error": "Invalid API key"}), 401
    
    # 3. Get request data
    data = request.json
    messages = data.get('messages', [])
    
    if not messages:
        return jsonify({"error": "No messages provided"}), 400
    
    # 4. Extract user content
    user_content = ""
    for msg in messages:
        if msg.get('role') == 'user':
            user_content = msg.get('content', '')
            break
    
    # 5. Run security checks
    try:
        result = guardrails.check_prompt(user_content, tenant_id=tenant_id)
        
        # 6. Check if blocked
        if result.get('action') == 'block' or result.get('should_block', False):
            return jsonify({
                "error": "Request blocked by security policy",
                "reason": "Potential security threat detected",
                "action": "block",
                "threat_detected": True,
                "threat_type": result.get('threat_type', 'unknown'),
                "risk_score": result.get('risk_score', 0.0),
                "details": result.get('reason', 'Security violation'),
                "tenant_id": tenant_id
            }), 403
        
        # 7. If allowed, return success (in real system would forward to LLM)
        return jsonify({
            "action": "allow",
            "threat_detected": False,
            "risk_score": result.get('risk_score', 0.0),
            "pii_redacted": result.get('pii_redacted', False),
            "normalized": result.get('normalized', False),
            "tenant_id": tenant_id,
            "message": "Request would be forwarded to LLM (mock response)",
            "security_checks": {
                "vector_scan": result.get('vector_scan_result', {}),
                "normalization": result.get('normalization_applied', False),
                "pii_detection": result.get('pii_detected', False)
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "error": "Security check failed",
            "details": str(e)
        }), 500

if __name__ == '__main__':
    print("Starting Vigil Test Server on http://0.0.0.0:8000")
    print("Ready for attack testing!")
    app.run(host='0.0.0.0', port=8000, debug=False)
