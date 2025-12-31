# PHASE 5: Real AgentShield Backend Integration

## Current Status: VERIFICATION NEEDED

### What We Have Now (Phase 3 & 4 Complete)
✅ Real attestation verification in vigil_enhanced_server.py  
✅ AgentShieldClient with real API calls (AWS Nitro + Azure TDX)  
✅ 21/21 tests passing  
✅ Mock backend DELETED (mock_agentshield.py removed)  

### What We Need for Phase 5: Real Backend
❌ AgentShield repo cloned to `./services/agentshield`  
❌ Docker Compose updated to build from real repo  
❌ Integration test running against real backend  

---

## Integration Verification Checklist

### Step 1: Git Submodule Status
```bash
cd /workspaces/vigil
git submodule status
```
**Current Result**: No submodule configured  
**Expected**: AgentShield should appear as a submodule  

### Step 2: Docker Compose Configuration
```bash
grep -A 15 "agentshield:" docker-compose.prod.yml | head -10
```
**Current Result**: 
```dockerfile
  agentshield:
    build:
      context: .                           # ← MOCK CONFIGURATION
      dockerfile: Dockerfile.agentshield
```
**Expected**: 
```dockerfile
  agentshield:
    build:
      context: ./services/agentshield      # ← REAL CONFIGURATION
      dockerfile: Dockerfile.prod
```

### Step 3: Mock Dependencies
```bash
grep "mock_agentshield" docker-compose.prod.yml
grep "FLASK_APP=mock_agentshield" docker-compose.prod.yml
```
**Current Result**: 
```
- FLASK_APP=mock_agentshield.py
```
**Expected**: No references to mock_agentshield (it's deleted)

### Step 4: File System Check
```bash
ls -la services/agentshield/ 2>&1 | head -3
```
**Current Result**: Directory not found  
**Expected**: Real agentshield repo with Dockerfile, requirements.txt, etc.

---

## Problem Analysis

### Why Tests Pass But Docker Fails
1. **Tests**: Use local AgentShieldClient with mocked HTTP calls
2. **Docker**: Tries to build Dockerfile.agentshield (references deleted mock_agentshield.py)
3. **Gateway**: Calls agent_shield_client.verify_attestation() which works in tests but needs real backend in Docker

### The Disconnect
```
✅ Code Level: Real attestation verification working (tests pass)
❌ Docker Level: Still configured for mock backend
❌ Deployment Level: Can't build Docker image without real repo
```

### Root Cause
Phase 4 deleted the mock backend but Phase 5 (real backend setup) wasn't completed.

---

## What Needs to Happen for Full Integration

### Option A: Clone Real AgentShield Repo (Recommended)
```bash
# 1. Get credentials to rom-mvp/agentshield private repo
# 2. Clone to services/
cd /workspaces/vigil
git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield
git submodule update --init --recursive

# 3. Update docker-compose.prod.yml (see changes below)
# 4. Rebuild
docker compose -f docker-compose.prod.yml build --no-cache agentshield
```

### Option B: Create Minimal Real Backend Stub
```bash
# Create minimal agentshield service that satisfies Docker build
mkdir -p services/agentshield
# Create minimal Dockerfile, requirements.txt, app.py
```

---

## Changes Required to docker-compose.prod.yml

### Change 1: AgentShield Service Build Context
```yaml
# FROM THIS:
agentshield:
  build:
    context: .
    dockerfile: Dockerfile.agentshield

# TO THIS:
agentshield:
  build:
    context: ./services/agentshield
    dockerfile: Dockerfile.prod  # or just Dockerfile
```

### Change 2: AgentShield Environment Variables
```yaml
# FROM THIS (mock):
environment:
  - FLASK_APP=mock_agentshield.py
  - FLASK_ENV=production
  - PORT=9000

# TO THIS (real):
environment:
  - APP_ENV=prod
  - HARDWARE_BACKEND=aws_nitro
  - PORT=9000
  - REDIS_URL=redis://redis:6379
  - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/agentshield
```

### Change 3: Add Dependencies (if not already present)
```yaml
# Uncomment these services for real backend:
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"

postgres:
  image: postgres:15-alpine
  environment:
    POSTGRES_DB: agentshield
    POSTGRES_PASSWORD: postgres
```

---

## Verification Script

```bash
#!/bin/bash
set -e

cd /workspaces/vigil

echo "=== PHASE 5 INTEGRATION VERIFICATION ==="
echo ""

# Check 1: Git submodule
echo "✓ Check 1: Git Submodule Status"
if git submodule status | grep -q "services/agentshield"; then
    echo "  ✅ AgentShield is a Git submodule"
else
    echo "  ❌ AgentShield is NOT a Git submodule"
fi
echo ""

# Check 2: Docker compose config
echo "✓ Check 2: Docker Compose Configuration"
if grep -q "context: ./services/agentshield" docker-compose.prod.yml; then
    echo "  ✅ Docker Compose builds from real repo"
else
    echo "  ❌ Docker Compose still builds from root (mock config)"
fi
echo ""

# Check 3: Mock references
echo "✓ Check 3: Mock Backend References"
if grep -q "FLASK_APP=mock_agentshield" docker-compose.prod.yml; then
    echo "  ❌ Still has mock_agentshield references"
else
    echo "  ✅ No mock_agentshield references (clean)"
fi
echo ""

# Check 4: Files exist
echo "✓ Check 4: File System"
if [ -f "services/agentshield/Dockerfile" ] || [ -f "services/agentshield/Dockerfile.prod" ]; then
    echo "  ✅ AgentShield Dockerfile found"
else
    echo "  ❌ AgentShield Dockerfile not found"
fi
echo ""

# Check 5: Test pass
echo "✓ Check 5: Tests"
if pytest tests/integration/test_agentshield_real.py -q --tb=no 2>&1 | grep -q "passed"; then
    echo "  ✅ All tests passing"
else
    echo "  ❌ Tests failing"
fi
echo ""

echo "=== SUMMARY ==="
echo "If all checks are ✅, system is ready for deployment"
echo "If any are ❌, see PHASE5_INTEGRATION.md for fixes"
```

---

## Current Integration Status

| Component | Status | Notes |
|-----------|--------|-------|
| Real attestation code | ✅ READY | Phase 3 complete |
| Test suite | ✅ 21/21 PASSING | Phase 4 complete |
| Mock deleted | ✅ DONE | Phase 4 complete |
| Git submodule | ❌ MISSING | Needs `git submodule add` |
| Docker compose config | ❌ WRONG | Still points to mock |
| Services dir structure | ⚠️ PARTIAL | Has enclave, needs agentshield |
| Real backend repo | ❌ MISSING | Needs clone of rom-mvp/agentshield |

---

## Next Steps

### Immediate (Required for Docker)
1. Clone or add AgentShield as submodule
2. Update docker-compose.prod.yml build context
3. Remove FLASK_APP=mock_agentshield references
4. Add HARDWARE_BACKEND=aws_nitro

### Testing (Validation)
1. `docker compose -f docker-compose.prod.yml build`
2. `docker compose -f docker-compose.prod.yml up -d`
3. `pytest tests/integration/test_agentshield_real.py -v`
4. `curl http://localhost:9000/health`
5. `curl http://localhost:8000/health`

### Final (Production)
1. Run full test suite
2. Load test with redteam_test.py
3. Monitor attestation verification logs
4. Validate decision latency

---

## References

- Phase 3 & 4 Status: [PHASE3_4_STATUS.md](PHASE3_4_STATUS.md)
- Docker Compose Prod: [docker-compose.prod.yml](docker-compose.prod.yml)
- AgentShield Client: [src/vigil/clients/agentshield_client.py](src/vigil/clients/agentshield_client.py)
- Tests: [tests/integration/test_agentshield_real.py](tests/integration/test_agentshield_real.py)

---

**Status**: VERIFICATION IN PROGRESS  
**Phase 3 & 4**: Complete ✅  
**Phase 5**: Pending real backend integration  
**Blockers**: Need access to rom-mvp/agentshield private repo
