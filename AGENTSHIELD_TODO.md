# 🚨 AgentShield Backend Action Items

## Overview

Vigil dashboard and audit system is **100% complete**. The AgentShield backend needs to verify it's providing all required fields in its decision responses.

---

## ✅ What AgentShield MUST Provide

### 1. POST /v1/enforce Request (What Vigil Sends)

**Updated Request Format:**

```json
{
  "request_id": "req-uuid-12345",
  "tenant_id": "ent-tenant",
  "agent_id": "ent-agent",
  "policy_id": "policy-abc",                      // ⚠️ NEW FIELD
  "policy_version": "v2",
  "environment": "production",
  "timestamp_ms": 1710000000000,                  // ⚠️ milliseconds
  "ttl_ms": 300000,                               // ⚠️ NEW FIELD (5 minutes)
  "input_hash": "sha256-hash-of-request",         // ⚠️ NEW FIELD (critical)
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "metadata": {}
}
```

### 2. POST /v1/enforce Response (What AgentShield Returns)

**Updated Response Format:**

```json
{
  "schema_version": "as_decision_v1",             // ⚠️ NEW FIELD
  "action": "ALLOW",                              // ✅ EXISTS
  "risk_score": 0.12,                             // ✅ EXISTS
  "reasons": ["stub-allow"],                      // ✅ EXISTS
  "signature": "base64-ed25519-sig",              // ✅ EXISTS
  "signature_key_id": "k1",                       // ✅ EXISTS (verify field name)
  "canonical_payload_hash": "sha256-hash",        // ⚠️ VERIFY
  "issued_at": 1710000000,                        // ⚠️ VERIFY (Unix seconds)
  "ttl_ms": 300000,                               // ⚠️ NEW FIELD
  "context_echo": {                               // ⚠️ VERIFY + ADD input_hash
    "request_id": "req-uuid-12345",
    "tenant_id": "ent-tenant",
    "agent_id": "ent-agent",
    "policy_id": "policy-abc",                    // ⚠️ NEW FIELD
    "policy_version": "v2",
    "input_hash": "sha256-hash-of-request",       // ⚠️ NEW FIELD (must echo back)
    "timestamp_ms": 1710000000000,
    "environment": "production"
  },
  "audit_event_id": "evt-abc123"                  // ✅ EXISTS
}
```

---

## ⚠️ Fields to Verify/Add

### 1. `input_hash` (CRITICAL - NEW)

**What it is:** SHA-256 hash of the canonicalized request input.

**Why it matters:** Prevents tampering with request content. Vigil computes hash before sending to AgentShield, AgentShield echoes it back. Vigil verifies the decision is for the exact request content sent.

**How to compute:**
```python
import hashlib
import json

# Canonical request data (sorted keys)
request_data = {
    "agent_id": "agent-1",
    "messages": [{"role": "user", "content": "Hello"}],
    "policy_id": "policy-abc",
    "request_id": "req-123",
    "tenant_id": "tenant-1",
    "timestamp_ms": 1710000000000
}

canonical = json.dumps(request_data, sort_keys=True, separators=(',', ':'))
input_hash = hashlib.sha256(canonical.encode()).hexdigest()
```

**Must echo back in response:**
```json
{
  "context_echo": {
    "input_hash": "sha256-of-request"  // ← Echo this back
  }
}
```

---

### 2. `ttl_ms` (CRITICAL - NEW)

**What it is:** Time-to-live in milliseconds. Decision expires after `issued_at + ttl_ms`.

**Why it matters:** Prevents replay attacks. Vigil rejects decisions older than TTL.

**How to implement:**
```python
import time

issued_at = int(time.time())  # Unix seconds
ttl_ms = 300000  # 5 minutes

# Add to response
response = {
    "issued_at": issued_at,
    "ttl_ms": ttl_ms,
    ...
}

# Vigil will verify:
# current_time <= issued_at + (ttl_ms / 1000)
```

**Add to response:**
```json
{
  "issued_at": 1710000000,     // Unix seconds
  "ttl_ms": 300000             // 5 minutes
}
```

---

### 3. `schema_version` (CRITICAL - NEW)

**What it is:** Version identifier for decision envelope format.

**Why it matters:** Allows breaking changes. Vigil rejects unknown versions.

**How to implement:**
```python
SCHEMA_VERSION = "as_decision_v1"

response = {
    "schema_version": SCHEMA_VERSION,
    ...
}
```

**Add to response:**
```json
{
  "schema_version": "as_decision_v1"
}
```

---

### 4. `policy_id` (IMPORTANT - NEW)

**What it is:** Unique identifier for the policy configuration.

**Why it matters:** Distinguishes between different policies (not just versions). Enables policy-level auditing.

**How to implement:**
```python
# In request
request_data = {
    "policy_id": "policy-abc",      # Policy identifier
    "policy_version": "v2",         # Version of that policy
    ...
}

# Echo in response
response = {
    "context_echo": {
        "policy_id": "policy-abc",
        "policy_version": "v2",
        ...
    }
}
```

**Add to response:**
```json
{
  "context_echo": {
    "policy_id": "policy-abc",
    "policy_version": "v2"
  }
}
```

---

### 5. `canonical_payload_hash` (VERIFY)

**What it is:** SHA-256 hash of the canonical payload that was signed.

**Why it matters:** Vigil uses this to detect tampering. If response is modified after signing, hash won't match.

**How to compute:**
```python
import hashlib
import json

payload = {
    "action": "ALLOW",
    "risk_score": 0.12,
    "reasons": ["stub-allow"],
    "context_echo": {...},
    "audit_event_id": "evt-abc123",
    "issued_at": 1710000000
}

canonical = json.dumps(payload, sort_keys=True)
hash_value = hashlib.sha256(canonical.encode()).hexdigest()
```

**Add to response:**
```json
{
  "canonical_payload_hash": "abc123..."  // SHA-256 hex string
}
```

---

### 6. `issued_at` (VERIFY - ALREADY DISCUSSED)

**What it is:** Unix timestamp when decision was issued.

**Why it matters:** Vigil rejects decisions older than 300 seconds (configurable via `DECISION_MAX_AGE_SECONDS`). Prevents replay attacks.

**How to compute:**
```python
import time

issued_at = int(time.time())  # Unix timestamp (seconds since epoch)
```

**Add to response:**
```json
{
  "issued_at": 1710000000  // Unix timestamp (integer)
}
```

---

### 7. `context_echo` (VERIFY - UPDATE WITH NEW FIELDS)

**What it is:** Echo of the request context that Vigil sent.

**Why it matters:** Vigil validates that the decision is for THIS EXACT request, not a replayed or cross-tenant decision.

**Updated to include new fields:**
```python
# In AgentShield /v1/enforce handler:

request_data = request.json
context_echo = {
    "request_id": request_data["request_id"],
    "tenant_id": request_data["tenant_id"],
    "agent_id": request_data["agent_id"],
    "policy_id": request_data["policy_id"],          # ← NEW
    "policy_version": request_data["policy_version"],
    "input_hash": request_data["input_hash"],        # ← NEW (critical)
    "timestamp_ms": request_data["timestamp_ms"],
    "environment": request_data.get("environment", "unknown")
}

# Include in signed payload and response
response = {
    "action": "ALLOW",
    "context_echo": context_echo,
    ...
}
```

**Add to response:**
```json
{
  "context_echo": {
    "request_id": "req-uuid-12345",
    "tenant_id": "ent-tenant",
    "agent_id": "ent-agent",
    "policy_id": "policy-abc",         // ← NEW
    "policy_version": "v2",
    "input_hash": "sha256-hash",       // ← NEW (must match request)
    "timestamp_ms": 1710000000000,
    "environment": "production"
  }
}
```

---

## 🔍 How to Verify

### Test AgentShield Response

```bash
# Send test request to AgentShield
curl -X POST http://localhost:9000/v1/enforce \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-123",
    "tenant_id": "demo-tenant",
    "agent_id": "demo-agent",
    "policy_version": "v1",
    "environment": "test",
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# Expected response should include:
# - signature (base64 string)
# - signature_key_id (string like "k1")
# - canonical_payload_hash (hex string)
# - issued_at (integer Unix timestamp)
# - context_echo (object with all request context)
# - audit_event_id (string)
```

### Check Response

```python
import json

response = {...}  # AgentShield response

# Check required fields
assert "signature" in response, "Missing signature"
assert "signature_key_id" in response, "Missing signature_key_id"
assert "canonical_payload_hash" in response, "Missing canonical_payload_hash"
assert "issued_at" in response, "Missing issued_at"
assert "context_echo" in response, "Missing context_echo"

# Check context_echo fields
context = response["context_echo"]
assert "request_id" in context, "Missing request_id in context_echo"
assert "tenant_id" in context, "Missing tenant_id in context_echo"
assert "agent_id" in context, "Missing agent_id in context_echo"
assert "policy_version" in context, "Missing policy_version in context_echo"

print("✅ All required fields present!")
```

---

## 🔧 Quick Fix (If Fields Missing)

If AgentShield is missing any fields, add them to the response builder:

```python
# In AgentShield backend (pseudo-code)

def create_decision_response(request_data, decision):
    # 1. Create canonical payload
    canonical_payload = {
        "action": decision.action,
        "risk_score": decision.risk_score,
        "reasons": decision.reasons,
        "context_echo": {
            "request_id": request_data["request_id"],
            "tenant_id": request_data["tenant_id"],
            "agent_id": request_data["agent_id"],
            "policy_version": request_data["policy_version"],
            "environment": request_data.get("environment", "unknown")
        },
        "audit_event_id": generate_event_id(),
        "issued_at": int(time.time())
    }
    
    # 2. Compute hash
    canonical_json = json.dumps(canonical_payload, sort_keys=True)
    payload_hash = hashlib.sha256(canonical_json.encode()).hexdigest()
    
    # 3. Sign payload
    signature = sign_with_ed25519(canonical_json, private_key)
    
    # 4. Build response
    response = canonical_payload.copy()
    response["signature"] = base64.b64encode(signature).decode()
    response["signature_key_id"] = "k1"  # Current active key ID
    response["canonical_payload_hash"] = payload_hash
    
    return response
```

---

## 🚀 Testing End-to-End

Once AgentShield has all fields:

```bash
# 1. Start Vigil + AgentShield
docker-compose up -d

# 2. Send test request through Vigil
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: demo" \
  -H "X-Agent-ID: test" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'

# 3. Check Vigil logs for signature verification
docker-compose logs vigil | grep "sig_verified"

# Expected: sig_verified=true
# If sig_verified=false, check:
#   - Signature is valid Ed25519
#   - canonical_payload_hash matches
#   - issued_at is recent (< 300s old)
#   - context_echo matches request

# 4. View in dashboard
# Open http://localhost:3000
# Login: admin / admin123
# See entry in Audit Logs with ✅ verified
```

---

## 📋 Checklist

**AgentShield Response (Updated):**

- [ ] `schema_version` field (e.g., "as_decision_v1") **← NEW**
- [ ] `action` field (ALLOW, BLOCK, SANITIZE)
- [ ] `risk_score` field (0.0 - 1.0)
- [ ] `reasons` array
- [ ] `signature` field (base64 Ed25519)
- [ ] `signature_key_id` field (e.g., "k1")
- [ ] `canonical_payload_hash` field (SHA-256 hex)
- [ ] `issued_at` field (Unix timestamp seconds)
- [ ] `ttl_ms` field (milliseconds) **← NEW**
- [ ] `context_echo` object with:
  - [ ] `request_id`
  - [ ] `tenant_id`
  - [ ] `agent_id`
  - [ ] `policy_id` **← NEW**
  - [ ] `policy_version`
  - [ ] `input_hash` **← NEW (critical)**
  - [ ] `timestamp_ms`
  - [ ] `environment`
- [ ] `audit_event_id` field

**Vigil Request (What Vigil Sends):**

- [ ] `request_id`
- [ ] `tenant_id`
- [ ] `agent_id`
- [ ] `policy_id` **← NEW**
- [ ] `policy_version`
- [ ] `input_hash` **← NEW (critical)**
- [ ] `timestamp_ms` **← NEW**
- [ ] `ttl_ms` **← NEW**
- [ ] `environment`
- [ ] `messages`

**Verification:**

- [ ] Signature is valid Ed25519
- [ ] Hash matches canonical payload
- [ ] Timestamp is recent (< 5 minutes)
- [ ] `issued_at + ttl_ms` not expired **← NEW**
- [ ] Context echo matches request (all fields including input_hash) **← UPDATED**
- [ ] JWKS endpoint returns valid keys
- [ ] Schema version is recognized **← NEW**
- [ ] Clock skew tolerance: ±2 minutes **← NEW**

---

## 🎯 Summary

**Vigil side: ⚠️ 80% complete - Needs Priority 1 updates**
- Dashboard UI ready ✅
- Admin APIs ready ✅
- Signature verification ready ✅
- Audit logging ready ✅
- **Need to add:** input_hash computation, ttl_ms validation, error taxonomy

**AgentShield side: ⚠️ Verify 7 fields (4 new)**
1. `input_hash` - **NEW** - Hash of canonicalized request (critical)
2. `ttl_ms` - **NEW** - Time-to-live in milliseconds
3. `schema_version` - **NEW** - Version identifier ("as_decision_v1")
4. `policy_id` - **NEW** - Policy identifier (not just version)
5. `canonical_payload_hash` - VERIFY - SHA-256 of signed payload
6. `issued_at` - VERIFY - Unix timestamp
7. `context_echo` - UPDATE - Must include input_hash and policy_id

**If those 7 fields exist → System is production-ready!**

**If missing → Implementation guide provided above**

**Priority:** Implement `input_hash` first - it's the most critical security addition.

---

## 📞 Next Steps

1. ✅ Check if AgentShield already has these fields
2. ⚠️ If missing, add them (5 minute fix)
3. ✅ Test end-to-end with Vigil
4. ✅ Verify dashboard shows ✅ verified
5. 🚀 Deploy to production

**The audit dashboard is the monetization core. This is what companies pay for.**
