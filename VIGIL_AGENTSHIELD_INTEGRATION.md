# Vigil ↔ AgentShield Integration Guide

## Executive Summary

**Phase 1: ✅ COMPLETE** - Vigil now has a dedicated AgentShieldClient in `src/vigil/clients/` that works with both mock and real backends.

**Phase 2: 🟡 READY** - Docker Compose and documentation prepared. Awaiting access to real AgentShield repository.

---

## Architecture: Pre & Post Integration

### Before (Monolithic)
```
vigil_enhanced_server.py
├── Embedded AgentShieldClient (mock)
├── Semantic caching
├── Decision signing (mock)
└── Merkle proof validation (mock)
```

### After (Decoupled)
```
vigil-gateway (port 8000)
├── src/vigil/clients/AgentShieldClient (HTTP client)
├── Semantic decision cache
├── Signature verification
└── Merkle proof validation
    ↓ CALLS ↓
agentshield-backend (port 9000)
├── Real policy engine
├── Ed25519 signing
├── Merkle accumulation
├── JWKS endpoint
└── Attestation validation
```

---

## Files Modified / Created

### New Files
| File | Purpose |
|------|---------|
| `src/vigil/clients/__init__.py` | Package initialization, exports AgentShieldClient |
| `src/vigil/clients/agentshield_client.py` | Real client impl: enforce(), get_jwks(), get_merkle_root(), health() |
| `PHASE2_AGENTSHIELD_SETUP.md` | Detailed setup guide with submodule options |
| `VIGIL_AGENTSHIELD_INTEGRATION.md` | This file - architecture & integration overview |

### Modified Files
| File | Changes |
|------|---------|
| `vigil_enhanced_server.py` | Added import: `from vigil.clients import AgentShieldClient as RealAgentShieldClient` → Replaced local class with wrapper |
| `docker-compose.prod.yml` | Added comments showing switch between mock & real backend, prepared env vars |

---

## Phase 1 Details: Service Client Implementation

### AgentShieldClient Class
**Location**: `src/vigil/clients/agentshield_client.py`

#### Core Methods

**`__init__(base_url, api_key, timeout_ms, require_signed, verify_merkle)`**
- Initializes HTTP client
- Sets up JWKS caching (TTL 3600s)
- Configures signature & proof verification

**`enforce(payload, metadata) → Dict`**
- Calls real AgentShield `/v1/enforce`
- Verifies Ed25519 signature on response
- Validates Merkle proof chain
- Checks decision expiry (max 300s)
- Raises `ValueError` if signature/proof invalid and `require_signed=True`

**`get_jwks() → Dict`**
- Fetches public keys from `/v1/keys/jwks`
- Caches for 3600s
- Used for signature verification

**`get_merkle_root() → Dict`**
- Fetches current Merkle root from `/v1/merkle/root`
- Validates proof freshness

**`health() → Dict`**
- Calls `/health` endpoint
- Returns service status

#### Signature Verification
```python
# EdDSA (Ed25519) signature flow:
1. Fetch JWKS from AgentShield
2. Extract public key (OKP, crv=Ed25519, base64url x-coordinate)
3. Reconstruct Ed25519PublicKey from x bytes
4. Verify signature against canonical payload hash
5. Raise ValueError if signature invalid
```

#### Merkle Proof Validation
```python
# Merkle tree traversal:
1. Fetch current root from /v1/merkle/root
2. Verify decision's merkle_root matches current or is in valid proof chain
3. Check proof age (max 300s)
4. Validate each sibling hash (SHA256) on path to root
```

---

## Phase 1 Details: vigil_enhanced_server.py Refactoring

### Old Implementation (Embedded Mock)
```python
class AgentShieldClient:
    def __init__(self, base_url, jwks_url, ...):
        self.base_url = base_url
        # Mock implementation: returns pre-signed decisions
    
    def enforce(self, payload, messages_text):
        # Local mock logic
        return mock_decision()
```

### New Implementation (Real Client Wrapper)
```python
from vigil.clients import AgentShieldClient as RealAgentShieldClient

class AgentShieldClient:
    """Wrapper maintaining backward compatibility with semantic caching."""
    def __init__(self, base_url, jwks_url, timeout_ms, require_signed, required):
        self.client = RealAgentShieldClient(
            base_url=base_url.rstrip('/'),
            api_key=None,  # Uses env var AGENTSHIELD_API_KEY
            timeout_ms=timeout_ms,
            require_signed=require_signed,
            verify_merkle=True,
        )
        self.cache = SemanticDecisionCache(...)  # Semantic caching preserved
    
    def enforce(self, payload, messages_text):
        # Check semantic cache first
        cached = self._cached_decision(messages_text)
        if cached:
            return {"source": "cache", **cached}
        
        # Call real backend
        data = self.client.enforce(payload)
        
        # Verify expiry, store in cache
        self._store_cache(messages_text, data)
        return data
```

### Benefits
✅ **Separation of Concerns**: Client logic isolated in `src/vigil/clients/`
✅ **Testability**: Can test client independently
✅ **Reusability**: Other services can import AgentShieldClient
✅ **Backward Compatibility**: Wrapper maintains semantic caching
✅ **Real Backend Ready**: No code changes needed when real AgentShield is available

---

## Phase 2: Real AgentShield Integration

### Prerequisites

1. **Access to agentshield repository**
   ```bash
   # Verify access (requires SSH key or GitHub token)
   git clone git@github.com:rom-mvp/agentshield.git
   ```

2. **Docker & Docker Compose**
   ```bash
   docker --version   # v20.10+
   docker-compose --version  # v1.29+
   ```

### Option A: SSH Submodule (Recommended)

```bash
cd /workspaces/vigil

# Add submodule
git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield

# Initialize
git submodule update --init --recursive

# Verify
ls -la services/agentshield/
```

### Option B: Local Symlink

```bash
cd /workspaces/vigil/services
ln -s /path/to/local/agentshield agentshield
git add agentshield  # or git config core.symlinks true
```

### Option C: HTTP Mirror (if SSH unavailable)

```bash
# Create local mirror
mkdir -p /tmp/mirrors
cd /tmp/mirrors
git clone --mirror https://github.com/rom-mvp/agentshield.git

# Register in Vigil repo
cd /workspaces/vigil
git submodule add file:///tmp/mirrors/agentshield.git services/agentshield
```

### Docker Compose Switch

In `docker-compose.prod.yml`, uncomment agentshield build section:

**Current (Mock)**:
```yaml
agentshield:
  build:
    context: .
    dockerfile: Dockerfile.agentshield
```

**After Switch (Real)**:
```yaml
agentshield:
  build:
    context: ./services/agentshield
    dockerfile: Dockerfile      # or Dockerfile.prod
  environment:
    - APP_ENV=prod
    - HARDWARE_BACKEND=aws_nitro
    - REDIS_URL=redis://redis:6379
    - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/agentshield
  depends_on:
    - redis
    - postgres
```

### Start Real Stack

```bash
# 1. Ensure submodule is present
git submodule update --init --recursive

# 2. Build all images (may take 5-10 min for real backend)
docker compose -f docker-compose.prod.yml build

# 3. Start services
docker compose -f docker-compose.prod.yml up -d

# 4. Wait for healthy
sleep 15
docker compose -f docker-compose.prod.yml ps

# 5. Verify endpoints
curl http://localhost:8000/health
curl http://localhost:9000/health
curl http://localhost:9000/v1/keys/jwks
```

---

## Environment Variables Reference

### Vigil Gateway
```bash
# Backend
AGENTSHIELD_API_URL=http://agentshield:9000         # Endpoint URL
AGENTSHIELD_API_KEY=<key>                           # Optional auth
AGENTSHIELD_REQUIRE_SIGNED=true                     # Enforce signatures

# Timeouts
AGENTSHIELD_TIMEOUT_MS=5000                         # Request timeout

# Semantic Cache
AGENTSHIELD_CACHE_TTL_SECONDS=300                   # Cache lifetime
AGENTSHIELD_CACHE_SIM_THRESHOLD=0.92                # Similarity threshold

# Transport (for Nitro/TDX vsock)
VIGIL_AGENTSHIELD_TRANSPORT=http                    # http, vsock, grpc
VIGIL_AGENTSHIELD_VSOCK_CID=3                       # Enclave CID
VIGIL_AGENTSHIELD_VSOCK_PORT=5555                   # vsock port
```

### Real AgentShield Backend
```bash
# Environment
APP_ENV=prod                                        # production, dev
HARDWARE_BACKEND=aws_nitro                          # aws_nitro, azure_tdx, none

# Dependencies
REDIS_URL=redis://redis:6379                        # Redis connection string
DATABASE_URL=postgresql://user:pass@host:5432/db    # PostgreSQL connection

# Security
AGENTSHIELD_SIGNING_KEY_PATH=/app/keys/signing.key  # Ed25519 private key
REQUIRE_ATTESTATION=false                           # Enforce Nitro/TDX

# Policies
POLICY_PATH=/app/agentshield_policy.json            # Policy file location

# Key Management
KEY_ROTATION_SECONDS=86400                          # Rotate keys daily
DECISION_TTL_MS_MAX=300000                          # Max decision age (5 min)
```

---

## Testing & Verification

### Unit Test: Client Instantiation
```python
from vigil.clients import AgentShieldClient

client = AgentShieldClient(
    base_url="http://localhost:9000",
    require_signed=True
)
# ✓ Success if no exception
```

### Integration Test: Mock Stack
```bash
docker compose -f docker-compose.prod.yml up -d

python3 << 'EOF'
import requests

# Test Vigil gateway
r = requests.get("http://localhost:8000/health")
assert r.status_code == 200
print("✓ Vigil health OK")

# Test AgentShield mock
r = requests.get("http://localhost:9000/health")
assert r.status_code == 200
print("✓ AgentShield health OK")

# Test enforcement
r = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={"messages": [{"role": "user", "content": "What is 2+2?"}]},
    headers={"Authorization": "Bearer test-key"}
)
assert r.status_code == 200
print("✓ Chat endpoint OK")
EOF
```

### Integration Test: Real Stack
Once submodule is in place, run the same tests. The AgentShieldClient will now:
- Call real `/v1/enforce` endpoint
- Verify real Ed25519 signatures
- Validate Merkle proofs from real backend
- Use semantic caching

---

## Troubleshooting

### Import Error: `No module named 'vigil.clients'`
```bash
# Ensure src is in Python path
export PYTHONPATH=/workspaces/vigil/src:$PYTHONPATH
python3 -c "from vigil.clients import AgentShieldClient"
```

### Submodule Error: "403 Forbidden"
```bash
# SSH setup required:
ssh-keygen -t ed25519
# Add public key to GitHub
git config user.name "Your Name"
git config user.email "your@email.com"
git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield
```

### Signature Verification Failure
```bash
# Check AGENTSHIELD_REQUIRE_SIGNED=true in env
# Verify agentshield /v1/keys/jwks endpoint returns valid keys
curl http://localhost:9000/v1/keys/jwks | jq .
```

### Merkle Proof Invalid
```bash
# Check proof age (max 300s)
# Verify current merkle root matches decision root
curl http://localhost:9000/v1/merkle/root
```

---

## Deployment Checklist

- [ ] Clone/symlink agentshield repository
- [ ] Update `docker-compose.prod.yml` agentshield service (context, dockerfile, env vars)
- [ ] Add Redis and PostgreSQL services (uncomment in compose file)
- [ ] Build images: `docker compose -f docker-compose.prod.yml build`
- [ ] Verify health endpoints respond 200 OK
- [ ] Run integration tests
- [ ] Commit changes: `git add . && git commit -m "Deploy real AgentShield backend"`
- [ ] Push to repository
- [ ] Monitor logs: `docker compose logs -f agentshield`

---

## Next Steps

1. **Immediate** (This Week)
   - Obtain SSH access to rom-mvp/agentshield
   - Clone submodule
   - Build real images
   - Run integration tests

2. **Short Term** (Next Week)
   - Deploy to staging environment
   - Monitor decision latency & cache hit rates
   - Load test with redteam_test.py

3. **Medium Term** (2-4 Weeks)
   - Deploy to production
   - Enable Nitro/TDX attestation (if on AWS/Azure)
   - Monitor metrics via `/analytics/metrics`

---

## Contacts & Resources

- **Vigil Repository**: https://github.com/rom-mvp/vigil
- **AgentShield Repository**: https://github.com/rom-mvp/agentshield (private)
- **Architecture Docs**: See `/docs` directory
- **API Spec**: See `vigil_enhanced_server.py` docstrings

---

Generated: 2025-12-31
Status: Phase 1 Complete, Phase 2 Ready
