#!/usr/bin/env python3
"""
Vigil Live Test Server - Simplified version for testing
"""
from flask import Flask, request, jsonify
import re
import redis
import json
import time
from datetime import datetime

app = Flask(__name__)

# Connect to Redis
try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    redis_client.ping()
    print("✓ Connected to Redis")
except Exception as e:
    print(f"⚠ Redis not available: {e}")
    redis_client = None

# Attack detection patterns
THREAT_PATTERNS = {
    "prompt_injection": {
        "patterns": [
            r"ignore\s+(all\s+)?previous\s+instructions?",
            r"disregard\s+(the\s+)?above",
            r"forget\s+(?:everything|previous|all).*(?:instructions?|rules?|prompts?)",
            r"system\s+prompt",
            r"repeat\s+(?:your|the)\s+(?:instructions?|system\s+prompt)",
            r"what\s+(?:are|is)\s+your\s+(?:instructions?|rules?|system\s+prompt)",
            r"new\s+instructions?:\s*\w+",
            r"actually,?\s*(?:disregard|ignore)",
            r"\|\|\|.*override.*\|\|\|",
        ],
        "score": 0.95,
        "category": "prompt_injection"
    },
    "jailbreak": {
        "patterns": [
            r"\bdan\s+mode\b",
            r"\bdo\s+anything\s+now\b",
            r"\bdeveloper\s+mode\b",
            r"(?:you\s+have\s+)?no\s+(?:ethical\s+)?(?:restrictions?|guidelines|constraints|rules)",
            r"\bunrestricted(?:\s+ai)?\b",
            r"\bjailbreak\b",
            r"pretend\s+(?:you\s+are|to\s+be)\s+(?:an?\s+)?(?:unfiltered|unrestricted)",
            r"(?:chaos|evil|devil)gpt",
        ],
        "score": 0.98,
        "category": "jailbreak"
    },
    "credential_exfil": {
        "patterns": [
            r"\bapi[_\s]?key\b",
            r"\bsk-[a-zA-Z0-9]{20,}",
            r"\bsecret[_\s]?key\b",
            r"\bpassword\b.*(?:is|:|=)",
            r"(?:dump|reveal|show).*(?:keys?|secrets?|credentials?)",
            r"\baccess[_\s]?token\b",
        ],
        "score": 0.92,
        "category": "credential_exfil"
    },
    "code_injection": {
        "patterns": [
            r"(?:drop|delete\s+from|truncate)\s+table",
            r";\s*drop\s+table",
            r"'\s*or\s+'1'\s*=\s*'1",
            r"';?\s*--",
            r"(?:rm\s+-rf|del\s+/|format\s+c:)",
            r"\.\./\.\./\.\./",
            r"(?:/etc/passwd|/etc/shadow)",
            r"<script[^>]*>.*</script>",
            r"javascript\s*:",
        ],
        "score": 0.90,
        "category": "code_injection"
    },
    "pii": {
        "patterns": [
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN only
            r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",  # credit card
            r"(?:ssn|social\s+security).*\b\d{3}-\d{2}-\d{4}\b",
            r"(?:credit\s+card|cvv).*\d{4}",
        ],
        "score": 0.85,  # Changed from 0.0 to block PII
        "category": "pii_detected"
    },
    "encoding_evasion": {
        "patterns": [
            r"\\x[0-9a-f]{2}(?:\\x[0-9a-f]{2}){3,}",  # Multiple hex encodings
            r"(?:base64|b64).*(?:decode|eval)",
            r"eval\s*\(",
        ],
        "score": 0.88,
        "category": "encoding_evasion"
    },
    "dangerous_commands": {
        "patterns": [
            r"(?:authorize|transfer|send).*\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?",
            r"(?:grant|give|provide).*(?:admin|administrator|root)\s+(?:privileges|access)",
            r"(?:execute|run)\s+sudo",
            r"\bmake\s+(?:thermite|explosives?|bombs?)\b",
            r"(?:build|create)\s+(?:a\s+)?bombs?",
            r"(?:hacking|hack)\s+tools?",
        ],
        "score": 0.93,
        "category": "dangerous_commands"
    },
    "aws_credential_leak": {
        "patterns": [
            r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID format
            r"AWS_ACCESS_KEY_ID",
            r"AWS_SECRET_ACCESS_KEY",
            r"aws_secret_access_key",
            r"(?:aws|amazon).*(?:key|secret|credential)",
        ],
        "score": 0.95,
        "category": "aws_credential_leak"
    },
    "middleware_bypass_attempt": {
        "patterns": [
            r"X-Forwarded-Host",
            r"X-Original-URL",
            r"X-Rewrite-URL",
            r"X-Middleware-Override",
            r"middleware\s+bypass",
            r"bypass.*(?:auth|security|middleware)",
        ],
        "score": 0.90,
        "category": "middleware_bypass_attempt"
    },
}

def check_threat(text):
    """Check text for threats"""
    text_lower = text.lower()
    
    max_score = 0.0
    threat_type = None
    reasons = []
    detected_patterns = []
    pii_found = []
    
    for category, config in THREAT_PATTERNS.items():
        for pattern in config["patterns"]:
            if re.search(pattern, text_lower, re.IGNORECASE):
                if config["score"] > max_score:
                    max_score with improved accuracy"""
    text_lower = text.lower()
    
    max_score = 0.0
    threat_type = None
    reasons = []
    detected_patterns = []
    pii_found = []
    
    for category, config in THREAT_PATTERNS.items():
        for pattern in config["patterns"]:
            matches = re.search(pattern, text_lower, re.IGNORECASE)
            if matches:
                if config["score"] > max_score:
                    max_score = config["score"]
                    threat_type = category
                reasons.append(f"{category}: '{pattern}'")
                detected_patterns.append(pattern)
                
                if category == "pii":
                    pii_found.append(pattern)
    
    # Improved blocking logic: require higher threshold for blocking
    blocked = max_score >= 0.85
    
    return {
        "risk_score": max_score,
        "threat_type": threat_type,
        "blocked": blocked
@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """Main LLM proxy endpoint"""
    try:
        data = request.get_json()
        messages = data.get('messages', [])
        
        # Extract user prompt
        user_prompt = ""
        for msg in messages:
            if msg.get('role') == 'user':
                user_prompt = msg.get('content', '')
                break
        
        # Also check HTTP headers for middleware bypass attempts
        headers_to_check = str(request.headers)
        full_content_to_check = user_prompt + "\n" + headers_to_check
        
        # Check for threats in both payload and headers
        threat_result = check_threat(full_content_to_check)
        
        # Log the request
        log_entry = {
            "timestamp": threat_result["timestamp"],
            "prompt": user_prompt[:200],  # truncate
            "risk_score": threat_result["risk_score"],
            "threat_type": threat_result["threat_type"],
            "blocked": threat_result["blocked"],
            "reasons": threat_result["reasons"],
        }
        attack_logs.append(log_entry)
        
        # Store in Redis if available
        if redis_client:
            try:
                redis_client.lpush("vigil:attack_logs", json.dumps(log_entry))
                redis_client.ltrim("vigil:attack_logs", 0, 999)  # Keep last 1000
            except:
                pass
        
        if threat_result["blocked"]:
            return jsonify({
                "error": {
                    "message": "Request blocked by Vigil security",
                    "type": "security_violation",
                    "risk_score": threat_result["risk_score"],
                    "threat_type": threat_result["threat_type"],
                    "reasons": threat_result["reasons"]
                }
            }), 403
        
        # If allowed, return mock success
        return jsonify({
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "gpt-3.5-turbo",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from Vigil Gateway."
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            },
            "vigil_metadata": {
                "risk_score": threat_result["risk_score"],
                "pii_detected": threat_result["pii_detected"]
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/attack-logs', methods=['GET'])
def get_attack_logs():
    """Get recent attack logs"""
    return jsonify({"logs": attack_logs[-100:]})  # Last 100

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics"""
    total = len(attack_logs)
    blocked = sum(1 for log in attack_logs if log.get('blocked'))
    allowed = total - blocked
    
    threat_counts = {}
    for log in attack_logs:
        tt = log.get('threat_type', 'none')
        threat_counts[tt] = threat_counts.get(tt, 0) + 1
    
    return jsonify({
        "total_requests": total,
        "blocked": blocked,
        "allowed": allowed,
        "block_rate": (blocked / total * 100) if total > 0 else 0,
        "threat_breakdown": threat_counts
    })

if __name__ == '__main__':
    print("=" * 60)
    print("🛡️  Vigil Test Gateway Starting")
    print("=" * 60)
    print("Port: 8000")
    print("Endpoints:")
    print("  - POST /v1/chat/completions (LLM proxy)")
    print("  - GET  /health (health check)")
    print("  - GET  /api/attack-logs (view logs)")
    print("  - GET  /api/stats (statistics)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8000, debug=False)
