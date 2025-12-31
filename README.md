# Vigil

**LLM Policy Enforcement Gateway for Production AI Systems (SDK)**

Vigil is a **production-grade policy enforcement gateway** for Large Language Model (LLM) applications.

It sits between your application and LLM providers (OpenAI, Anthropic, etc.) to **enforce security and usage policy, reduce risk, and provide visibility** into AI interactions — without requiring changes to application code.

Vigil exposes an **OpenAI-compatible API** and can run standalone or as part of a broader AI control plane with AgentShield.

---
## 🚀 Quick Start

Get Vigil running in under 5 minutes:

```bash
git clone https://github.com/rom-mvp/vigil.git
cd vigil
docker compose -f docker-compose.saas.yml up --build -d

# Wait for services to start
sleep 10

# Run smoke test
python scripts/smoke_test.py
```

**What you get out of the box:**
- ✅ Full enforcement pipeline with real Ed25519 signing
- ✅ Policy rules that block prompt injection, PII, XSS, SQL injection
- ✅ Merkle audit log with tamper detection
- ✅ PII detection & redaction
- ✅ API authentication
- ✅ Fail-closed mode (blocks when backend unreachable)

**See [QUICKSTART.md](QUICKSTART.md) for detailed setup & testing.**

---


## What problem Vigil solves

As LLMs move from experimentation into production systems, teams face new risks:

* Prompt injection and instruction override attacks
* Jailbreak attempts that bypass application intent
* Sensitive or regulated data leaking into prompts
* Lack of visibility and auditability around AI usage
* No centralized place to enforce policy across agents and apps

Existing tools fail because:

* Models cannot reliably enforce their own constraints
* Traditional WAFs do not understand instruction-level attacks
* Pure ML-based detectors introduce unacceptable false positives
* Ad-hoc prompt rules do not scale or audit

**Vigil provides a dedicated enforcement point for AI traffic**, where policy can be defined, tested, monitored, and evolved.

---

## What Vigil is (and is not)

### Vigil **is**

* An **LLM security and policy gateway**
* A **control point** between applications and models
* A way to **block, allow, or sanitize** AI requests
* OpenAI-compatible and easy to integrate
* Built for low latency and production reliability

### Vigil **is not**

* A guarantee against hallucinations
* A replacement for application authorization logic
* A model alignment or “AI truth” system

Vigil enforces **boundaries and policy** — not correctness.

---

## How Vigil works

```
Your Application → Vigil → LLM Provider
```

For every request, Vigil evaluates the input before it reaches the model.

### Enforcement layers include:

1. **Sensitive data detection**

   * Identifies regulated identifiers (e.g. financial, healthcare, personal data)
   * Blocks or flags requests based on policy

2. **Instruction and capability abuse detection**

   * Detects attempts to override system instructions
   * Identifies unauthorized actions (policy changes, data exfiltration, tool misuse)

3. **Semantic risk analysis (optional)**

   * Embedding-based similarity against known risk concepts
   * Tunable per agent profile
   * Can be disabled for strictly deterministic enforcement

4. **Obfuscation and entropy heuristics**

   * Flags encoded or intentionally obscured payloads commonly used in bypass attempts

Requests that pass policy are forwarded upstream.
High-confidence violations are blocked immediately.

Normal requests typically pass through in **<20ms**.

---

## The Vigil SaaS offering (what you are actually selling)

Vigil can be used in two ways:

### 1. Standalone gateway (most users)

* Run Vigil as a managed or self-hosted gateway
* Enforce policy on all LLM calls
* Gain visibility into AI usage and risk
* No enclave or additional services required

This is ideal for:

* Startups and teams shipping AI features quickly
* Production systems needing basic AI security controls
* Agent-based applications with moderate privilege

### 2. Control plane + governance (enterprises)

When paired with **AgentShield**, Vigil becomes the **data plane** of a full AI control plane:

* Vigil enforces policy inline
* AgentShield signs decisions, manages secrets, and records tamper-evident audit logs
* Optional confidential-compute deployment for sensitive workloads

This is designed for:

* Regulated environments
* Multi-tenant AI platforms
* Organizations needing auditability and governance

---

## Quick start

```bash
docker compose up --build
```

Send a request using the OpenAI-compatible API:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "What is the weather?"}]
  }'
```

That’s it — Vigil is now enforcing policy on your LLM calls.

---

## Integration

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer your-vigil-key"},
    json={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello!"}]
    }
)

print(response.json())
```

### Node.js

```javascript
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your-vigil-key',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [{ role: 'user', content: 'Hello!' }]
  })
});

const data = await response.json();
```

**No SDK rewrite required.**
Just change your base URL.

---

## Performance characteristics

Vigil is designed to be fast and predictable:

| Metric             | Observed (internal testing)       |
| ------------------ | --------------------------------- |
| Typical latency    | ~15–20ms                          |
| P99 latency        | <50ms                             |
| Detection approach | Deterministic + optional semantic |
| Failure behavior   | Explicit, observable              |

Performance depends on configuration and enabled features.

---

## Repository structure

```text
vigil/
├── src/vigil/              # Core gateway logic
│   ├── guardrails.py       # Enforcement layers
│   ├── firewall_engine.py  # Deterministic rules
│   ├── vector_engine.py    # Semantic analysis (optional)
│   └── pii_engine.py       # Sensitive data detection
├── shared/
│   ├── schemas/            # API and policy contracts
│   ├── crypto/             # Cryptographic primitives
│   └── errors/             # Standardized error handling
├── services/
│   ├── vigil-gateway/      # Public API service
│   └── agentshield-enclave/# Optional secure analysis path
├── tests/
│   ├── unit/
│   ├── integration/
│   └── performance/
├── red_team_attack.py      # Injection and bypass tests
└── docker-compose.yml
```

---

## Relationship to AgentShield

Vigil is the **inline enforcement gateway**.
[AgentShield](https://github.com/rom-mvp/agentshield) is the **control plane**.

```
Application
   ↓
Vigil (policy enforcement)
   ↓
AgentShield (optional)
   ↓
LLM Provider
```

AgentShield adds:

* Signed enforcement decisions (Ed25519)
* Tamper-evident audit logs
* Just-in-time secret release
* Governance and compliance hooks

Vigil works independently; AgentShield adds higher-assurance controls.

---

## Testing

```bash
pytest
python red_team_attack.py
```

Tests focus on **policy enforcement correctness**, not model behavior.

---

## Deployment

### Docker

```bash
docker compose up -d
```

### Kubernetes

```bash
kubectl apply -f k8s-deployment.yaml
```

### Configuration example

```bash
export VIGIL_STRICT_MODE=true        # Fail-secure (crash on errors)
export VIGIL_ENV=production          # Enable production optimizations
export VIGIL_API_KEY=your-secret-key # API authentication
export VIGIL_ML_ENABLED=true         # Enable semantic detection

# AgentShield integration (optional, non-breaking)
export AGENTSHIELD_URL=http://agentshield-gateway:9000
export AGENTSHIELD_APPROVAL_HUB=http://agentshield-approval-hub:9001
export AGENTSHIELD_TIMEOUT_MS=3000

# Model IP protection signals
export DISTILLATION_DETECTION_ENABLED=true
export EXTRACTION_RISK_CLUSTERS=enabled

# Caching
export REDIS_URL=redis://redis:6379/0
```

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Contact

Built by the Vigil team.

📧 [suladesada@gmail.com](mailto:suladesada@gmail.com)

For enterprise deployments, governance integrations, or architecture reviews, reach out.
