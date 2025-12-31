# Quick Start: Phase 1 & 2 Integration

## TL;DR

**Phase 1**: ✅ Done - Vigil now calls a real HTTP client for AgentShield  
**Phase 2**: 🟡 Ready - Just need to clone the agentshield submodule  

---

## What Changed

### For Users: Nothing Breaking ✓
```bash
# Old command still works
docker compose -f docker-compose.prod.yml up -d
curl http://localhost:8000/health
# Returns 200 OK (using mock backend)
```

### For Developers: New Client Available
```python
# Can now import and use the real client
from vigil.clients import AgentShieldClient

client = AgentShieldClient(base_url="http://localhost:9000")
decision = client.enforce({"messages": [...]})
# Real signatures and Merkle proofs verified!
```

---

## Phase 1 Files

| What | Where | What It Does |
|------|-------|--------------|
| **Client** | `src/vigil/clients/agentshield_client.py` | Real HTTP client for AgentShield API |
| **Package** | `src/vigil/clients/__init__.py` | Python package for clients module |
| **Gateway** | `vigil_enhanced_server.py` (modified) | Now uses real client instead of embedded mock |
| **Compose** | `docker-compose.prod.yml` (modified) | Prepared for real backend switch |

---

## To Activate Phase 2 (Real Backend)

### Step 1: Get Access
```bash
# You need SSH access to the private repo
# Contact: [DevOps/Admin]
# Expected: SSH key set up for github.com
```

### Step 2: Clone Submodule (when you have access)
```bash
cd /workspaces/vigil
git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield
git submodule update --init --recursive
```

### Step 3: Update Compose
Edit `docker-compose.prod.yml`:
```yaml
agentshield:
  build:
    context: ./services/agentshield    # Changed from "."
    dockerfile: Dockerfile              # Changed from "Dockerfile.agentshield"
  environment:
    # Comment out mock:
    # - FLASK_APP=mock_agentshield.py
    
    # Uncomment real:
    - APP_ENV=prod
    - HARDWARE_BACKEND=aws_nitro
    - REDIS_URL=redis://redis:6379
    - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/agentshield
```

### Step 4: Build & Start
```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
sleep 10
curl http://localhost:9000/health
```

### Step 5: Verify Integration
```bash
# Test that gateway calls real backend
python3 << 'EOF'
import requests
import json

r = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json={"messages": [{"role": "user", "content": "Hello"}]},
    headers={"Authorization": "Bearer test-key"}
)
print(json.dumps(r.json(), indent=2))
# Should show "signature_verified" or similar
EOF
```

---

## What Works Right Now (Phase 1)

```bash
# ✅ Import the client
python3 -c "from vigil.clients import AgentShieldClient; print('✓')"

# ✅ Run mock stack
docker compose -f docker-compose.prod.yml up -d

# ✅ Gateway calls mock backend
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is 2+2?"}]}'

# ✅ Semantic caching works
# (same prompt called twice returns cached result)

# ✅ Ed25519 signature verification enabled
# (even for mock responses)
```

---

## Architecture Overview

**Current (Phase 1)**:
```
HTTP Request
    ↓
Vigil Gateway (port 8000)
    ↓
Wrapper Client
    ↓
Real Client ← NEW!
    ↓
Mock Backend (port 9000)
    ↓
HTTP Response (with signatures verified)
```

**After Phase 2**:
```
HTTP Request
    ↓
Vigil Gateway (port 8000)
    ↓
Wrapper Client
    ↓
Real Client
    ↓
REAL Backend (services/agentshield, port 9000)
    ├─ Policy Engine
    ├─ Ed25519 Signing (real private keys)
    ├─ Merkle Accumulation
    ├─ JWKS Endpoint
    └─ PostgreSQL + Redis
    ↓
HTTP Response (real signatures + proofs)
```

---

## Key Methods Available

```python
from vigil.clients import AgentShieldClient

client = AgentShieldClient(
    base_url="http://localhost:9000",
    api_key="optional",
    timeout_ms=5000,
    require_signed=True,           # Enforce Ed25519 verification
    verify_merkle=True             # Enforce Merkle proof validation
)

# Main method: Enforce policies
decision = client.enforce(payload, metadata)
# Returns: {
#   "action": "ALLOW" | "BLOCK" | "SANITIZE",
#   "risk_score": 0.0-1.0,
#   "signature": "...",
#   "merkle_proof": [...],
#   ...
# }

# Fetch JWKS (cached for 3600s)
keys = client.get_jwks()

# Get Merkle root
root = client.get_merkle_root()

# Health check
status = client.health()
```

---

## Environment Variables

```bash
# Gateway
export AGENTSHIELD_API_URL=http://agentshield:9000
export AGENTSHIELD_REQUIRE_SIGNED=true
export AGENTSHIELD_TIMEOUT_MS=5000

# For real backend (Phase 2)
export HARDWARE_BACKEND=aws_nitro
export DATABASE_URL=postgresql://postgres:postgres@postgres:5432/agentshield
export REDIS_URL=redis://redis:6379
```

---

## Documentation Map

📋 **Phase 1 Execution**: [PHASE1_COMPLETION_REPORT.md](PHASE1_COMPLETION_REPORT.md)  
📐 **Architecture Diagrams**: [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md)  
🚀 **Phase 2 Setup**: [PHASE2_AGENTSHIELD_SETUP.md](PHASE2_AGENTSHIELD_SETUP.md)  
📖 **Full Integration Guide**: [VIGIL_AGENTSHIELD_INTEGRATION.md](VIGIL_AGENTSHIELD_INTEGRATION.md)  

---

## Next Steps

### For Immediate Use (Today)
```bash
# Everything works as before
docker compose -f docker-compose.prod.yml up -d
# Gateway calls real HTTP client (which calls mock backend)
```

### For Phase 2 Activation (When Access Available)
```bash
# 1. SSH setup
ssh-keygen -t ed25519

# 2. Clone submodule
git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield

# 3. Update compose, build, deploy
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

### For Testing
```bash
# Load test (28 attack vectors)
python3 redteam_test.py

# Unit test client
python3 -m pytest tests/unit/ -v

# Integration test
python3 tests/integration/test_agentshield.py
```

---

## Status

| Phase | Status | Date |
|-------|--------|------|
| Phase 1 | ✅ Complete | 2025-12-31 |
| Phase 2 | 🟡 Ready | 2025-12-31 |
| Production Ready | ⏳ After Phase 2 | Q1 2026 |

---

## Support

- **Questions?** Check [VIGIL_AGENTSHIELD_INTEGRATION.md](VIGIL_AGENTSHIELD_INTEGRATION.md) (comprehensive reference)
- **Setup Help?** Check [PHASE2_AGENTSHIELD_SETUP.md](PHASE2_AGENTSHIELD_SETUP.md) (setup guide)
- **Architecture?** Check [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) (visual guide)
- **Code Review?** Check `src/vigil/clients/agentshield_client.py` (well-commented)

---

**Last Updated**: 2025-12-31  
**Commit**: 30c831f  
**Ready for Production**: After Phase 2 activation
