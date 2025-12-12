# AgentShield Decision Signing Specification

This document specifies how AgentShield must sign enforcement decisions and how Vigil verifies them.

## Requirement

All enforcement decisions MUST be signed when `AGENTSHIELD_REQUIRE_SIGNED=true` (production default).

## Signing Algorithm

- **Algorithm**: RSA with PKCS#1 v1.5 padding
- **Hash**: SHA-256
- **Key size**: 2048-bit minimum (4096-bit recommended for production)
- **Encoding**: Base64 URL-safe (without padding)

## Canonical Payload

The signed payload MUST be a JSON object with deterministic serialization:

```json
{
  "request_context": {
    "request_id": "req_1765561072.123",
    "tenant_id": "prod-tenant",
    "agent_id": "prod-agent",
    "policy_version": 10,
    "environment": "production"
  },
  "decision": {
    "action": "ALLOW",
    "risk_score": 0.15,
    "reasons": ["policy-allowed"],
    "audit_event_id": "evt_abc123",
    "signature_hash": "merkle_hash_xyz",
    "sanitized": []
  }
}
```

**Canonicalization rules:**
- Keys sorted lexicographically
- No whitespace: `separators=(',', ':')`
- UTF-8 encoding
- Fields MUST match exactly (no extra fields in signed payload)

## Response Format

AgentShield `/v1/enforce` responses MUST include:

```json
{
  "action": "ALLOW",
  "risk_score": 0.15,
  "reasons": ["policy-allowed"],
  "audit_event_id": "evt_abc123",
  "signature_hash": "merkle_hash_xyz",
  "sanitized": [],
  "signature": "base64url_encoded_signature_without_padding",
  "key_id": "prod-key-2024-12"
}
```

**Required fields:**
- `signature`: Base64 URL-safe encoded RSA signature (strip trailing `=`)
- `key_id`: Identifies which key was used (enables key rotation)

## Key Management

### Key Distribution
- AgentShield provides public keys via:
  1. PEM file at a known path (`AGENTSHIELD_PUBKEY_PATH`)
  2. Inline PEM (`AGENTSHIELD_PUBKEY_PEM`)
  3. (Future) JWKS endpoint for dynamic key rotation

### Key Rotation
- Multiple keys may be active simultaneously (overlapping validity)
- Vigil validates against the key matching `key_id`
- Old keys remain valid during rotation window

### Key Pinning
- Vigil pins expected `key_id` via `AGENTSHIELD_KEY_ID` env var
- Decisions with unexpected `key_id` are rejected
- Prevents key-confusion attacks

## Vigil Verification Flow

1. **Receive decision** from AgentShield `/v1/enforce`
2. **Check required fields**: `signature`, `key_id`
3. **Validate key_id** matches `AGENTSHIELD_KEY_ID`
4. **Load pinned public key** from `AGENTSHIELD_PUBKEY_PATH` or `AGENTSHIELD_PUBKEY_PEM`
5. **Reconstruct canonical payload** using request context + decision fields
6. **Verify signature** using RSA PKCS#1 v1.5 + SHA-256
7. **On success**: Mark `sig_verified=true`, proceed with enforcement
8. **On failure**: Reject decision, return HTTP 503 (fail closed)

## Context Binding

The signature includes **request context** to prevent:
- **Cross-tenant attacks**: Decision for tenant A cannot be replayed for tenant B
- **Confused deputy**: Decision bound to specific agent/policy cannot be reused
- **Replay attacks**: `request_id` uniqueness enforced

## Security Properties

- **Authenticity**: Only AgentShield with the private key can sign decisions
- **Integrity**: Any tampering invalidates the signature
- **Non-repudiation**: Signed decisions are tamper-evident and logged
- **Context binding**: Decisions cannot be reused across different contexts

## Error Handling

### Missing Signature
If `AGENTSHIELD_REQUIRE_SIGNED=true` and decision lacks `signature` or `key_id`:
- Gateway returns HTTP 503: "AgentShield unavailable or decision verification failed"
- No fallback to unsigned mode
- Incident logged

### Verification Failure
If signature verification fails:
- Gateway returns HTTP 503
- Log includes: `sig_verified=false`, failure reason
- No fallback to unsigned mode

### Key Mismatch
If `key_id` doesn't match `AGENTSHIELD_KEY_ID`:
- Treated as verification failure (HTTP 503)
- Prevents key-confusion attacks

## Production Configuration

```bash
# AgentShield
AGENTSHIELD_REQUIRE_SIGNED=true
AGENTSHIELD_KEY_ID=prod-key-2024-12
AGENTSHIELD_PUBKEY_PATH=/etc/vigil/agentshield_prod.pem

# Vigil
VIGIL_ENVIRONMENT=production
AGENTSHIELD_REQUIRED=true  # Fail closed if AgentShield unavailable
```

## Test Validation

Validated with:
- Real RSA keypair (2048-bit)
- Signed stub signing canonical payload
- Gateway verification with pinned key
- Latency: ~11.8 ms (includes signing + verification)
- Audit log: `sig_verified=true`, `key_id=default`, `environment=production`, `policy_version=10`

## Future Enhancements

1. **JWKS endpoint**: Dynamic key discovery and rotation
2. **Ed25519 support**: Faster signing/verification
3. **Timestamp validation**: Reject stale decisions
4. **Nonce tracking**: Additional replay protection
