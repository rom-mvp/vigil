# Migration Guide: Student Project → Enterprise SaaS

This guide explains how to migrate from the original Vigil architecture to the new SaaS monorepo.

## 🎯 What Changed?

### Before (Original Vigil)
```
/vigil (Single Repo)
├── src/vigil/
│   ├── advanced_threat_detector.py  # Local detection (REMOVED)
│   ├── enclave_transport.py         # Basic HPKE (REPLACED)
│   └── ...
├── test_*.py                         # Scattered tests (MOVED)
└── docker-compose.yml                # Single service (REPLACED)
```

### After (SaaS Monorepo)
```
/vigil-suite (Monorepo)
├── /shared                   # ✅ NEW: Shared schemas
│   ├── schemas/protocol.py
│   ├── crypto/primitives.py
│   └── errors/codes.py
├── /services
│   ├── /vigil-gateway        # ✅ Gateway service
│   └── /agentshield-enclave  # ✅ Enclave service
├── /tests                    # ✅ Organized by type
├── docker-compose.saas.yml   # ✅ Multi-service orchestration
└── Makefile                  # ✅ Common operations
```

## 📋 Migration Checklist

### Step 1: Understand the New Architecture

**Old Flow:**
```
Client → Vigil → LocalDetector → LLM
```

**New Flow:**
```
Client → Gateway (JWT Auth) → Enclave (HPKE Decrypt + Analyze) → Gateway → LLM
                               ↑
                          Tenant-Aware
```

**Key Differences:**
1. **JWT Authentication**: All requests must have valid JWT tokens
2. **Tenant Isolation**: Every request tagged with `tenant_id`
3. **Two Services**: Gateway (public) + Enclave (private)
4. **Shared Schemas**: No more manual dict building

### Step 2: Update Client Code

**Old Client:**
```python
response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer test-key"},
    json={"messages": [...]}
)
```

**New Client (Same!):**
```python
# No changes needed! API is backward-compatible
response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer test-key"},  # JWT in production
    json={"messages": [...]}
)

# Response now includes tenant_id
result = response.json()
print(result["tenant_id"])  # e.g., "tenant_prod_xyz"
```

### Step 3: Deploy with Docker Compose

**Old Command:**
```bash
docker-compose up
```

**New Command:**
```bash
# Use the SaaS orchestration file
docker-compose -f docker-compose.saas.yml up

# Or use Makefile
make up
```

### Step 4: Add Tenant Configuration

Create a tenant policy for each customer:

```python
from shared.schemas.governance import TenantPolicy

# Free tier
free_tenant = TenantPolicy(
    tenant_id="tenant_free_001",
    monthly_budget_usd=10.0,
    requests_per_minute=10,
    tier="free"
)

# Pro tier
pro_tenant = TenantPolicy(
    tenant_id="tenant_pro_002",
    monthly_budget_usd=500.0,
    requests_per_minute=120,
    tier="pro"
)
```

Store in Redis or PostgreSQL for persistence.

### Step 5: Enable JWT Authentication

**Local Development (Mock):**
```bash
# Uses test-key for local dev
export VIGIL_ENV=local
./start.sh
```

**Production (Real JWT):**
```bash
# Configure Auth0/Clerk/Cognito
export AUTH_JWKS_URL=https://auth.vigil.ai/.well-known/jwks.json
export AUTH_ISSUER=https://auth.vigil.ai
export AUTH_AUDIENCE=vigil-api
export VIGIL_ENV=production

docker-compose -f docker-compose.saas.yml up
```

## 🔧 Code Migration Examples

### Example 1: Using Shared Schemas

**Old Code (Manual Dict):**
```python
packet = {
    "request_id": "req_123",
    "payload": json.dumps(data),
    "timestamp": time.time()
}
```

**New Code (Pydantic Schema):**
```python
from shared.schemas.protocol import EnclaveRequest

packet = EnclaveRequest(
    request_id="req_123",
    tenant_id=tenant_id,  # NEW: Required field
    agent_id=agent_id,
    payload_encrypted=encrypted_blob,
    timestamp=time.time()
)
```

### Example 2: Tenant-Aware Enforcement

**Old Code (No Tenant Context):**
```python
if check_threat(prompt):
    return {"error": "Blocked"}
```

**New Code (Tenant-Aware):**
```python
from services.agentshield_enclave.governance_saas import tenant_governance

# Check rate limit and budget
tenant_governance.enforce_tenant_isolation(
    tenant_id=request.tenant_id,
    agent_id=request.agent_id,
    estimated_cost=0.001
)

if check_threat(prompt):
    # Record blocked request for tenant metrics
    tenant_governance.usage_metrics[tenant_id].blocked_requests += 1
    return {"error": "Blocked", "tenant_id": tenant_id}
```

### Example 3: Error Handling

**Old Code (Generic Errors):**
```python
if quota_exceeded:
    raise Exception("Quota exceeded")
```

**New Code (Standard Error Codes):**
```python
from shared.errors import QuotaExceededError

if quota_exceeded:
    raise QuotaExceededError(
        tenant_id=tenant_id,
        quota_type="requests"
    )
```

## 🧪 Testing Migration

### Run Old Tests
```bash
# Old test structure still works
pytest tests/unit/test_guardrails.py
```

### Run New Tests
```bash
# New organized structure
make test-unit
make test-integration
```

## 🚀 Deployment Checklist

- [ ] Set up Auth0/Clerk/Cognito for JWT tokens
- [ ] Configure Redis for policy cache
- [ ] Set `ENCLAVE_URL` to AgentShield service
- [ ] Enable `VIGIL_STRICT_MODE=true` in production
- [ ] Configure tenant policies in database
- [ ] Set up monitoring (health checks on `/health`)
- [ ] Enable signature verification (Ed25519)
- [ ] Configure rate limiting per tier
- [ ] Set up billing webhooks (usage export)

## ⚠️ Breaking Changes

### 1. Removed `advanced_threat_detector.py`
**Impact:** Local threat detection is now in AgentShield Enclave  
**Migration:** Use `enclave_transport_saas.py` instead

### 2. Required `tenant_id` Field
**Impact:** All requests must include tenant context  
**Migration:** Extract from JWT token using `jwt_auth.require_auth`

### 3. Two-Service Architecture
**Impact:** Gateway and Enclave run as separate containers  
**Migration:** Use `docker-compose.saas.yml` for orchestration

### 4. Schema Validation
**Impact:** All payloads validated against Pydantic models  
**Migration:** Import from `shared.schemas.protocol`

## 📚 Further Reading

- [MONOREPO_README.md](MONOREPO_README.md) - Full architecture guide
- [shared/schemas/protocol.py](shared/schemas/protocol.py) - API contract
- [shared/errors/codes.py](shared/errors/codes.py) - Error codes
- [Makefile](Makefile) - All available commands

## 🆘 Troubleshooting

### Gateway can't reach Enclave
```bash
# Check Docker network
docker network inspect vigil-suite_secure-mesh

# Check Enclave is running
docker ps | grep agentshield-enclave

# Check logs
docker logs agentshield-enclave
```

### JWT validation failing
```bash
# Check environment variables
echo $AUTH_JWKS_URL
echo $AUTH_ISSUER

# Use test mode for local dev
export VIGIL_ENV=local
```

### Tests failing
```bash
# Install shared dependencies
pip install -e shared/

# Run with verbose output
pytest tests/unit -vv
```

---

**Questions?** Open an issue or email: suladesada@gmail.com
