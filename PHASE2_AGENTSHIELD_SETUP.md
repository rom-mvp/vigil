# Phase 2: Real AgentShield Integration

## Overview
This document outlines the two-phase decoupling of the mock AgentShield from Vigil and integration of the real AgentShield backend.

## Phase 1 Status: ✅ COMPLETE

### Step 1-3: Service Client Created
- Created `/src/vigil/clients/` directory structure
- Implemented `AgentShieldClient` class in `/src/vigil/clients/agentshield_client.py`
- Features:
  - Ed25519 signature verification
  - Merkle proof validation
  - JWKS caching with TTL
  - Replay detection
  - Attestation support
  - HTTP request handling with timeout

### Step 3: Import Refactored
- Updated `vigil_enhanced_server.py`:
  - Import: `from vigil.clients import AgentShieldClient as RealAgentShieldClient`
  - Replaced local `AgentShieldClient` with wrapper around `RealAgentShieldClient`
  - Maintains semantic caching and backward compatibility
  - Now calls real backend at `AGENTSHIELD_API_URL`

## Phase 2 Status: 🟡 IN PROGRESS

### Step 4: Git Submodule Setup
The real AgentShield repository is not publicly accessible. 

**Option A: SSH Access (Recommended)**
```bash
cd /workspaces/vigil
git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield
git submodule update --init --recursive
```

**Option B: Local Development**
If you have the AgentShield repository locally, you can:
```bash
cd /workspaces/vigil/services
ln -s /path/to/local/agentshield agentshield
```

**Option C: Mirror Repository**
```bash
# Create a mirror in your workspace
mkdir -p /tmp/agentshield-mirror
cd /tmp/agentshield-mirror
git clone --mirror https://github.com/rom-mvp/agentshield.git
cd /workspaces/vigil
git submodule add file:///tmp/agentshield-mirror/agentshield.git services/agentshield
```

### Step 5: Docker Compose Update Required

Once the submodule is in place, update `docker-compose.prod.yml`:

```yaml
services:
  vigil:
    build: .
    ports:
      - "8000:8000"
    environment:
      - AGENTSHIELD_API_URL=http://agentshield:9000
      - AGENTSHIELD_REQUIRE_SIGNED=true
    depends_on:
      - agentshield
      - redis
      - postgres

  agentshield:
    build:
      context: ./services/agentshield  # Real repo
      dockerfile: Dockerfile.prod      # or Dockerfile.agentshield
    ports:
      - "9000:9000"
    environment:
      - APP_ENV=prod
      - HARDWARE_BACKEND=aws_nitro     # Enable TEE detection
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/agentshield
      - AGENTSHIELD_SIGNING_KEY_PATH=/app/keys/signing.key
      - REQUIRE_ATTESTATION=false      # Set to true for Nitro
    depends_on:
      - redis
      - postgres
    volumes:
      - ./services/agentshield/keys:/app/keys:ro

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=agentshield
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Environment Variables

### Vigil Gateway
```bash
AGENTSHIELD_API_URL=http://agentshield:9000         # Real backend URL
AGENTSHIELD_API_KEY=<key>                           # Optional API key
AGENTSHIELD_REQUIRE_SIGNED=true                     # Require Ed25519 sigs
AGENTSHIELD_TIMEOUT_MS=5000                        # Request timeout
AGENTSHIELD_CACHE_TTL_SECONDS=300                  # Semantic cache TTL
AGENTSHIELD_CACHE_SIM_THRESHOLD=0.92               # Cache similarity threshold
```

### Real AgentShield Backend
```bash
APP_ENV=prod                                        # Production mode
HARDWARE_BACKEND=aws_nitro                         # TEE detection (aws_nitro, azure_tdx)
REDIS_URL=redis://redis:6379                       # Redis connection
DATABASE_URL=postgresql://...                      # PostgreSQL connection
AGENTSHIELD_SIGNING_KEY_PATH=/app/keys/signing.key # Ed25519 key location
REQUIRE_ATTESTATION=false                          # Require attestation (Nitro/TDX)
```

## Testing Phase 2

Once submodule and compose are updated:

```bash
# Initialize submodule
git submodule update --init --recursive

# Start services
docker compose -f docker-compose.prod.yml up -d

# Wait for services
sleep 10

# Check health
curl http://localhost:8000/health
curl http://localhost:9000/health

# Test enforcement
python3 << 'EOF'
import requests
import json

payload = {
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "policies": ["default"]
}

resp = requests.post(
    "http://localhost:8000/v1/chat/completions",
    json=payload,
    headers={"Authorization": "Bearer test-key"}
)
print(json.dumps(resp.json(), indent=2))
EOF
```

## Expected Behavior

After Phase 2 integration:

1. **Vigil Gateway** (port 8000)
   - Receives incoming requests
   - Calls real AgentShield at port 9000
   - Verifies Ed25519 signatures from AgentShield
   - Validates Merkle proofs
   - Caches decisions semantically

2. **Real AgentShield** (port 9000)
   - Evaluates policies
   - Signs decisions with Ed25519
   - Provides Merkle accumulation
   - Tracks key rotation
   - Logs decision metadata

3. **Shared Infrastructure**
   - Redis: Session/replay tracking
   - PostgreSQL: Audit logging
   - Health checks: Both endpoints report 200 OK

## Known Limitations

- Submodule requires SSH or local access
- Dockerfile in real AgentShield must support `Dockerfile.prod` naming
- TEE integration currently stubbed (vsock/Nitro requires host support)
- Tests may need API key env var

## Next Steps

1. [ ] Obtain access to github.com/rom-mvp/agentshield repository
2. [ ] Clone submodule: `git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield`
3. [ ] Update docker-compose.prod.yml with real backend build context
4. [ ] Run `docker compose -f docker-compose.prod.yml build`
5. [ ] Start services: `docker compose -f docker-compose.prod.yml up -d`
6. [ ] Verify health endpoints respond 200
7. [ ] Run integration tests
8. [ ] Commit changes: `git add . && git commit -m "Decouple mock, add real AgentShield submodule"`
