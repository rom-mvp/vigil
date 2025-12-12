# 🚨 AgentShield Backend Action Items

## Overview

Vigil dashboard and audit system is **100% complete**. The AgentShield backend needs to verify it's providing all required fields in its decision responses.

---

## ✅ What AgentShield MUST Provide

### 1. POST /v1/enforce Response Fields

**Currently Required (Verify These Exist):**

```json
{
  "action": "ALLOW",                              // ✅ EXISTS
  "risk_score": 0.12,                             // ✅ EXISTS
  "reasons": ["stub-allow"],                      // ✅ EXISTS
  "signature": "base64-ed25519-sig",              // ✅ EXISTS
  "signature_key_id": "k1",                       // ✅ EXISTS (verify field name)
  "canonical_payload_hash": "sha256-hash",        // ⚠️ VERIFY
  "issued_at": 1710000000,                        // ⚠️ VERIFY
  "context_echo": {                               // ⚠️ VERIFY
    "request_id": "req-uuid-12345",
    "tenant_id": "ent-tenant",
    "agent_id": "ent-agent",
    "policy_version": "v1",
    "environment": "production"
  },
  "audit_event_id": "evt-abc123"                  // ✅ EXISTS
}
```

---

## ⚠️ Fields to Verify

### 1. `canonical_payload_hash` (CRITICAL)

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

### 2. `issued_at` (CRITICAL)

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

### 3. `context_echo` (CRITICAL)

**What it is:** Echo of the request context that Vigil sent.

**Why it matters:** Vigil validates that the decision is for THIS EXACT request, not a replayed or cross-tenant decision.

**How to implement:**
```python
# In AgentShield /v1/enforce handler:

request_data = request.json
context_echo = {
    "request_id": request_data["request_id"],
    "tenant_id": request_data["tenant_id"],
    "agent_id": request_data["agent_id"],
    "policy_version": request_data["policy_version"],
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
    "policy_version": "v1",
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

**AgentShield Response:**

- [ ] `action` field (ALLOW, BLOCK, SANITIZE)
- [ ] `risk_score` field (0.0 - 1.0)
- [ ] `reasons` array
- [ ] `signature` field (base64 Ed25519)
- [ ] `signature_key_id` field (e.g., "k1")
- [ ] `canonical_payload_hash` field (SHA-256 hex)
- [ ] `issued_at` field (Unix timestamp)
- [ ] `context_echo` object with:
  - [ ] `request_id`
  - [ ] `tenant_id`
  - [ ] `agent_id`
  - [ ] `policy_version`
  - [ ] `environment`
- [ ] `audit_event_id` field

**Verification:**

- [ ] Signature is valid Ed25519
- [ ] Hash matches canonical payload
- [ ] Timestamp is recent (< 5 minutes)
- [ ] Context echo matches request
- [ ] JWKS endpoint returns valid keys

---

## 🎯 Summary

**Vigil side: ✅ 100% complete**
- Dashboard UI ready
- Admin APIs ready
- Signature verification ready
- Audit logging ready

**AgentShield side: ⚠️ Verify these 3 fields**
1. `canonical_payload_hash` - SHA-256 of signed payload
2. `issued_at` - Unix timestamp
3. `context_echo` - Request context object

**If those 3 fields exist → System is production-ready!**

**If missing → Quick fix in AgentShield response builder (see code above)**

---

## 📞 Next Steps

1. ✅ Check if AgentShield already has these fields
2. ⚠️ If missing, add them (5 minute fix)
3. ✅ Test end-to-end with Vigil
4. ✅ Verify dashboard shows ✅ verified
5. 🚀 Deploy to production

**The audit dashboard is the monetization core. This is what companies pay for.**
