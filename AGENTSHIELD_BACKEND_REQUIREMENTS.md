# AgentShield Backend Requirements

## Overview

This document specifies what the **AgentShield backend** needs to provide to fully support the Vigil dashboard and audit system.

---

## ✅ What AgentShield Must Provide

### 1. **Signed Decision Endpoint**

**Endpoint:** `POST /v1/enforce`

**Request:**
```json
{
  "request_id": "req-uuid-12345",
  "tenant_id": "ent-tenant",
  "agent_id": "ent-agent",
  "policy_version": "v1",
  "environment": "production",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "metadata": {}
}
```

**Response (Signed):**
```json
{
  "action": "ALLOW",
  "risk_score": 0.12,
  "reasons": ["stub-allow"],
  "context_echo": {
    "request_id": "req-uuid-12345",
    "tenant_id": "ent-tenant",
    "agent_id": "ent-agent",
    "policy_version": "v1",
    "environment": "production"
  },
  "audit_event_id": "evt-abc123",
  "signature": "base64-encoded-ed25519-signature",
  "signature_key_id": "k1",
  "canonical_payload_hash": "sha256-hash-of-decision",
  "issued_at": 1710000000
}
```

**Required Fields:**
- `action`: ALLOW, BLOCK, SANITIZE, CHALLENGE
- `risk_score`: 0.0 - 1.0
- `reasons`: Array of reason codes
- `context_echo`: Full echo of request context (for replay prevention)
- `audit_event_id`: Unique ID for this decision
- `signature`: Ed25519 signature of canonical payload
- `signature_key_id`: Key ID used for signing (e.g., "k1")
- `canonical_payload_hash`: SHA-256 hash of the signed payload
- `issued_at`: Unix timestamp when decision was issued

---

### 2. **JWKS Endpoint (Public Keys)**

**Endpoint:** `GET /v1/keys/jwks`

**Response:**
```json
{
  "keys": [
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "k1",
      "x": "base64-encoded-public-key",
      "alg": "EdDSA",
      "use": "sig"
    },
    {
      "kty": "OKP",
      "crv": "Ed25519",
      "kid": "k0",
      "x": "base64-encoded-public-key",
      "alg": "EdDSA",
      "use": "sig"
    }
  ]
}
```

**Purpose:**
- Vigil fetches public keys from this endpoint to verify signatures
- Supports key rotation (multiple keys with different `kid` values)
- Keys are cached by Vigil with TTL

**Required Fields:**
- `kty`: "OKP" (Octet Key Pair)
- `crv`: "Ed25519"
- `kid`: Key ID (must match `signature_key_id` in decisions)
- `x`: Base64url-encoded public key
- `alg`: "EdDSA"
- `use`: "sig" (signature)

---

### 3. **Health Check Endpoint**

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-03-10T12:00:00Z"
}
```

**Purpose:**
- Vigil checks AgentShield availability
- Used in Kubernetes readiness/liveness probes

---

### 4. **Policy Update Endpoint (Optional)**

**Endpoint:** `POST /v1/policies/update`

**Request:**
```json
{
  "agent_id": "ent-agent",
  "policy_version": 2,
  "max_risk_score": 0.25,
  "disallowed_reasons": ["credential-exfil", "tenant-boundary"]
}
```

**Response:**
```json
{
  "status": "ok",
  "policy_version": 2
}
```

**Purpose:**
- Allow admins to update policy configuration from Vigil dashboard
- AgentShield stores and enforces these policies

---

## 🔒 Security Requirements

### Signature Verification

AgentShield MUST:
1. **Sign every decision** with Ed25519 private key
2. **Include canonical payload hash** (SHA-256 of the signed fields)
3. **Include request context echo** (request_id, tenant_id, agent_id)
4. **Include timestamp** (`issued_at`) for freshness validation
5. **Support key rotation** (multiple active keys in JWKS)

### Replay Attack Prevention

AgentShield MUST:
1. **Echo request context** in `context_echo` field
2. **Include timestamp** in signature payload
3. **Never reuse signatures** across different requests

### Fail-Closed Behavior

AgentShield MUST:
1. **Return BLOCK** on any internal error (never fail-open)
2. **Return 503** if service is unhealthy (never 200 with unsafe decision)

---

## 🔐 Network Security

### Deployment Model

AgentShield should be deployed as:
- **Internal service** (not internet-facing)
- **Private network only** (VPC, cluster-internal)
- **mTLS required** for production (Vigil → AgentShield)

### Example Network Policy (Kubernetes)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agentshield-ingress
  namespace: agentshield-system
spec:
  podSelector:
    matchLabels:
      app: agentshield
  policyTypes:
    - Ingress
  ingress:
    # Only allow Vigil gateway to reach AgentShield
    - from:
        - namespaceSelector:
            matchLabels:
              name: vigil-system
        - podSelector:
            matchLabels:
              app: vigil-gateway
      ports:
        - protocol: TCP
          port: 9000
```

---

## 📊 Audit & Logging

### What AgentShield Should Log

AgentShield should maintain its own audit log with:
- All `/v1/enforce` requests received
- Decision details (action, risk_score, reasons)
- Signature metadata (key_id, hash)
- Request context (tenant_id, agent_id, policy_version)
- Timings (internal processing time)

### Log Format

```json
{
  "timestamp": "2024-03-10T12:00:00Z",
  "request_id": "req-uuid-12345",
  "tenant_id": "ent-tenant",
  "agent_id": "ent-agent",
  "decision": "ALLOW",
  "risk_score": 0.12,
  "reasons": ["stub-allow"],
  "signature_key_id": "k1",
  "processing_time_ms": 7.5
}
```

---

## 🚨 Error Handling

### Error Responses

AgentShield should return structured errors:

```json
{
  "error": {
    "code": "POLICY_VERSION_MISMATCH",
    "message": "Policy version not found",
    "request_id": "req-uuid-12345"
  }
}
```

**Error Codes:**
- `POLICY_VERSION_MISMATCH`: Requested policy version doesn't exist
- `TENANT_NOT_FOUND`: Tenant ID not recognized
- `AGENT_NOT_FOUND`: Agent ID not recognized
- `SIGNING_KEY_UNAVAILABLE`: Cannot sign decision (no active key)
- `INTERNAL_ERROR`: Generic internal error (fail-closed)

---

## 🔄 Key Rotation

### Process

1. **Generate new key pair** (Ed25519)
2. **Add new public key to JWKS** with new `kid` (e.g., "k2")
3. **Start signing with new key** (`signature_key_id: "k2"`)
4. **Keep old key in JWKS** for 24-48 hours (grace period)
5. **Remove old key** after grace period

### Example Rotation

**Before:**
```json
{
  "keys": [
    {"kid": "k1", "x": "..."}
  ]
}
```

**During Rotation:**
```json
{
  "keys": [
    {"kid": "k2", "x": "..."},  // New key (active for signing)
    {"kid": "k1", "x": "..."}   // Old key (verification only)
  ]
}
```

**After Rotation:**
```json
{
  "keys": [
    {"kid": "k2", "x": "..."}   // Only new key remains
  ]
}
```

---

## 📦 Deployment Considerations

### Environment Variables

AgentShield should support:
- `SIGNING_KEY_PATH`: Path to Ed25519 private key file
- `PORT`: Service port (default: 9000)
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARN, ERROR)
- `POLICY_STORAGE`: Policy storage backend (file, database, etc.)

### Health Checks

- **Liveness:** Service is running
- **Readiness:** Service can sign decisions (has active key)

### Metrics

AgentShield should expose metrics (Prometheus format):
- `agentshield_requests_total{decision}`: Total requests by decision type
- `agentshield_risk_score_bucket`: Risk score distribution
- `agentshield_processing_time_seconds`: Processing time percentiles
- `agentshield_signature_failures_total`: Failed signature attempts

---

## 🎯 Summary Checklist

AgentShield Backend Must Provide:

- [ ] POST `/v1/enforce` with signed decisions (Ed25519)
- [ ] GET `/v1/keys/jwks` with public keys (JWKS format)
- [ ] GET `/health` health check endpoint
- [ ] Signature includes: `signature`, `signature_key_id`, `canonical_payload_hash`, `issued_at`
- [ ] Context echo includes: `request_id`, `tenant_id`, `agent_id`, `policy_version`
- [ ] Support for key rotation (multiple keys in JWKS)
- [ ] Fail-closed error handling (BLOCK on error)
- [ ] Internal audit logging
- [ ] Not internet-facing (internal service only)
- [ ] mTLS support for production

---

## 📝 Example AgentShield Implementation (Stub)

See `agentshield_stub_server.py` for a reference implementation that:
- Signs decisions with Ed25519
- Serves JWKS endpoint
- Implements all required fields
- Demonstrates key rotation

Run:
```bash
python agentshield_stub_server.py
```

Then test Vigil integration:
```bash
python test_integration.py
```

---

**This document defines the AgentShield backend contract. All items marked with checkboxes MUST be implemented for production use.**
