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
import os
from collections import defaultdict, Counter
import datetime

app = Flask(__name__)
START_TIME = time.time()

# In-memory analytics store (in production, use Redis/Database)
analytics_store = {
    "requests": [],
    "decisions": Counter(),
    "tenants": defaultdict(lambda: {"count": 0, "blocked": 0, "allowed": 0}),
    "agents": defaultdict(lambda: {"count": 0, "blocked": 0, "allowed": 0}),
    "risk_scores": [],
    "latencies": []
}

@app.route('/health', methods=['GET'])
def health():
    uptime = round(time.time() - START_TIME, 2)
    return jsonify({
        "status": "ok",
        "service": "mock-agentshield",
        "uptime_seconds": uptime,
        "decision_signing": {
            "schema_version": "as_decision_v1",
            "key_id": "k1",
            "ready": True
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    })

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
    
    # Store analytics data
    analytics_store["requests"].append({
        "timestamp": time.time(),
        "request_id": request_id,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "action": decision["action"],
        "risk_score": decision["risk_score"]
    })
    analytics_store["decisions"][decision["action"]] += 1
    analytics_store["tenants"][tenant_id]["count"] += 1
    analytics_store["tenants"][tenant_id][decision["action"].lower()] += 1
    analytics_store["agents"][agent_id]["count"] += 1
    analytics_store["agents"][agent_id][decision["action"].lower()] += 1
    analytics_store["risk_scores"].append(decision["risk_score"])
    
    # Keep only last 1000 requests in memory
    if len(analytics_store["requests"]) > 1000:
        analytics_store["requests"] = analytics_store["requests"][-1000:]
    if len(analytics_store["risk_scores"]) > 1000:
        analytics_store["risk_scores"] = analytics_store["risk_scores"][-1000:]
    
    print(f"✅ Mock AgentShield: Processed request {request_id}")
    print(f"   - schema_version: {decision['schema_version']}")
    print(f"   - ttl_ms: {decision['ttl_ms']}")
    print(f"   - policy_id: {policy_id}")
    print(f"   - input_hash: {input_hash[:32]}...")
    
    return jsonify(decision)

@app.route('/analytics/dashboard', methods=['GET'])
def analytics_dashboard():
    """Return comprehensive analytics dashboard data."""
    total_requests = len(analytics_store["requests"])
    recent_requests = analytics_store["requests"][-100:]  # Last 100
    
    # Calculate statistics
    risk_scores = analytics_store["risk_scores"]
    avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
    max_risk = max(risk_scores) if risk_scores else 0
    
    # Time-based metrics (last hour)
    one_hour_ago = time.time() - 3600
    recent_hour = [r for r in analytics_store["requests"] if r["timestamp"] > one_hour_ago]
    
    return jsonify({
        "summary": {
            "total_requests": total_requests,
            "requests_last_hour": len(recent_hour),
            "decisions": dict(analytics_store["decisions"]),
            "avg_risk_score": round(avg_risk, 3),
            "max_risk_score": round(max_risk, 3)
        },
        "by_tenant": dict(analytics_store["tenants"]),
        "by_agent": dict(analytics_store["agents"]),
        "recent_requests": recent_requests,
        "timestamp": datetime.datetime.utcnow().isoformat()
    })

@app.route('/analytics/metrics', methods=['GET'])
def analytics_metrics():
    """Return Prometheus-style metrics."""
    metrics = []
    
    # Decision counters
    for action, count in analytics_store["decisions"].items():
        metrics.append(f'agentshield_decisions_total{{action="{action}"}} {count}')
    
    # Tenant metrics
    for tenant_id, stats in analytics_store["tenants"].items():
        metrics.append(f'agentshield_tenant_requests_total{{tenant="{tenant_id}"}} {stats["count"]}')
        metrics.append(f'agentshield_tenant_blocks_total{{tenant="{tenant_id}"}} {stats.get("blocked", 0)}')
    
    # Risk score stats
    if analytics_store["risk_scores"]:
        avg_risk = sum(analytics_store["risk_scores"]) / len(analytics_store["risk_scores"])
        max_risk = max(analytics_store["risk_scores"])
        metrics.append(f'agentshield_risk_score_avg {avg_risk:.3f}')
        metrics.append(f'agentshield_risk_score_max {max_risk:.3f}')
    
    metrics.append(f'agentshield_requests_total {len(analytics_store["requests"])}')
    
    return '\n'.join(metrics) + '\n', 200, {'Content-Type': 'text/plain'}

@app.route('/analytics/logs', methods=['GET'])
def analytics_logs():
    """Return audit logs with filtering."""
    tenant_id = request.args.get('tenant_id')
    agent_id = request.args.get('agent_id')
    limit = int(request.args.get('limit', 100))
    
    logs = analytics_store["requests"][-limit:]
    
    # Apply filters
    if tenant_id:
        logs = [r for r in logs if r["tenant_id"] == tenant_id]
    if agent_id:
        logs = [r for r in logs if r["agent_id"] == agent_id]
    
    return jsonify({
        "logs": logs,
        "count": len(logs),
        "total_in_store": len(analytics_store["requests"])
    })

@app.route('/analytics/threats', methods=['GET'])
def analytics_threats():
    """Return threat analysis - high risk score requests."""
    threshold = float(request.args.get('threshold', 0.5))
    
    threats = [
        r for r in analytics_store["requests"]
        if r.get("risk_score", 0) > threshold
    ]
    
    # Group by tenant
    threats_by_tenant = defaultdict(list)
    for threat in threats:
        threats_by_tenant[threat["tenant_id"]].append(threat)
    
    return jsonify({
        "threshold": threshold,
        "total_threats": len(threats),
        "threats": threats[-50:],  # Last 50 threats
        "by_tenant": {k: len(v) for k, v in threats_by_tenant.items()}
    })

if __name__ == '__main__':
    print("🛡️  Mock AgentShield running on http://0.0.0.0:9000")
    print("   (With Priority 1 fields: schema_version, ttl_ms, policy_id, input_hash)")
    print("")
    print("📊 Analytics Endpoints:")
    print("   GET  /analytics/dashboard  - Comprehensive dashboard data")
    print("   GET  /analytics/metrics    - Prometheus metrics")
    print("   GET  /analytics/logs       - Audit logs (with filters)")
    print("   GET  /analytics/threats    - High-risk requests")
    print("")
    app.run(host='0.0.0.0', port=9000, debug=False)
