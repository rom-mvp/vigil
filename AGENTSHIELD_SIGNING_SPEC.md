# AgentShield Decision Signing Specification

This document specifies how AgentShield must sign enforcement decisions and how Vigil verifies them.

## Requirement

All enforcement decisions MUST be signed when `AGENTSHIELD_REQUIRE_SIGNED=true` (production default).

## Signing Algorithm

### Supported Algorithms

**Primary (Recommended): Ed25519**
- **Algorithm**: Ed25519 (EdDSA)
- **No hash required**: Ed25519 is deterministic
- **Encoding**: Base64 URL-safe (without padding)
- **Performance**: ~10x faster than RSA

**Legacy: RSA**
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
  "signature_key_id": "prod-key-2024-12",
  "canonical_payload_hash": "base64url_sha256_hash_of_canonical_payload",
  "context_echo": {
    "tenant_id": "prod-tenant",
    "user_id": "prod-agent",
    "policy_version": 10
  }
}
```

**Required fields:**
- `signature`: Base64 URL-safe encoded signature (strip trailing `=`)
- `signature_key_id`: Identifies which key was used (enables key rotation)
- `canonical_payload_hash`: SHA-256 hash of canonical payload (for Ed25519)
- `context_echo`: Echoed request context for validation

## Key Management

### JWKS Endpoint (Recommended)

AgentShield SHOULD expose keys at `GET /v1/keys/jwks`:

```json
{
  "keys": [
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "prod-key-2024-12",
      "x": "base64url_encoded_public_key"
    }
  ]
}
```

Vigil fetches JWKS periodically (default TTL: 3600s) and caches keys.

### Static Key Distribution (Legacy)
- AgentShield provides public keys via:
  1. PEM file at a known path (`AGENTSHIELD_PUBKEY_PATH`)
  2. Inline PEM (`AGENTSHIELD_PUBKEY_PEM`)

### Key Rotation
- Multiple keys may be active simultaneously (overlapping validity)
- Vigil validates against the key matching `key_id`
- Old keys remain valid during rotation window

### Key Pinning
- Vigil pins expected `key_id` via `AGENTSHIELD_KEY_ID` env var
- Decisions with unexpected `key_id` are rejected
- Prevents key-confusion attacks

## Transport Security (mTLS)

Vigil MUST authenticate to AgentShield using mutual TLS:

```bash
AGENTSHIELD_MTLS_CERT=./certs/vigil_client.crt
AGENTSHIELD_MTLS_KEY=./certs/vigil_client.key
```

- AgentShield validates Vigil's client certificate
- Prevents unauthorized clients from requesting decisions
- Complements signature verification (defense in depth)

## Vigil Verification Flow

1. **Receive decision** from AgentShield `/v1/enforce`
2. **Check required fields**: `signature`, `signature_key_id`
3. **Load public key**:
   - If `AGENTSHIELD_JWKS_URL` is set, fetch from JWKS (cached)
   - Else load pinned key from `AGENTSHIELD_PUBKEY_PATH` or `AGENTSHIELD_PUBKEY_PEM`
4. **Validate context_echo** (if present): match against request `tenant_id`, `agent_id`, `policy_version`
5. **Reconstruct verification payload**:
   - For Ed25519: use `canonical_payload_hash` if provided, else canonical payload
   - For RSA: canonical payload
6. **Verify signature** using Ed25519 or RSA PKCS#1 v1.5 + SHA-256
7. **On success**: Mark `sig_verified=true`, proceed with enforcement
8. **On failure**: Reject decision, return HTTP 503 (fail closed)

## Context Binding

The signature includes **request context** and decision includes **context_echo** to prevent:
- **Cross-tenant attacks**: `context_echo.tenant_id` must match request `tenant_id`
- **Confused deputy**: `context_echo.user_id` must match request `agent_id`
- **Policy bypass**: `context_echo.policy_version` must match request `policy_version`
- **Replay attacks**: `request_id` uniqueness enforced

Vigil validates `context_echo` before signature verification.

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
AGENTSHIELD_JWKS_URL=https://agentshield.prod.example.com/v1/keys/jwks
AGENTSHIELD_JWKS_TTL=3600
AGENTSHIELD_MTLS_CERT=/etc/vigil/certs/client.crt
AGENTSHIELD_MTLS_KEY=/etc/vigil/certs/client.key

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
