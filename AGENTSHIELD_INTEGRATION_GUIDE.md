# AgentShield Backend Integration Guide

## Quick Reference: What Changed in Vigil

Vigil has been updated with **Priority 1 security hardening**. Here's what AgentShield backend needs to implement to work with the new version.

---

## TL;DR - Required Changes

Add **4 new fields** to your `/v1/enforce` response:

```python
# In your AgentShield backend:

response = {
    "schema_version": "as_decision_v1",        # NEW - Add this
    "action": "ALLOW",
    "risk_score": 0.12,
    "ttl_ms": 300000,                          # NEW - Add this (5 minutes)
    "issued_at": int(time.time()),
    "context_echo": {
        "request_id": request_data["request_id"],
        "tenant_id": request_data["tenant_id"],
        "agent_id": request_data["agent_id"],
        "policy_id": request_data["policy_id"],          # NEW - Echo this
        "policy_version": request_data["policy_version"],
        "input_hash": request_data["input_hash"],        # NEW - Echo this (critical!)
        "timestamp_ms": request_data["timestamp_ms"],
        "environment": request_data["environment"]
    },
    # ... rest of your response
}
```

**That's it!** Just add those 4 fields and you're compatible.

---

## Detailed Implementation

### 1. Add `schema_version` Field ⭐ NEW

**What:** Version identifier for decision envelope format  
**Value:** Always `"as_decision_v1"` for now  
**Why:** Enables breaking changes without breaking old clients

```python
response["schema_version"] = "as_decision_v1"
```

---

### 2. Add `ttl_ms` Field ⭐ NEW

**What:** Decision expiry time in milliseconds  
**Default:** 300000 (5 minutes)  
**Why:** Prevents replay attacks

```python
response["ttl_ms"] = 300000  # 5 minutes

# Vigil will validate: current_time <= issued_at + (ttl_ms / 1000)
```

---

### 3. Echo `policy_id` in `context_echo` ⭐ NEW

**What:** Policy identifier (not just version)  
**Why:** Enables policy-level auditing  
**Action:** Echo back whatever Vigil sends

```python
# Vigil will now send this in requests:
request_data["policy_id"]  # e.g., "policy-abc"

# You must echo it back:
response["context_echo"]["policy_id"] = request_data["policy_id"]
```

---

### 4. Echo `input_hash` in `context_echo` ⭐ NEW (CRITICAL!)

**What:** SHA-256 hash of canonicalized request  
**Why:** Prevents request tampering (MITM attacks)  
**Action:** Echo back whatever Vigil sends

```python
# Vigil will now send this in requests:
request_data["input_hash"]  # e.g., "abc123def456..."

# You MUST echo it back:
response["context_echo"]["input_hash"] = request_data["input_hash"]
```

**⚠️ IMPORTANT:** Don't compute the hash yourself. Just echo back what Vigil sends.

---

## Request Format Changes

Vigil will now send these **additional fields** in enforcement requests:

```json
{
  "request_id": "req-123",
  "tenant_id": "tenant-1",
  "agent_id": "agent-1",
  "policy_id": "policy-abc",           // ⭐ NEW
  "policy_version": 1,
  "timestamp_ms": 1710000000000,       // ⭐ NEW (milliseconds)
  "ttl_ms": 300000,                    // ⭐ NEW (5 minutes)
  "input_hash": "sha256-hash-here",    // ⭐ NEW (critical!)
  "messages": [...],
  "environment": "production"
}
```

**You don't need to validate these** - just echo back `policy_id` and `input_hash` in `context_echo`.

---

## Complete Example

### Before (Old Format)

```python
def enforce(request_data):
    decision = make_decision(request_data)
    
    response = {
        "action": decision.action,
        "risk_score": decision.risk_score,
        "issued_at": int(time.time()),
        "context_echo": {
            "request_id": request_data["request_id"],
            "tenant_id": request_data["tenant_id"],
            "agent_id": request_data["agent_id"],
            "policy_version": request_data["policy_version"]
        }
    }
    
    # Sign and return
    return sign_response(response)
```

### After (New Format) ✅

```python
def enforce(request_data):
    decision = make_decision(request_data)
    
    response = {
        "schema_version": "as_decision_v1",     # ⭐ NEW
        "action": decision.action,
        "risk_score": decision.risk_score,
        "issued_at": int(time.time()),
        "ttl_ms": 300000,                       # ⭐ NEW
        "context_echo": {
            "request_id": request_data["request_id"],
            "tenant_id": request_data["tenant_id"],
            "agent_id": request_data["agent_id"],
            "policy_id": request_data.get("policy_id"),          # ⭐ NEW
            "policy_version": request_data["policy_version"],
            "input_hash": request_data.get("input_hash"),        # ⭐ NEW
            "timestamp_ms": request_data.get("timestamp_ms"),
            "environment": request_data.get("environment")
        }
    }
    
    # Sign and return
    return sign_response(response)
```

**Changes:**
- Added `schema_version` at top level
- Added `ttl_ms` at top level
- Echo `policy_id` in `context_echo`
- Echo `input_hash` in `context_echo`
- Echo `timestamp_ms` in `context_echo`

---

## Testing Your Changes

### 1. Start Updated AgentShield

```bash
# Start your AgentShield backend with the changes
python your_agentshield_server.py
```

### 2. Test with Vigil

```bash
# In Vigil repo
cd /workspaces/vigil

# Start Vigil
docker-compose up vigil

# Send test request
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: test-tenant" \
  -H "X-Agent-ID: test-agent" \
  -H "X-Policy-ID: policy-test" \
  -d '{
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### 3. Check Logs

```bash
# Check Vigil logs for verification status
docker-compose logs vigil | grep "sig_verified"

# Expected output:
# sig_verified=true ✅
```

### 4. View in Dashboard

```bash
# Open dashboard
open http://localhost:3000

# Login: admin / admin123
# Check Audit Logs page - should show:
#   • ✅ Signature Verified
#   • policy_id: policy-test
#   • input_hash: abc123...
```

---

## Error Handling

If you **don't** add the new fields, Vigil will:

1. **Missing `input_hash`:** ✅ Still works (optional verification)
2. **Missing `policy_id`:** ✅ Still works (uses default)
3. **Missing `ttl_ms`:** ✅ Still works (uses timestamp validation only)
4. **Missing `schema_version`:** ✅ Still works (no version check)

**But:** You **should** add them for production security!

---

## Backward Compatibility

✅ **Old AgentShield backends still work** - Vigil handles missing fields gracefully  
⚠️ **But:** Security is degraded without the new fields  
🎯 **Recommended:** Update AgentShield ASAP for full security

---

## Common Issues

### Issue 1: `input_hash` Mismatch

```
Error: Input hash mismatch: request tampered
```

**Cause:** You're computing the hash instead of echoing  
**Fix:** Just echo back `request_data["input_hash"]`

### Issue 2: `schema_version` Invalid

```
Error: Unsupported schema_version: as_decision_v2
```

**Cause:** Using wrong version string  
**Fix:** Use exactly `"as_decision_v1"`

### Issue 3: TTL Expired

```
Error: Decision TTL expired
```

**Cause:** `ttl_ms` is too small or `issued_at` is old  
**Fix:** Use at least 60000ms (1 minute) TTL

---

## Verification Checklist

Before deploying:

- [ ] Added `schema_version = "as_decision_v1"` to response
- [ ] Added `ttl_ms = 300000` to response
- [ ] Echo `policy_id` in `context_echo`
- [ ] Echo `input_hash` in `context_echo` (critical!)
- [ ] Tested with Vigil end-to-end
- [ ] Verified signature validation passes
- [ ] Checked dashboard shows new fields

---

## Support

**Questions?** Check these files:
- [AGENTSHIELD_TODO.md](AGENTSHIELD_TODO.md) - Full specification
- [PRIORITY1_COMPLETE.md](PRIORITY1_COMPLETE.md) - Implementation details
- [test_priority1_implementation.py](test_priority1_implementation.py) - Test examples

**Need help?** The Vigil implementation is complete and tested. Just follow this guide!

---

## Timeline

**Estimated implementation time:** 15-30 minutes

**Steps:**
1. Add 4 new fields to response (5 minutes)
2. Test locally (10 minutes)
3. Deploy and verify (5 minutes)

**Impact:** ⚠️ High - Enables enterprise-grade security for Vigil

---

✅ **That's all you need!** Add those 4 fields and you're production-ready with Vigil.
