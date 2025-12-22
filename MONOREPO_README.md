# Vigil SaaS Monorepo Structure

This monorepo contains the complete Vigil security platform, organized for enterprise SaaS deployment.

## 📁 Directory Structure

```
/vigil-suite (Root)
├── /shared                     # Shared libraries (The Contract)
│   ├── /schemas                # Pydantic models for protocol
│   ├── /crypto                 # HPKE/Ed25519 cryptography
│   └── /errors                 # Standard error codes
├── /services
│   ├── /vigil-gateway          # Public-facing API gateway
│   └── /agentshield-enclave    # Secure threat detection vault
├── /deploy                     # Infrastructure as Code
├── /docs                       # Architecture diagrams
├── /tests                      # Organized test suite
├── docker-compose.saas.yml     # SaaS orchestration
└── Makefile                    # Common operations
```

## 🏗️ Architecture

### The Two-Service Model

**Vigil Gateway** (The "Dumb" Forwarder)
- Public-facing HTTP API on port 8000
- JWT authentication and tenant extraction
- HPKE encryption of payloads
- Blind forwarding to enclave (cannot read content)

**AgentShield Enclave** (The "Smart" Vault)
- Hidden backend (no exposed ports)
- HPKE decryption inside secure boundary
- Threat detection engines (firewall, ML, vector)
- Multi-tenant governance and budget enforcement
- Ed25519 signature of all decisions

```
┌─────────────┐     HPKE      ┌──────────────────┐
│   Client    │────Encrypted──▶│ Vigil Gateway    │
│  (JWT Auth) │                │ (Port 8000)      │
└─────────────┘                └───────┬──────────┘
                                       │ VSOCK/HTTP
                                       ▼
                              ┌────────────────────┐
                              │ AgentShield        │
                              │ (Hidden Enclave)   │
                              │ - Decrypt          │
                              │ - Analyze          │
                              │ - Sign Decision    │
                              └────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.10+
- `make` (optional, for convenience)

### Start the Platform

```bash
# Option 1: Using Makefile
make build
make up

# Option 2: Direct Docker Compose
docker-compose -f docker-compose.saas.yml up --build

# Check health
curl http://localhost:8000/health
```

### Send a Test Request

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Hello world"}]
  }'
```

## 🧩 The Shared Contract

All communication between services uses **shared Pydantic schemas** to prevent drift.

### EnclaveRequest (Gateway → Enclave)

```python
from shared.schemas.protocol import EnclaveRequest

packet = EnclaveRequest(
    request_id="req_123",
    tenant_id="tenant_prod_xyz",  # SaaS tenant ID
    agent_id="agent_001",
    payload_encrypted="<base64-hpke-blob>",
    timestamp=1703203200.0
)
```

### EnclaveResponse (Enclave → Gateway)

```python
from shared.schemas.protocol import EnclaveResponse

response = EnclaveResponse(
    request_id="req_123",
    decision="ALLOW",
    risk_score=0.12,
    reasons=["clean"],
    latency_ms=15.3,
    signature="<ed25519-signature>",
    signature_key_id="key_001",
    tenant_id="tenant_prod_xyz",
    cost_estimate=0.0015
)
```

## 🛡️ Multi-Tenant Governance

Each tenant has isolated quotas and policies:

```python
from shared.schemas.governance import TenantPolicy

policy = TenantPolicy(
    tenant_id="tenant_prod_xyz",
    monthly_budget_usd=500.0,
    requests_per_minute=120,
    tokens_per_day=5_000_000,
    tier="pro"
)
```

Enforced in `agentshield-enclave/governance_saas.py`:
- **Rate limiting**: Per-tenant request throttling
- **Budget enforcement**: Prevents overspend
- **Usage tracking**: Real-time metering for billing

## 🔐 JWT Authentication

Gateway validates JWT tokens and extracts tenant context:

```python
from vigil.middleware import jwt_auth

@app.route("/v1/chat/completions")
@jwt_auth.require_auth  # Enforces JWT validation
def chat_endpoint():
    tenant_id = request.tenant_id  # Extracted from token
    user_id = request.user_id
    ...
```

Token structure (Auth0/Clerk/Cognito):
```json
{
  "sub": "user_123",
  "org_id": "tenant_prod_xyz",  // Maps to tenant_id
  "email": "user@example.com",
  "exp": 1703203200
}
```

## 📦 Makefile Commands

```bash
make build              # Build Docker images
make up                 # Start all services
make down               # Stop services
make logs               # View logs
make test               # Run all tests
make test-unit          # Unit tests only
make test-integration   # Integration tests
make clean              # Remove containers & volumes
```

## 🧪 Testing

### Unit Tests
```bash
pytest tests/unit -v
```

### Integration Tests
```bash
pytest tests/integration -v
```

### Load Tests
```bash
pytest tests/performance -v
```

## 🏢 Production Deployment

### AWS Nitro Enclaves

```bash
# Build secure enclave image
docker build -f services/agentshield-enclave/Dockerfile.nitro \
  -t agentshield-enclave:nitro .

# Convert to EIF (Enclave Image Format)
nitro-cli build-enclave \
  --docker-uri agentshield-enclave:nitro \
  --output-file agentshield.eif
```

### Kubernetes

```bash
kubectl apply -f deploy/k8s/vigil-gateway.yaml
kubectl apply -f deploy/k8s/agentshield-enclave.yaml
```

## 🔒 Security Considerations

### Distroless Images
- **No shell** (`/bin/bash`, `/bin/sh` removed)
- **No package manager** (apt, yum removed)
- **Minimal attack surface** (only Python runtime)

### Network Isolation
- AgentShield has **no exposed ports** to host
- Only accessible via Docker network or VSOCK
- Gateway cannot decrypt enclave responses (blind forwarding)

### Supply Chain Security
- Reproducible builds (Dockerfile.nitro)
- Signed images (TODO: add Cosign signatures)
- SBOM generation (TODO: add Syft)

## 📚 Documentation

- [Protocol Schemas](shared/schemas/protocol.py)
- [Governance Schemas](shared/schemas/governance.py)
- [Cryptography](shared/crypto/primitives.py)
- [Error Codes](shared/errors/codes.py)

## 🤝 Contributing

1. Add features to `/shared` if used by both services
2. Update schemas in `/shared/schemas` for API changes
3. Run `make test` before committing
4. Follow Pydantic models for all data structures

## 📄 License

MIT License - See LICENSE file
