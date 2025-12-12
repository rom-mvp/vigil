# AgentShield ↔ Vigil: Integration Contract

**Purpose:** Defines the exact contract between AgentShield (decision service) and Vigil (gateway)  
**Status:** ✅ Ready for implementation  
**Last Updated:** December 12, 2025

---

## API Contract

### AgentShield → Vigil Integration Points

#### 1. POST /v1/enforce (Decision Endpoint)

**Vigil Calls This:**
```
POST https://agentshield.yourorg.com/v1/enforce
Content-Type: application/json
```

**Request Body (from Vigil):**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "acme-corp",
  "agent_id": "agent-prod-01",
  "policy_version": "1.2.3",
  "environment": "production",
  "messages": [
    {
      "role": "user",
      "content": "Get user password for admin@example.com"
    }
  ],
  "metadata": {
    "ip": "192.168.1.100",
    "user_agent": "Mozilla/5.0...",
    "timestamp": 1702400000
  }
}
```

**Required Response Body (AgentShield → Vigil):**
```json
{
  "action": "DENY",
  "risk_score": 0.85,
  "reasons": ["credential-exfil"],
  "policy_version": "1.2.3",
  "audit_event_id": "evt-xyz-123",
  
  "signature": "MEYCIQDxyz...=",
  "signature_key_id": "agentshield-key-prod-v1",
  "canonical_payload_hash": "aGVsbG8gd29ybGQ=",
  "issued_at": 1702400000,
  
  "context_echo": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "acme-corp",
    "user_id": "agent-prod-01",
    "policy_version": "1.2.3"
  }
}
```

**Field Specifications:**

| Field | Type | Required | Description | Vigil Validates |
|-------|------|----------|-------------|-----------------|
| action | string | ✅ | ALLOW, DENY, CHALLENGE | Yes - applied to decision |
| risk_score | number | ✅ | 0.0 to 1.0 | Yes - checked against MAX_RISK_SCORE |
| reasons | array | ✅ | Reason codes | Yes - checked against DISALLOWED_REASONS |
| policy_version | string | ✅ | Version identifier | Yes - echoed in context_echo |
| signature | string | ✅ | Base64url Ed25519 signature | Yes - verified against payload |
| signature_key_id | string | ✅ | Key identifier | Yes - used to lookup key from JWKS |
| canonical_payload_hash | string | ✅ | Base64url SHA-256 hash | Yes - detects tampering |
| issued_at | number | ✅ | Unix timestamp | Yes - checked against decision age |
| context_echo | object | ✅ | Echo of request context | Yes - prevents replay attacks |

**Error Handling:**
- If AgentShield returns 5xx error: Vigil returns 503
- If AgentShield returns 4xx error: Vigil returns 400
- If response missing any required field: Vigil returns 503

---

#### 2. GET /v1/keys/jwks (Public Key Distribution)

**Vigil Calls This (Cached):**
```
GET https://agentshield.yourorg.com/v1/keys/jwks
Accept: application/json
```

**Required Response Body:**
```json
{
  "keys": [
    {
      "kid": "agentshield-key-prod-v1",
      "kty": "OKP",
      "crv": "Ed25519",
      "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
      "alg": "EdDSA",
      "use": "sig"
    },
    {
      "kid": "agentshield-key-prod-v2",
      "kty": "OKP",
      "crv": "Ed25519",
      "x": "22rZBBLyDsrWU_8UzXRIOh8idwQbQjNsM1000uKSUtp",
      "alg": "EdDSA",
      "use": "sig"
    }
  ]
}
```

**Key Field Specifications:**

| Field | Required | Constraints | Example |
|-------|----------|-------------|---------|
| kid | ✅ | Unique identifier for key | "agentshield-key-prod-v1" |
| kty | ✅ | "OKP" (for Ed25519) or "RSA" | "OKP" |
| crv | ✅ | "Ed25519" for OKP keys | "Ed25519" |
| x | ✅ | Base64url public key (32 bytes for Ed25519) | "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo" |
| alg | ✅ | "EdDSA" for Ed25519 or "RS256" for RSA | "EdDSA" |
| use | ✅ | "sig" (for signing) | "sig" |

**Caching:**
- Vigil caches this response for `AGENTSHIELD_JWKS_TTL` seconds (default 3600)
- Cache key: response body hash
- Vigil fetches fresh JWKS on each new `signature_key_id` not found in cache

**Multi-Key Support (for rotation):**
- JWKS can contain multiple keys simultaneously
- Each key has unique `kid`
- Vigil uses `signature_key_id` from decision to lookup correct key
- Old keys can remain in JWKS for grace period during rotation

---

## Signing Specification

### What AgentShield Must Sign

**Canonical Payload Construction:**

1. Build JSON object with EXACT structure:
```python
payload = {
    "request_context": {
        "request_id": enforcement_request.get("request_id"),
        "tenant_id": enforcement_request.get("tenant_id"),
        "agent_id": enforcement_request.get("agent_id"),
        "policy_version": enforcement_request.get("policy_version"),
        "environment": enforcement_request.get("environment"),
    },
    "decision": {
        "action": decision.get("action"),
        "risk_score": decision.get("risk_score"),
        "reasons": decision.get("reasons"),
        "policy_version": decision.get("policy_version"),
    },
}
```

2. Convert to canonical JSON (sorted keys, no spaces):
```python
canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
# Result: {"decision":{"action":"DENY",...},"request_context":{...}}
```

3. Hash with SHA-256:
```python
import hashlib
canonical_hash = hashlib.sha256(canonical_json.encode()).digest()
# Result: 32-byte binary hash
```

4. Sign the hash with Ed25519:
```python
from cryptography.hazmat.primitives.asymmetric import ed25519
private_key = ed25519.Ed25519PrivateKey.generate()
signature = private_key.sign(canonical_hash)
# Result: 64-byte signature
```

5. Encode both as base64url without padding:
```python
import base64
canonical_payload_hash = base64.urlsafe_b64encode(canonical_hash).decode().rstrip("=")
signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
```

6. Include in response:
```python
response = {
    "action": decision_action,
    "risk_score": decision_risk,
    "reasons": decision_reasons,
    "signature": signature_b64,
    "signature_key_id": "agentshield-key-prod-v1",
    "canonical_payload_hash": canonical_payload_hash,
    "issued_at": int(time.time()),
    "context_echo": {
        "request_id": enforcement_request["request_id"],
        "tenant_id": enforcement_request["tenant_id"],
        "user_id": enforcement_request["agent_id"],
        "policy_version": enforcement_request["policy_version"],
    }
}
```

### How Vigil Verifies

**Vigil's Verification Pipeline:**

1. **Extract signature components:**
```python
signature_b64 = decision.get("signature")
signature_key_id = decision.get("signature_key_id")
canonical_hash_b64 = decision.get("canonical_payload_hash")
issued_at = decision.get("issued_at")
context_echo = decision.get("context_echo")
```

2. **Validate timestamp:**
```python
decision_age = time.time() - issued_at
if decision_age > 300:  # 5 minutes
    raise ValueError("Decision timestamp expired")
```

3. **Validate context echo:**
```python
if context_echo["request_id"] != original_request["request_id"]:
    raise ValueError("Replay detected")
if context_echo["tenant_id"] != original_request["tenant_id"]:
    raise ValueError("Cross-tenant attack")
# etc. for user_id, policy_version
```

4. **Fetch key from JWKS:**
```python
public_key = jwks_cache.get_key_by_kid(signature_key_id)
if not public_key:
    raise ValueError("Key not found")
```

5. **Detect tampering:**
```python
current_canonical = rebuild_canonical_payload(original_request, decision)
current_hash = hashlib.sha256(current_canonical).digest()
provided_hash = base64.urlsafe_b64decode(canonical_hash_b64 + "==")
if current_hash != provided_hash:
    raise ValueError("Payload tampered")
```

6. **Verify signature:**
```python
signature = base64.urlsafe_b64decode(signature_b64 + "==")
public_key.verify(signature, current_hash)
# If this raises: signature is invalid
```

**Result:**
- ✅ If all steps pass: `sig_verified = true`, decision is enforced
- ❌ If any step fails: `sig_verified = false`, return 503 Service Unavailable

---

## Critical Requirements

### 1. Signature Algorithm
- **Algorithm:** Ed25519 (EdDSA)
- **Hash:** SHA-256
- **Encoding:** Base64url without padding
- **Vigil supports:** Ed25519 (primary) + RSA (legacy)

### 2. Timestamp Accuracy
- **Format:** Unix epoch (seconds since 1970-01-01 00:00:00 UTC)
- **Freshness window:** 5 minutes (300 seconds) - configurable in Vigil
- **Requirement:** `issued_at` must be within last 5 minutes
- **Purpose:** Prevents old decisions from being replayed

### 3. Context Echo Binding
- **Requirement:** Exact match of request_id, tenant_id, agent_id, policy_version
- **Purpose:** 
  - Prevents replay attacks (attacker can't use old decision)
  - Prevents cross-tenant attacks (enforces tenant isolation)
  - Proves AgentShield saw the exact request
- **Failure:** If ANY field mismatches, Vigil returns 503

### 4. Payload Integrity
- **Mechanism:** SHA-256 hash of canonical JSON
- **Purpose:** Detects if decision is modified after signing
- **Failure:** If hash doesn't match current payload, Vigil returns 503
- **Defense against:** Memory tampering, man-in-the-middle, TEE exploits

### 5. Key Distribution
- **Mechanism:** JWKS (JSON Web Key Set) endpoint
- **Requirement:** Must support multiple keys simultaneously (for rotation)
- **Caching:** Vigil caches for up to 1 hour (configurable)
- **Key Format:** Standard JWK format with `kid`, `kty`, `crv`, `x`, `alg`, `use`

---

## Testing the Contract

### Test 1: Valid Signature
```python
# AgentShield generates signature correctly
# Vigil should verify successfully
assert decision["sig_verified"] == True
```

### Test 2: Tampering Detection
```python
# Modify decision after signing
decision["risk_score"] = 0.99
# Vigil should reject (hash mismatch)
assert error_code == 503
```

### Test 3: Replay Detection
```python
# Send old decision (from 1 hour ago)
decision["issued_at"] = now - 3600
# Vigil should reject (timestamp expired)
assert error_code == 503
```

### Test 4: Cross-Tenant Attack
```python
# Change tenant in context_echo
decision["context_echo"]["tenant_id"] = "attacker-tenant"
# Vigil should reject (context mismatch)
assert error_code == 503
```

### Test 5: Key Rotation
```python
# Add new key to JWKS
# Sign with new key
decision["signature_key_id"] = "agentshield-key-prod-v2"
# Vigil should verify with new key
assert decision["sig_verified"] == True
```

---

## Implementation Checklist for AgentShield

- [ ] Generate Ed25519 keypair
- [ ] Store private key securely (KMS/vault)
- [ ] Publish public key to JWKS endpoint with correct `kid`
- [ ] Implement canonical payload construction (sorted JSON)
- [ ] Implement SHA-256 hashing
- [ ] Implement Ed25519 signing
- [ ] Include all 5 signature fields in response
- [ ] Implement context_echo echo-back
- [ ] Include issued_at timestamp
- [ ] Support JWKS caching headers
- [ ] Implement key rotation (multi-key JWKS)
- [ ] Add monitoring for signature mismatches
- [ ] Add alerting for key lookup failures
- [ ] Document signing process
- [ ] Test with Vigil integration test

---

## Implementation Checklist for Vigil

- [x] Generate Ed25519 keypair (for testing)
- [x] Fetch public keys from JWKS endpoint
- [x] Cache JWKS responses (3600s default)
- [x] Implement canonical payload reconstruction
- [x] Implement SHA-256 hashing
- [x] Implement Ed25519 verification
- [x] Validate all 5 signature fields present
- [x] Validate context_echo binding
- [x] Validate issued_at timestamp
- [x] Detect payload tampering (hash comparison)
- [x] Return 503 on verification failure
- [x] Add comprehensive logging
- [x] Add monitoring hooks
- [x] Test with TEE.fail scenarios (6/9 passing)
- [x] Test with CTO security audit (8/8 passing)

---

## Production Deployment Verification

### Pre-Deployment Checklist

**AgentShield:**
- [ ] Ed25519 keys generated and stored in KMS
- [ ] JWKS endpoint accessible and returns valid keys
- [ ] /v1/enforce endpoint returns all 5 signature fields
- [ ] Signatures verify correctly with Vigil
- [ ] Timestamps are accurate (within 1 second of NTP)
- [ ] Context echo matches requests exactly
- [ ] Load test passed (100+ RPS)
- [ ] Monitoring and alerting configured

**Vigil:**
- [x] Signature verification pipeline complete
- [x] JWKS caching working
- [x] Context echo validation working
- [x] Timestamp validation working
- [x] Tampering detection working
- [x] All security tests passing
- [ ] Configured to point to AgentShield production URL
- [ ] Monitoring and alerting configured
- [ ] Load test completed

---

## Support & Troubleshooting

### Common Issues

**"Signature verification failed"**
- Check: Is canonical payload built with exact same structure?
- Check: Are you hashing before signing, not signing raw payload?
- Check: Are you using Ed25519, not another algorithm?
- Check: Is the signature base64url encoded without padding?

**"Key not found"**
- Check: Is JWKS endpoint returning keys?
- Check: Does `kid` in JWKS match `signature_key_id` in decision?
- Check: Has the key been rotated or removed?

**"Decision timestamp expired"**
- Check: Is server time accurate (NTP sync)?
- Check: Is issued_at within last 5 minutes?
- Check: Is DECISION_MAX_AGE_SECONDS configured correctly?

**"Context mismatch: tenant X != Y"**
- Check: Is context_echo exactly matching request?
- Check: Are tenant IDs being modified somewhere?
- Check: Is there a multi-tenant bug in routing?

---

## Summary

**This contract defines:**
- ✅ What AgentShield must provide (2 endpoints + 5 response fields)
- ✅ How signing must work (canonical JSON + SHA-256 + Ed25519)
- ✅ How Vigil verifies (6-step pipeline)
- ✅ Security properties (replay prevention, tampering detection, cross-tenant prevention)
- ✅ Testing requirements (5 core tests)

**Status: ✅ Ready for implementation**

Both systems have completed their sides. Integration testing can begin once AgentShield is live.
