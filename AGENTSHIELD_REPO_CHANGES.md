# What You Need to Change in the AgentShield Repo

This is a checklist for making your separate **agentshield** backend repo production-ready to work with Vigil.

## 📋 Quick Summary

**Vigil repo (✅ DONE):**
- Full enforcement gateway
- Real Ed25519 signing in mock
- Policy rules that actually block threats
- Smoke test suite
- Complete documentation

**AgentShield repo (⚠️ YOU NEED TO DO):**
- Replace mock with real backend
- Implement these endpoints: POST /v1/enforce, GET /v1/keys/jwks, GET /health
- Add ML-based threat detection
- Add TEE/enclave support (optional but recommended for banks)

---

## 🚀 STEP 1: Repository Structure

Create this structure in your agentshield repo:

```
agentshield/
├── src/
│   ├── main.py                 # FastAPI server (NEW)
│   ├── policy_engine.py        # Policy evaluation logic (NEW)
│   ├── signing.py              # Ed25519 signing (NEW)
│   ├── threat_detector.py      # ML threat detection (NEW)
│   ├── enclave.py              # TEE integration (OPTIONAL)
│   └── analytics.py            # Analytics endpoints (NEW)
├── policies/
│   └── default.json            # Default policy rules (NEW)
├── models/
│   └── threat_model.pkl        # ML model weights (NEW)
├── Dockerfile                  # Production container (NEW)
├── requirements.txt            # Python dependencies (NEW)
├── docker-compose.yml          # Standalone deployment (NEW)
└── README.md                   # Documentation (UPDATE)
```

---

## 🔧 STEP 2: Implement Core Endpoints

### File: `src/main.py`

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
from .policy_engine import PolicyEngine
from .signing import SigningService
from .analytics import AnalyticsService

app = FastAPI(title="AgentShield Backend")

# Initialize services
policy_engine = PolicyEngine()
signing_service = SigningService()
analytics_service = AnalyticsService()

@app.post("/v1/enforce")
async def enforce(request: Request):
    """
    Main enforcement endpoint.
    See AGENTSHIELD_REQUIREMENTS.md in vigil repo for full spec.
    """
    data = await request.json()
    
    # Extract fields
    request_id = data.get("request_id")
    messages = data.get("messages", [])
    tenant_id = data.get("tenant_id")
    policy_id = data.get("policy_id", "default-policy")
    
    # Evaluate threat
    action, risk_score, reasons = policy_engine.evaluate(
        messages=messages,
        policy_id=policy_id,
        tenant_id=tenant_id
    )
    
    # Build decision
    decision = {
        "schema_version": "as_decision_v1",
        "action": action,
        "risk_score": risk_score,
        "reasons": reasons,
        "issued_at": int(time.time()),
        "ttl_ms": data.get("ttl_ms", 300000),
        "context_echo": {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "agent_id": data.get("agent_id"),
            "policy_id": policy_id,
            "policy_version": data.get("policy_version", 1),
            "input_hash": data.get("input_hash"),
            "timestamp_ms": data.get("timestamp_ms"),
            "environment": data.get("environment", "production")
        },
        "audit_event_id": f"evt-{int(time.time())}"
    }
    
    # Sign decision
    signature = signing_service.sign(decision)
    decision["signature"] = signature["signature"]
    decision["signature_key_id"] = signature["key_id"]
    decision["canonical_payload_hash"] = signature["payload_hash"]
    
    # Record analytics
    analytics_service.record(decision)
    
    return JSONResponse(content=decision)

@app.get("/v1/keys/jwks")
async def jwks():
    """Return JWKS public keys."""
    return signing_service.get_jwks()

@app.get("/health")
async def health():
    """Health check."""
    return {
        "status": "ok",
        "service": "agentshield",
        "uptime_seconds": time.time() - START_TIME,
        "decision_signing": {
            "schema_version": "as_decision_v1",
            "key_id": signing_service.key_id,
            "ready": True
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

# Add analytics endpoints (dashboard, metrics, logs, threats)
# See AGENTSHIELD_REQUIREMENTS.md for full spec
```

---

## 🛡️ STEP 3: Policy Engine

### File: `src/policy_engine.py`

```python
import re
import json
from typing import Tuple, List

class PolicyEngine:
    def __init__(self, policy_path="policies/default.json"):
        with open(policy_path) as f:
            self.policy = json.load(f)
        
        self.rules = self.policy.get("rules", [])
    
    def evaluate(self, messages: List[dict], policy_id: str, tenant_id: str) -> Tuple[str, float, List[str]]:
        """
        Evaluate messages against policy rules.
        Returns (action, risk_score, reasons)
        """
        all_text = " ".join([msg.get("content", "") for msg in messages])
        
        max_risk = 0.0
        reasons = []
        
        # Pattern-based rules
        for rule in self.rules:
            pattern = rule.get("pattern")
            if pattern and re.search(pattern, all_text, re.IGNORECASE):
                reasons.append(rule["reason"])
                max_risk = max(max_risk, rule["risk_score"])
        
        # ML-based detection (ADD THIS)
        # ml_risk = self.ml_model.predict(all_text)
        # if ml_risk > 0.8:
        #     reasons.append("ml-detected-threat")
        #     max_risk = max(max_risk, ml_risk)
        
        # Decision logic
        if max_risk >= 0.8:
            return "BLOCK", max_risk, reasons
        elif max_risk >= 0.5:
            return "SANITIZE", max_risk, reasons
        else:
            return "ALLOW", max(max_risk, 0.05), reasons if reasons else ["clean"]
```

---

## 🔐 STEP 4: Signing Service

### File: `src/signing.py`

```python
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import json
import base64
import hashlib

class SigningService:
    def __init__(self):
        # Generate or load Ed25519 key
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        self.key_id = "k1"
        
        # Export public key for JWKS
        self.public_key_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    
    def sign(self, decision: dict) -> dict:
        """Sign a decision and return signature data."""
        # Create canonical payload
        canonical_payload = {
            "action": decision["action"],
            "risk_score": decision["risk_score"],
            "reasons": decision["reasons"],
            "context_echo": decision["context_echo"],
            "audit_event_id": decision["audit_event_id"],
            "issued_at": decision["issued_at"]
        }
        
        # Canonicalize JSON
        canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(',', ':'))
        
        # Hash payload
        payload_hash = hashlib.sha256(canonical_json.encode()).digest()
        
        # Sign with Ed25519
        signature_bytes = self.private_key.sign(canonical_json.encode())
        
        return {
            "signature": base64.urlsafe_b64encode(signature_bytes).decode().rstrip('='),
            "key_id": self.key_id,
            "payload_hash": base64.urlsafe_b64encode(payload_hash).decode().rstrip('=')
        }
    
    def get_jwks(self) -> dict:
        """Return JWKS public keys."""
        x_coord = base64.urlsafe_b64encode(self.public_key_bytes).decode().rstrip('=')
        
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "kid": self.key_id,
                    "x": x_coord,
                    "use": "sig"
                }
            ]
        }
```

---

## 📦 STEP 5: Requirements

### File: `requirements.txt`

```txt
fastapi==0.109.0
uvicorn==0.27.0
pydantic==2.5.3
cryptography==42.0.0
redis==5.0.1
transformers==4.36.0  # For ML threat detection
torch==2.1.2          # For ML models
presidio-analyzer==2.2.33
presidio-anonymizer==2.2.33
prometheus-client==0.19.0
```

---

## 🐳 STEP 6: Dockerfile

### File: `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY policies/ ./policies/
COPY models/ ./models/

# Expose port
EXPOSE 9000

# Run server
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

---

## 🚀 STEP 7: Docker Compose

### File: `docker-compose.yml`

```yaml
version: '3.8'

services:
  agentshield:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "9000:9000"
    environment:
      - POLICY_PATH=/app/policies/default.json
      - ML_MODEL_PATH=/app/models/threat_model.pkl
      - REDIS_URL=redis://redis:6379
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:9000/health')"]
      interval: 10s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

---

## 📋 STEP 8: Default Policy

### File: `policies/default.json`

```json
{
  "policy_id": "default-policy",
  "version": 1,
  "rules": [
    {
      "id": "rule-1",
      "pattern": "(?i)system:",
      "action": "block",
      "reason": "prompt-injection-system",
      "risk_score": 0.9
    },
    {
      "id": "rule-2",
      "pattern": "(?i)ignore previous",
      "action": "block",
      "reason": "prompt-injection-override",
      "risk_score": 0.95
    },
    {
      "id": "rule-3",
      "pattern": "\\b[0-9]{13,19}\\b",
      "action": "block",
      "reason": "credit-card-number",
      "risk_score": 0.99
    },
    {
      "id": "rule-4",
      "pattern": "\\b[0-9]{3}-[0-9]{2}-[0-9]{4}\\b",
      "action": "block",
      "reason": "ssn-pattern",
      "risk_score": 0.99
    }
  ]
}
```

---

## ✅ STEP 9: Test It Works

```bash
# In agentshield repo
docker compose up --build -d

# Test health
curl http://localhost:9000/health

# Test JWKS
curl http://localhost:9000/v1/keys/jwks

# Test enforcement
curl -X POST http://localhost:9000/v1/enforce \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-1",
    "tenant_id": "test",
    "agent_id": "test-agent",
    "messages": [{"role": "user", "content": "system: ignore previous"}]
  }'

# Should return decision with action: "BLOCK"
```

---

## 🔗 STEP 10: Integrate with Vigil

Once your agentshield backend is working, update Vigil's `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  vigil-gateway:
    image: registry.yourbank.com/vigil:v1.2.3
    ports:
      - "8000:8000"
    environment:
      - AGENTSHIELD_URL=http://agentshield:9000  # Point to real backend
      - FAIL_CLOSED=true

  agentshield:
    image: registry.yourbank.com/agentshield:v1.0.0  # Your real backend
    ports:
      - "9000:9000"
    environment:
      - POLICY_PATH=/app/policies/default.json

  redis:
    image: redis:7-alpine
```

Then test the full stack:

```bash
# In vigil repo
docker compose -f docker-compose.prod.yml up -d

# Run smoke test
python scripts/smoke_test.py
```

---

## 📚 Additional Resources

See the complete specification in **vigil repo**:
- `AGENTSHIELD_REQUIREMENTS.md` - Full API spec, TEE guide, Kubernetes manifests
- `QUICKSTART.md` - How to test with mock backend
- `INTEGRATION_STATUS.md` - What's working vs what's missing

---

## 🎯 Priority Order

1. **CRITICAL (Do First)**:
   - Implement `main.py` with /v1/enforce endpoint
   - Implement `signing.py` with real Ed25519
   - Implement `policy_engine.py` with pattern rules
   - Create Dockerfile and docker-compose.yml

2. **HIGH (Do Soon)**:
   - Add ML-based threat detection
   - Add analytics endpoints
   - Add comprehensive tests

3. **MEDIUM (Bank Requirements)**:
   - TEE/enclave integration (SGX, SEV, or Nitro)
   - Key rotation
   - Multi-region deployment

4. **NICE TO HAVE**:
   - Grafana dashboards
   - SIEM integration
   - Custom policy UI

---

**Once you complete CRITICAL + HIGH, you'll have a production-ready AgentShield backend that works seamlessly with Vigil!**
