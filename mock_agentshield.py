#!/usr/bin/env python3
"""
Mock AgentShield server upgraded with:
- Real Ed25519 signing + JWKS
- Policy loading from agentshield_policy.json
- Key rotation, decision expiry enforcement, replay protection
- TEE hooks: sealed key persistence + optional attestation gating
"""

from flask import Flask, request, jsonify
import time
import hashlib
import json
import base64
import os
from collections import defaultdict, Counter, deque
import datetime
import re
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from math import ceil

# Configuration (env overrides)
POLICY_PATH = os.environ.get("POLICY_PATH", "agentshield_policy.json")
KEY_ROTATION_SECONDS = int(os.environ.get("KEY_ROTATION_SECONDS", "86400"))  # default 24h
DECISION_TTL_MS_MAX = int(os.environ.get("DECISION_TTL_MS_MAX", "300000"))   # default 5 minutes
REPLAY_WINDOW_SECONDS = int(os.environ.get("REPLAY_WINDOW_SECONDS", "300"))   # default 5 minutes
SEAL_KEY_PATH = os.environ.get("SEAL_KEY_PATH", "/tmp/agentshield_sealed_ed25519.key")
REQUIRE_ATTESTATION = os.environ.get("REQUIRE_ATTESTATION", "false").lower() == "true"
ATTESTATION_MEASUREMENT = os.environ.get("ATTESTATION_MEASUREMENT", "")
# Optional: provide a fixed signing key (base64 raw 32 bytes) or path to raw key bytes
SIGNING_KEY_B64 = os.environ.get("AGENTSHIELD_SIGNING_KEY_B64", "")
SIGNING_KEY_PATH_OVERRIDE = os.environ.get("AGENTSHIELD_SIGNING_KEY_PATH", "")

app = Flask(__name__)
START_TIME = time.time()

def load_or_create_sealed_key(path: str):
    """Load Ed25519 private key from env/path/sealed storage or create one."""
    # Highest priority: explicit env b64 key
    if SIGNING_KEY_B64:
        try:
            raw = base64.urlsafe_b64decode(SIGNING_KEY_B64 + "=")
            return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
        except Exception:
            pass

    # Next: explicit override file path containing raw base64url or raw bytes
    if SIGNING_KEY_PATH_OVERRIDE:
        try:
            with open(SIGNING_KEY_PATH_OVERRIDE, "rb") as f:
                file_bytes = f.read().strip()
                try:
                    raw = base64.urlsafe_b64decode(file_bytes + b"=")
                except Exception:
                    raw = file_bytes
            return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
        except Exception:
            pass

    # Fallback: sealed storage path (base64url)
    try:
        if os.path.exists(path):
            with open(path, "rb") as f:
                raw = base64.urlsafe_b64decode(f.read())
            return ed25519.Ed25519PrivateKey.from_private_bytes(raw)
    except Exception:
        pass  # Fall back to new key

    key = ed25519.Ed25519PrivateKey.generate()
    try:
        raw = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(path, "wb") as f:
            f.write(base64.urlsafe_b64encode(raw))
    except Exception:
        # If sealing fails, continue with in-memory key only
        pass
    return key


def new_key_record(kid: str, private_key: ed25519.Ed25519PrivateKey):
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return {
        "kid": kid,
        "private_key": private_key,
        "public_bytes": public_bytes,
        "created_at": time.time(),
    }


# KEY RING WITH ROTATION
KEY_RING = []
LAST_ROTATION = time.time()


def initialize_keys():
    sealed_key = load_or_create_sealed_key(SEAL_KEY_PATH)
    base_kid = "k1"
    KEY_RING.clear()
    KEY_RING.append(new_key_record(base_kid, sealed_key))


def active_key():
    # Latest key in ring
    return KEY_RING[-1]


def maybe_rotate_keys():
    global LAST_ROTATION
    now = time.time()
    if now - LAST_ROTATION < KEY_ROTATION_SECONDS:
        return
    kid = f"k{int(now)}"
    KEY_RING.append(new_key_record(kid, ed25519.Ed25519PrivateKey.generate()))
    LAST_ROTATION = now
    # Cap key ring to last 5 keys
    if len(KEY_RING) > 5:
        del KEY_RING[0]


# POLICY RULES - loaded from file with safe defaults
DEFAULT_BLOCK_PATTERNS = [
    (r"(?i)system:", "prompt-injection-system", 0.9),
    (r"(?i)ignore previous", "prompt-injection-override", 0.95),
    (r"(?i)</system>", "prompt-injection-xml", 0.9),
    (r"(?i)ignore all.*instruction", "prompt-injection-instruction-override", 0.95),
    (r"\b[0-9]{13,19}\b", "credit-card-number", 0.99),
    (r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b", "ssn-pattern", 0.99),
    (r"(?i)<script>", "xss-attempt", 0.98),
    (r"(?i)DROP\s+TABLE", "sql-injection", 0.98),
    (r"(?i)exec\s*\(", "code-execution", 0.95),
]

POLICY_RULES = DEFAULT_BLOCK_PATTERNS[:]
TEE_POLICY = {
    "sgx_mrenclave": [],
    "sgx_mrsigner": [],
    "sev_measurement": [],
    "tdx_mrtd": [],
    "azure_measurement": [],
}
POLICY_VERSION = 1
POLICY_LOADED_AT = time.time()


def load_policy():
    global POLICY_RULES, POLICY_VERSION, POLICY_LOADED_AT, TEE_POLICY
    try:
        with open(POLICY_PATH, "r") as f:
            data = json.load(f)
        POLICY_RULES = []
        for rule in data.get("rules", []):
            POLICY_RULES.append(
                (
                    rule.get("pattern", ""),
                    rule.get("reason", "unspecified"),
                    float(rule.get("risk_score", 0.5)),
                )
            )
        if not POLICY_RULES:
            POLICY_RULES = DEFAULT_BLOCK_PATTERNS[:]
        # Allow env overrides for measurement allow-lists (comma-separated)
        env_overrides = {
            "sgx_mrenclave": os.getenv("AGENTSHIELD_SGX_MRENCLAVE", ""),
            "sgx_mrsigner": os.getenv("AGENTSHIELD_SGX_MRSIGNER", ""),
            "sev_measurement": os.getenv("AGENTSHIELD_SEV_MEASUREMENT", ""),
            "tdx_mrtd": os.getenv("AGENTSHIELD_TDX_MRTD", ""),
            "azure_measurement": os.getenv("AGENTSHIELD_AZURE_MEASUREMENT", ""),
        }
        def env_list(val):
            return [v.strip() for v in val.split(',') if v.strip()] if val else []
        TEE_POLICY = {
            "sgx_mrenclave": env_list(env_overrides["sgx_mrenclave"]) or data.get("sgx_mrenclave", []),
            "sgx_mrsigner": env_list(env_overrides["sgx_mrsigner"]) or data.get("sgx_mrsigner", []),
            "sev_measurement": env_list(env_overrides["sev_measurement"]) or data.get("sev_measurement", []),
            "tdx_mrtd": env_list(env_overrides["tdx_mrtd"]) or data.get("tdx_mrtd", []),
            "azure_measurement": env_list(env_overrides["azure_measurement"]) or data.get("azure_measurement", []),
        }
        POLICY_VERSION += 1
        POLICY_LOADED_AT = time.time()
    except Exception:
        POLICY_RULES = DEFAULT_BLOCK_PATTERNS[:]


def validate_attestation(measurement: str) -> bool:
    # Accept all if no expectations set
    if not any(TEE_POLICY.values()):
        return True
    allowed = set(
        TEE_POLICY.get("sgx_mrenclave", [])
        + TEE_POLICY.get("sgx_mrsigner", [])
        + TEE_POLICY.get("sev_measurement", [])
        + TEE_POLICY.get("tdx_mrtd", [])
        + TEE_POLICY.get("azure_measurement", [])
    )
    if not allowed:
        return True
    if not measurement:
        return False
    return measurement in allowed


# Initialize keyring and policy on startup
initialize_keys()
load_policy()

# Replay protection
REPLAY_CACHE = deque()
REPLAY_INDEX = {}

# In-memory analytics store (in production, use Redis/Database)
analytics_store = {
    "requests": [],
    "decisions": Counter(),
    "tenants": defaultdict(lambda: {"count": 0, "blocked": 0, "allowed": 0}),
    "agents": defaultdict(lambda: {"count": 0, "blocked": 0, "allowed": 0}),
    "risk_scores": [],
    "latencies": []
}

# Merkle accumulator for signed decision log
MERKLE_LEAVES = []  # list of bytes digests
MERKLE_LEVELS = []  # list of levels, each level is list of digests


def _build_merkle_tree():
    """Recompute full Merkle tree from leaves."""
    global MERKLE_LEVELS
    if not MERKLE_LEAVES:
        MERKLE_LEVELS = []
        return
    level = MERKLE_LEAVES[:]
    levels = [level]
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            next_level.append(hashlib.sha256(left + right).digest())
        level = next_level
        levels.append(level)
    MERKLE_LEVELS = levels


def _merkle_root_b64() -> str:
    if not MERKLE_LEVELS:
        return ""
    root = MERKLE_LEVELS[-1][0]
    return base64.urlsafe_b64encode(root).decode().rstrip('=')


def _merkle_proof(index: int):
    """Return Merkle proof (list of dicts with sibling and side)."""
    proof = []
    if index < 0 or not MERKLE_LEVELS:
        return proof
    idx = index
    for level in MERKLE_LEVELS[:-1]:
        sibling_idx = idx - 1 if idx % 2 else idx + 1
        if sibling_idx >= len(level):
            sibling = level[idx]
        else:
            sibling = level[sibling_idx]
        proof.append({
            "sibling": base64.urlsafe_b64encode(sibling).decode().rstrip('='),
            "side": "left" if sibling_idx < idx else "right"
        })
        idx = idx // 2
    return proof


def evaluate_threat(messages):
    """
    Evaluate messages for threats using pattern matching.
    Returns (action, risk_score, reasons)
    """
    all_text = " ".join([msg.get("content", "") for msg in messages if isinstance(msg, dict)])
    
    reasons = []
    max_risk_score = 0.0
    
    for pattern, reason, risk_score in POLICY_RULES:
        if pattern and re.search(pattern, all_text):
            reasons.append(reason)
            max_risk_score = max(max_risk_score, risk_score)
    
    # Decision logic
    if max_risk_score >= 0.8:
        return "BLOCK", max_risk_score, reasons
    elif max_risk_score >= 0.5:
        return "SANITIZE", max_risk_score, reasons
    else:
        return "ALLOW", max(max_risk_score, 0.05), reasons if reasons else ["clean"]


def purge_replay_cache(now: float):
    while REPLAY_CACHE and now - REPLAY_CACHE[0][1] > REPLAY_WINDOW_SECONDS:
        req_id, _ts = REPLAY_CACHE.popleft()
        REPLAY_INDEX.pop(req_id, None)


def is_replay(request_id: str, now: float) -> bool:
    if not request_id:
        return False
    purge_replay_cache(now)
    ts = REPLAY_INDEX.get(request_id)
    if ts and now - ts <= REPLAY_WINDOW_SECONDS:
        return True
    REPLAY_CACHE.append((request_id, now))
    REPLAY_INDEX[request_id] = now
    if len(REPLAY_CACHE) > 10000:
        old_id, _ = REPLAY_CACHE.popleft()
        REPLAY_INDEX.pop(old_id, None)
    return False

@app.route('/health', methods=['GET'])
def health():
    uptime = round(time.time() - START_TIME, 2)
    attestation_ok = validate_attestation(ATTESTATION_MEASUREMENT)
    ak = active_key()
    return jsonify({
        "status": "ok",
        "service": "mock-agentshield",
        "uptime_seconds": uptime,
        "decision_signing": {
            "schema_version": "as_decision_v1",
            "key_id": ak["kid"],
            "ready": True,
            "rotation_seconds": KEY_ROTATION_SECONDS,
            "keys_available": len(KEY_RING)
        },
        "policy": {
            "version": POLICY_VERSION,
            "loaded_at": POLICY_LOADED_AT,
            "rule_count": len(POLICY_RULES)
        },
        "replay_protection": {
            "window_seconds": REPLAY_WINDOW_SECONDS,
            "cache_size": len(REPLAY_CACHE)
        },
        "attestation": {
            "required": REQUIRE_ATTESTATION,
            "measurement": ATTESTATION_MEASUREMENT,
            "verified": attestation_ok
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    })

@app.route('/v1/keys/jwks', methods=['GET'])
def jwks():
    """Return REAL JWKS keys with Ed25519 public keys (all active keys)."""
    keys = []
    for record in KEY_RING:
        x_coord = base64.urlsafe_b64encode(record["public_bytes"]).decode().rstrip('=')
        keys.append({
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": record["kid"],
            "x": x_coord,
            "use": "sig"
        })
    return jsonify({"keys": keys})

@app.route('/v1/enforce', methods=['POST'])
def enforce():
    """Enforcement endpoint with REAL Ed25519 signing and policy evaluation."""
    request_data = request.json
    now = time.time()
    maybe_rotate_keys()
    attestation_ok = validate_attestation(ATTESTATION_MEASUREMENT)
    if REQUIRE_ATTESTATION and not attestation_ok:
        return jsonify({
            "error": "attestation_failed",
            "message": "Attestation not verified; refusing to issue decisions"
        }), 503
    
    # Extract request fields
    request_id = request_data.get("request_id", "unknown")
    tenant_id = request_data.get("tenant_id", "unknown")
    agent_id = request_data.get("agent_id", "unknown")
    policy_id = request_data.get("policy_id", "default-policy")
    policy_version = request_data.get("policy_version", POLICY_VERSION)
    input_hash = request_data.get("input_hash", "")
    timestamp_ms = request_data.get("timestamp_ms", int(time.time() * 1000))
    ttl_ms = min(int(request_data.get("ttl_ms", 300000)), DECISION_TTL_MS_MAX)
    environment = request_data.get("environment", "test")
    messages = request_data.get("messages", [])
    expires_at_ms = int(now * 1000) + ttl_ms

    # Replay protection
    if is_replay(request_id, now):
        return jsonify({
            "error": "replay_detected",
            "message": "Duplicate request_id within replay window",
            "replay_window_seconds": REPLAY_WINDOW_SECONDS
        }), 409
    
    # 🛡️ EVALUATE THREAT using policy rules
    action, risk_score, reasons = evaluate_threat(messages)
    
    # Make decision
    decision = {
        "schema_version": "as_decision_v1",
        "action": action,  # Now can be BLOCK, SANITIZE, or ALLOW
        "risk_score": risk_score,
        "reasons": reasons,
        "issued_at": int(now),
        "ttl_ms": ttl_ms,
        "expires_at_ms": expires_at_ms,
        "context_echo": {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "input_hash": input_hash,
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
        "issued_at": decision["issued_at"],
        "expires_at_ms": decision["expires_at_ms"],
    }
    
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':'))
    payload_hash = hashlib.sha256(canonical_json.encode()).digest()
    
    # 🔐 REAL Ed25519 SIGNATURE
    ak = active_key()
    signature_bytes = ak["private_key"].sign(canonical_json.encode())
    
    decision["signature"] = base64.urlsafe_b64encode(signature_bytes).decode().rstrip('=')
    decision["signature_key_id"] = ak["kid"]
    decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip('=')

    # 📦 Merkle accumulation
    leaf = payload_hash
    MERKLE_LEAVES.append(leaf)
    _build_merkle_tree()
    decision["merkle_root"] = _merkle_root_b64()
    decision["merkle_proof"] = _merkle_proof(len(MERKLE_LEAVES) - 1)
    
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
    
    # Track blocked/allowed per tenant
    if action == "BLOCK":
        analytics_store["tenants"][tenant_id]["blocked"] += 1
    else:
        analytics_store["tenants"][tenant_id]["allowed"] += 1
    
    analytics_store["agents"][agent_id]["count"] += 1
    
    # Track blocked/allowed per agent
    if action == "BLOCK":
        analytics_store["agents"][agent_id]["blocked"] += 1
    else:
        analytics_store["agents"][agent_id]["allowed"] += 1
    
    analytics_store["risk_scores"].append(decision["risk_score"])
    
    # Keep only last 1000 requests in memory
    if len(analytics_store["requests"]) > 1000:
        analytics_store["requests"] = analytics_store["requests"][-1000:]
    if len(analytics_store["risk_scores"]) > 1000:
        analytics_store["risk_scores"] = analytics_store["risk_scores"][-1000:]
    
    print(f"{'🛡️' if action == 'BLOCK' else '✅'} Mock AgentShield: {action} request {request_id}")
    print(f"   - Risk Score: {risk_score}")
    print(f"   - Reasons: {', '.join(reasons)}")
    print(f"   - Policy: {policy_id} v{policy_version}")
    print(f"   - TTL(ms): {ttl_ms} (expires_at_ms={expires_at_ms})")
    if REQUIRE_ATTESTATION:
        print(f"   - Attestation verified: {attestation_ok}")
    
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


@app.route('/v1/merkle/root', methods=['GET'])
def merkle_root():
    return jsonify({
        "root": _merkle_root_b64(),
        "leaves": len(MERKLE_LEAVES),
        "levels": len(MERKLE_LEVELS)
    })

if __name__ == '__main__':
    print("🛡️  Mock AgentShield running on http://0.0.0.0:9000")
    print("   WITH REAL Ed25519 SIGNING + POLICY ENFORCEMENT + ROTATION")
    print("")
    print("📋 Policy Rules Loaded:")
    for pattern, reason, risk_score in POLICY_RULES:
        print(f"   - {reason} (risk: {risk_score})")
    print("")
    print("🔐 Crypto:")
    ak = active_key()
    print(f"   - Active key: {ak['kid']} (rotates every {KEY_ROTATION_SECONDS}s)")
    print("")
    print("📊 Analytics Endpoints:")
    print("   GET  /analytics/dashboard  - Comprehensive dashboard data")
    print("   GET  /analytics/metrics    - Prometheus metrics")
    print("   GET  /analytics/logs       - Audit logs (with filters)")
    print("   GET  /analytics/threats    - High-risk requests")
    print("")
    app.run(host='0.0.0.0', port=9000, debug=False)
