# Architecture Diagrams: Before & After

## BEFORE: Monolithic with Embedded Mock

```
┌─────────────────────────────────────────────────────────────────┐
│                     vigil_enhanced_server.py                      │
│                    (1479 lines, ~50KB)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 1-7: Capability Detection, PII Scanning, etc.   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 8: AgentShieldClient (EMBEDDED MOCK)             │   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐  │   │
│  │  │ class AgentShieldClient:                         │  │   │
│  │  │   def __init__(...)                              │  │   │
│  │  │   def _fetch_jwks()                              │  │   │
│  │  │   def _get_public_key()                          │  │   │
│  │  │   def _canonical_payload()                       │  │   │
│  │  │   def _verify_merkle()                           │  │   │
│  │  │   def verify_signature()  ← MOCK LOGIC          │  │   │
│  │  │   def _cached_decision()                         │  │   │
│  │  │   def _store_cache()                             │  │   │
│  │  │   def enforce()           ← MOCK LOGIC          │  │   │
│  │  │                                                  │  │   │
│  │  │ Returns pre-signed mock decision                │  │   │
│  │  │ No real backend called                          │  │   │
│  │  └──────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Layer 9: Semantic Cache & Decision Logging            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                    RETURNS MOCK DECISION
                         (No real backend)
                              │
                              ↓
                      Client Response
```

**Problems**:
- ❌ Hard to test in isolation
- ❌ Can't switch to real backend without major refactor
- ❌ Monolithic (1479 lines)
- ❌ Signature verification is mock
- ❌ Merkle proofs are mock
- ❌ Can't reuse client in other services

---

## AFTER: Decoupled with Real Service Client

```
┌──────────────────────────────────────────┐
│     vigil_enhanced_server.py             │
│        (refactored, ~1400 lines)         │
├──────────────────────────────────────────┤
│                                          │
│  ┌──────────────────────────────────┐  │
│  │  Layers 1-7 (unchanged)          │  │
│  └──────────────────────────────────┘  │
│                    │                    │
│  ┌──────────────────────────────────┐  │
│  │  Layer 8: AgentShield Wrapper    │  │
│  │  (thin, 50 lines)                │  │
│  │                                  │  │
│  │  from vigil.clients import       │  │
│  │    AgentShieldClient as Real...  │  │
│  │                                  │  │
│  │  class AgentShieldClient:        │  │
│  │    def __init__(self, ...):      │  │
│  │      self.client = Real...       │  │
│  │      self.cache = ...            │  │
│  │                                  │  │
│  │    def enforce(self, ...):       │  │
│  │      cache_hit = check_cache()   │  │
│  │      if cache_hit: return        │  │
│  │      response =                  │  │
│  │        self.client.enforce()     │  │
│  │      verify_expiry()             │  │
│  │      store_cache()               │  │
│  │      return response             │  │
│  │                                  │  │
│  └──────────────────────────────────┘  │
│                    │                    │
│  ┌──────────────────────────────────┐  │
│  │  Layers 9 (unchanged)            │  │
│  └──────────────────────────────────┘  │
│                                          │
└──────────────────────────────────────────┘
              │
              │ (semantic cache first)
              │
              ↓
┌──────────────────────────────────────────────────────────────┐
│  src/vigil/clients/agentshield_client.py                     │
│  (300 lines, REAL HTTP CLIENT)                              │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  class AgentShieldClient:                                    │
│                                                               │
│    def __init__(self, base_url, api_key, timeout_ms, ...):  │
│      self.base_url = base_url                               │
│      self.api_key = api_key                                 │
│      self.jwks_cache = {}                                   │
│      self.jwks_cache_ttl = 3600                             │
│                                                               │
│    def enforce(self, payload, metadata):                    │
│      response = requests.post(                              │
│        f"{self.base_url}/v1/enforce",                       │
│        json=payload,                                         │
│        headers={"Authorization": "Bearer ..."},             │
│        timeout=self.timeout                                 │
│      )                                                       │
│      decision = response.json()                             │
│                                                               │
│      if self.require_signed:                                │
│        self._verify_signature(decision)  ← REAL ED25519     │
│                                                               │
│      if self.verify_merkle:                                 │
│        self._verify_merkle_proof(decision)  ← REAL SHA256    │
│                                                               │
│      return decision                                         │
│                                                               │
│    def _verify_signature(self, decision):                   │
│      jwks = self.get_jwks()                                 │
│      key_data = jwks['keys'][0]                             │
│      x_bytes = base64.urlsafe_b64decode(key_data['x'])     │
│      public_key = ed25519.Ed25519PublicKey.from_public_bytes(x_bytes)
│      sig_bytes = base64.b64decode(decision['signature'])    │
│      public_key.verify(sig_bytes, payload_hash)  ← VERIFY   │
│                                                               │
│    def _verify_merkle_proof(self, decision):                │
│      root = self.get_merkle_root()                          │
│      node = leaf_hash                                       │
│      for step in decision['merkle_proof']:                  │
│        sib = base64.urlsafe_b64decode(step['sibling'])      │
│        if step['side'] == 'left':                           │
│          node = hashlib.sha256(sib + node).digest()        │
│        else:                                                 │
│          node = hashlib.sha256(node + sib).digest()        │
│      verify(node == merkle_root)                            │
│                                                               │
│    def get_jwks(self):                                      │
│      if cache_valid: return cached_jwks                     │
│      response = requests.get(f"{self.base_url}/v1/keys/jwks")
│      return response.json()                                  │
│                                                               │
│    def get_merkle_root(self):                               │
│      response = requests.get(f"{self.base_url}/v1/merkle/root")
│      return response.json()                                  │
│                                                               │
│    def health(self):                                        │
│      response = requests.get(f"{self.base_url}/health")     │
│      return response.json()                                  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
              │
              │ HTTP calls with signature verification
              │
              ↓
┌──────────────────────────────────────────────────────────────┐
│              REAL AGENTSHIELD BACKEND (Port 9000)            │
├──────────────────────────────────────────────────────────────┤
│  (Could be mock_agentshield.py or real services/agentshield) │
│                                                               │
│  POST /v1/enforce (request with policies)                   │
│    → Evaluate policies                                       │
│    → Make decision                                           │
│    → Sign with Ed25519 private key                          │
│    → Include Merkle proof                                    │
│    → Return signed decision                                  │
│                                                               │
│  GET /v1/keys/jwks (JWKS endpoint)                          │
│    → Return all Ed25519 public keys                         │
│    → Used for signature verification                        │
│                                                               │
│  GET /v1/merkle/root (Merkle root)                          │
│    → Return current Merkle tree root                        │
│    → Used for proof validation                              │
│                                                               │
│  GET /health (health check)                                 │
│    → Return service status                                  │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Execution Flow: With Real Client

```
HTTP Request to /v1/chat/completions
    │
    ├─ Validate API key
    ├─ Apply layers 1-7 security checks
    │
    ├─ Get messages text
    │
    └─→ Agent.enforce() call
        │
        └─→ AgentShieldClient.enforce(payload, messages_text)
            │
            ├─ Check SemanticDecisionCache
            │   └─ If hit: return cached_decision
            │
            ├─ Call self.client.enforce(payload)
            │   │
            │   └─→ RealAgentShieldClient.enforce()
            │       │
            │       ├─ POST /v1/enforce (with API key)
            │       │
            │       ├─ Verify Ed25519 signature
            │       │   ├─ Fetch JWKS (cached)
            │       │   ├─ Get public key from JWKS
            │       │   ├─ Reconstruct Ed25519PublicKey
            │       │   └─ Verify signature against canonical_payload_hash
            │       │
            │       ├─ Verify Merkle proof
            │       │   ├─ Fetch merkle_root (fresh)
            │       │   ├─ Traverse proof (leaf to root)
            │       │   ├─ Compute hash at each step (SHA256)
            │       │   └─ Verify final node matches merkle_root
            │       │
            │       └─ Return decision with metadata
            │
            ├─ Check decision expiry
            │
            ├─ Store in SemanticDecisionCache (with TTL)
            │
            └─ Return decision

Response to client with:
  ├─ action: "ALLOW" | "BLOCK" | "SANITIZE"
  ├─ risk_score: 0.0-1.0
  ├─ reasons: [...]
  ├─ source: "cache" | "agentshield" | "vigil"
  ├─ cache_hit: true | false | undefined
  └─ signature_verified: true | false (in audit logs)
```

---

## Deployment Progression

### Week 1: Phase 1 (✅ COMPLETE)
```
Old Stack              New Stack
─────────────         ──────────────
vigil_enhanced    →   vigil_enhanced
  (embedded)            (wrapper)
                            ↓
                        Real Client
                      (src/vigil/clients)
                            ↓
                        Mock Backend
                      (still works)
```

**Status**: Backward compatible, all tests pass

---

### Week 2: Phase 2 (🟡 READY)
```
New Stack             Real Stack
──────────────        ──────────────
vigil_enhanced    →   vigil_enhanced
  (wrapper)           (wrapper)
     ↓                     ↓
Real Client       Real Client
     ↓                     ↓
Mock Backend  →   Real Backend
              (clone submodule)
```

**Steps**:
1. Clone agentshield submodule
2. Uncomment docker-compose sections
3. Build real backend image
4. Start services
5. Verify health endpoints
6. Run integration tests

---

## Key Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **File Organization** | Monolithic (1 file) | Modular (clients package) |
| **Testability** | Can't test client separately | Test client independently |
| **Reusability** | Client only in vigil_server | Can import in other services |
| **Backend Switch** | Hard refactor needed | Flip docker-compose config |
| **Real Verification** | Mock only | Real Ed25519 + Merkle |
| **JWKS Caching** | Manual in server | Built into client (3600s) |
| **Signature Check** | Mock implementation | Cryptography library (real) |
| **Merkle Proof** | Mock implementation | SHA256 tree traversal (real) |
| **API Documentation** | In docstrings | Separate client module |
| **Dependency Management** | All in vigil_enhanced_server | Isolated in client |

---

## Integration Status

✅ **Phase 1 Complete**:
- [x] Client created in src/vigil/clients/
- [x] Real HTTP methods (enforce, get_jwks, get_merkle_root, health)
- [x] Signature verification (Ed25519)
- [x] Merkle proof validation (SHA256 tree)
- [x] JWKS caching (3600s TTL)
- [x] vigil_enhanced_server.py refactored
- [x] Semantic cache preserved
- [x] Backward compatible with mock
- [x] Python syntax validated
- [x] Imports tested

🟡 **Phase 2 Ready**:
- [ ] Submodule cloned (awaiting SSH access)
- [ ] docker-compose.prod.yml sections uncommented
- [ ] Real backend deployed
- [ ] Integration tests passing
- [ ] Production ready

---

**Generated**: 2025-12-31  
**Commit**: 30c831f  
**Status**: Architecture refactored successfully
