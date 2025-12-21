# 🚀 Vigil SaaS Architecture - Implementation Guide

## Overview

Vigil has been enhanced to support a **multi-tenant SaaS architecture** where:
- **Vigil** = Data Plane (Edge Gateway) running on GPU instances
- **AgentShield** = Control Plane (Policy & Vault Service)
- **Customers** = Tenants with API keys accessing via SDK/API

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ CUSTOMER APPLICATION                                                │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ POST /chat/completions                                          │ │
│ │ Authorization: Bearer vk_abc123...                              │ │
│ │ Content-Type: application/json                                  │ │
│ │                                                                 │ │
│ │ { "model": "gpt-4", "messages": [...] }                        │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ VIGIL GATEWAY (Data Plane) - Port 8000                             │
│ Runs on: AWS G4/G5 GPU instances at edge locations                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [1] API KEY AUTHENTICATION (Redis)                                 │
│     ✓ Validates Bearer vk_... token                                │
│     ✓ Resolves tenant_id from Redis                                │
│     ✓ Rejects invalid keys (401 Unauthorized)                      │
│                                                                     │
│ [2] TENANT ISOLATION                                                │
│     ✓ Tags all logs/metrics with tenant_id                         │
│     ✓ Prevents cross-tenant data access                            │
│                                                                     │
│ [3] RATE LIMITING (Per Tenant)                                     │
│     ✓ Checks RPM limit based on tier (free/pro/enterprise)         │
│     ✓ Returns 429 with X-RateLimit-* headers                       │
│                                                                     │
│ [4] QUOTA ENFORCEMENT (Token Limits)                                │
│     ✓ Checks daily/monthly token quota                             │
│     ✓ Blocks if quota exceeded (429)                               │
│                                                                     │
│ [5] HOT SECURITY (WAF + Vector DB)                                 │
│     ✓ Normalization (Base64, ROT13, Leetspeak)                     │
│     ✓ Vector Threat Scan (GPU VRAM - <10ms)                        │
│     ✓ PII Redaction (CPU-local)                                    │
│     ✓ Blocks known jailbreaks instantly                            │
│                                                                     │
│ [6] AGENTSHIELD DECISION                                            │
│     ✓ Calls /decision with tenant_id + scan_results                │
│     ✓ Gets signed ALLOW/BLOCK/SANITIZE decision                    │
│     ✓ Signature verification (Ed25519)                             │
│                                                                     │
│ [7] VAULT KEY RETRIEVAL                                             │
│     ✓ Calls /vault/credentials with tenant_id                      │
│     ✓ Gets tenant's OpenAI API key (encrypted)                     │
│     ✓ Fails if no key configured (500)                             │
│                                                                     │
│ [8] LLM FORWARDING                                                  │
│     ✓ Forwards to OpenAI with tenant's key                         │
│     ✓ Proxies response back to customer                            │
│     ✓ Adds Vigil metadata (risk_score, timings)                    │
│                                                                     │
│ [9] TOKEN METERING (Async)                                          │
│     ✓ Counts input + output tokens                                 │
│     ✓ Pushes to Redis billing queue                                │
│     ✓ Updates real-time usage counters                             │
│                                                                     │
│ [10] FAIL-SAFE                                                      │
│     ✓ Configurable fail-open/fail-closed                           │
│     ✓ Queues logs if AgentShield down                              │
│                                                                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ AGENTSHIELD (Control Plane) - Port 9000                            │
│ Runs on: Standard compute (CPU only)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ [1] POLICY EVALUATION                                               │
│     ✓ Loads tenant's security policy                               │
│     ✓ Checks rules (crypto scams, sensitive topics, etc.)          │
│     ✓ Calculates risk score with ML model                          │
│                                                                     │
│ [2] DECISION SIGNING                                                │
│     ✓ Signs decision with Ed25519 private key                      │
│     ✓ Returns signature + audit_event_id                           │
│                                                                     │
│ [3] VAULT MANAGEMENT                                                │
│     ✓ Stores tenant's LLM API keys (encrypted at rest)             │
│     ✓ Returns keys only for authorized requests                    │
│     ✓ Supports rotation/revocation                                 │
│                                                                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ OPENAI API (LLM Provider) - api.openai.com                         │
│                                                                     │
│ [1] Receives request with tenant's API key                         │
│ [2] Generates completion                                            │
│ [3] Returns response with usage stats                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Request Flow

### Complete SaaS Request Lifecycle

```
1. Customer → Vigil
   POST /chat/completions
   Authorization: Bearer vk_abc123...

2. Vigil: API Key Authentication
   ✓ Validates vk_abc123 against Redis
   ✓ Resolves: vk_abc123 → tenant_id="acme-corp"
   ✓ Gets tier: "enterprise"

3. Vigil: Rate Limiting
   ✓ Checks Redis: acme-corp has 47/100 RPM remaining
   ✓ Allows request (increments counter)

4. Vigil: Quota Check
   ✓ Checks Redis: acme-corp used 150K/unlimited tokens today
   ✓ Allows request

5. Vigil: Hot Security (WAF)
   ✓ Normalizes input (Base64, Unicode, etc.)
   ✓ Vector Scan (GPU): cosine similarity vs threat DB
   ✓ Result: Clean (no jailbreak detected)
   ✓ PII Scan: Redacts email@example.com → [EMAIL]

6. Vigil → AgentShield: Decision Request
   POST /decision
   {
     "tenant_id": "acme-corp",
     "agent_id": "chatbot-v2",
     "policy_id": "policy-acme-chatbot-v2",
     "messages": [sanitized],
     "scan_results": {
       "scanned": true,
       "vector_db_hit": false,
       "vector_distance": 0.23,
       ...
     }
   }

7. AgentShield: Policy Evaluation
   ✓ Loads acme-corp's policy (v42)
   ✓ Checks rules: "Block Crypto Scams" → No match
   ✓ ML Risk Score: 0.12 (low risk)
   ✓ Decision: ALLOW

8. AgentShield → Vigil: Signed Decision
   {
     "decision": "ALLOW",
     "risk_score": 0.12,
     "signature": "...",
     "audit_event_id": "ae_xyz789",
     "signature_hash": "sha256:abc123"
   }

9. Vigil: Signature Verification
   ✓ Verifies Ed25519 signature
   ✓ Checks timestamp TTL (not expired)
   ✓ Signature valid ✓

10. Vigil → AgentShield: Vault Credentials
    POST /vault/credentials
    {
      "tenant_id": "acme-corp",
      "agent_id": "chatbot-v2",
      "policy_id": "policy-acme-chatbot-v2"
    }

11. AgentShield → Vigil: LLM Key
    {
      "provider": "openai",
      "api_key": "sk-proj-abc123...",  # acme-corp's key
      "endpoint": "https://api.openai.com/v1/chat/completions",
      "model": "gpt-4"
    }

12. Vigil → OpenAI: Forward Request
    POST https://api.openai.com/v1/chat/completions
    Authorization: Bearer sk-proj-abc123...  # Tenant's key
    {
      "model": "gpt-4",
      "messages": [sanitized]
    }

13. OpenAI → Vigil: Response
    {
      "id": "chatcmpl-xyz",
      "choices": [...],
      "usage": {
        "prompt_tokens": 150,
        "completion_tokens": 200,
        "total_tokens": 350
      }
    }

14. Vigil: Token Metering (Async)
    ✓ Push to Redis billing queue:
      {
        "tenant_id": "acme-corp",
        "request_id": "req_123",
        "input_tokens": 150,
        "output_tokens": 200,
        "model": "gpt-4",
        "timestamp": 1234567890
      }
    ✓ Update usage counters:
      usage:acme-corp:daily:2025-12-17 += 350
      usage:acme-corp:monthly:2025-12 += 350

15. Vigil → Customer: Final Response
    {
      "id": "chatcmpl-xyz",
      "choices": [...],
      "usage": {...},
      "vigil": {
        "request_id": "req_123",
        "tenant_id": "acme-corp",
        "action": "ALLOW",
        "risk_score": 0.12,
        "audit_event_id": "ae_xyz789",
        "vector_scan": {
          "scanned": true,
          "threat_detected": false
        },
        "timings": {
          "vector_ms": 3.2,
          "agentshield_ms": 45.1,
          "llm_ms": 1823.7,
          "total_ms": 1891.4
        }
      }
    }
```

## Implementation Details

### 1. API Key Authentication

**File:** `src/vigil/api_key_auth.py`

```python
class APIKeyAuth:
    def validate_key(api_key: str) -> (tenant_id, metadata)
    def check_rate_limit(tenant_id, limit_rpm) -> (allowed, info)
    def get_tenant_rate_limit(tenant_id, tier) -> int
```

**Redis Schema:**
```
api_keys:vk_abc123 → Hash
  - tenant_id: "acme-corp"
  - tenant_name: "Acme Corporation"
  - tier: "enterprise"
  - status: "active"
  - created_at: "1234567890"

rate_limit:acme-corp:rpm → Sorted Set (sliding window)
  timestamp1: timestamp1
  timestamp2: timestamp2
  ...
```

**Rate Limits by Tier:**
- Free: 10 RPM
- Pro: 100 RPM
- Enterprise: 1000 RPM
- Unlimited: 10000 RPM

### 2. Token Metering & Billing

**File:** `src/vigil/token_meter.py`

```python
class TokenMeter:
    def estimate_tokens(text, model) -> int
    def count_message_tokens(messages, model) -> int
    def record_usage(tenant_id, request_id, model, input_tokens, output_tokens) -> bool
    def check_quota(tenant_id, tier, requested_tokens) -> dict
```

**Redis Schema:**
```
billing:events → List (queue)
  [
    {"tenant_id": "acme", "tokens": 350, "model": "gpt-4", ...},
    ...
  ]

usage:acme-corp:daily:2025-12-17 → Counter (int)
usage:acme-corp:monthly:2025-12 → Counter (int)
usage:acme-corp:total → Counter (int)
```

**Quota Limits by Tier:**
- Free: 10K daily, 100K monthly
- Pro: 100K daily, 2M monthly
- Enterprise: Unlimited

### 3. Vault Integration

**File:** `src/vigil/agentshield_client.py`

```python
class AgentShieldClient:
    def get_llm_credentials(request_data) -> dict:
        # POST /vault/credentials
        # Returns: {provider, api_key, endpoint, model}
```

**AgentShield Vault Schema (Hypothetical):**
```json
{
  "tenant_id": "acme-corp",
  "credentials": {
    "openai": {
      "api_key": "sk-proj-...",  # Encrypted at rest
      "endpoint": "https://api.openai.com/v1",
      "default_model": "gpt-4"
    },
    "anthropic": {
      "api_key": "sk-ant-...",
      "endpoint": "https://api.anthropic.com/v1",
      "default_model": "claude-3-opus"
    }
  }
}
```

### 4. Main Request Handler

**File:** `src/vigil/local_server.py`

**Changes:**
1. Added imports for `APIKeyAuth` and `TokenMeter`
2. Initialized SaaS components at module level
3. Added authentication check at start of `transparent_proxy()`
4. Added rate limiting check (tenant-aware)
5. Added quota check (token-based)
6. Updated tenant_id to come from API key (not headers)
7. Added vault credentials retrieval after ALLOW decision
8. Added real LLM forwarding (replaced mock)
9. Added token metering after LLM response
10. Added Vigil metadata to response

## Configuration

### Environment Variables

```bash
# Redis (for API keys, rate limiting, billing queue)
REDIS_URL=redis://localhost:6379/0

# AgentShield
AGENTSHIELD_URL=http://localhost:9000
AGENTSHIELD_TIMEOUT_MS=3000

# Vigil Behavior
VIGIL_ENVIRONMENT=production  # or 'development'
VIGIL_FAIL_MODE=closed  # or 'open' (when Redis/AgentShield down)

# Vector Scanning
VECTOR_MODEL_PATH=models/all-MiniLM-L6-v2.onnx
VECTOR_DB_PATH=data/threat_vectors.jsonl
```

### Redis Setup

```bash
# Install Redis
apt-get install redis-server

# Start Redis
redis-server --daemonize yes

# Create sample API key
redis-cli HSET "api_keys:vk_test_abc123" \
  tenant_id "test-tenant" \
  tenant_name "Test Company" \
  tier "enterprise" \
  status "active" \
  created_at "$(date +%s)"
```

### Testing the SaaS Flow

```bash
# 1. Create API key
python3 -c "
from src.vigil.api_key_auth import APIKeyAuth
auth = APIKeyAuth()
api_key = auth.create_api_key('acme-corp', 'Acme Corporation', 'enterprise')
print(f'API Key: {api_key}')
"

# 2. Test request
curl -X POST http://localhost:8000/chat/completions \
  -H "Authorization: Bearer vk_test_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ]
  }'

# Expected response: LLM completion with Vigil metadata
```

## Deployment

### Vigil (Data Plane)

```dockerfile
# Dockerfile for Vigil
FROM nvidia/cuda:12.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y python3 python3-pip redis-tools

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY src/ /app/src/
COPY models/ /app/models/
COPY data/ /app/data/

WORKDIR /app
EXPOSE 8000

CMD ["python3", "-m", "src.vigil.local_server"]
```

**Deployment:**
```bash
# AWS G4/G5 instance with GPU
docker run -d \
  --gpus all \
  -p 8000:8000 \
  -e REDIS_URL=redis://redis-cluster:6379/0 \
  -e AGENTSHIELD_URL=http://agentshield:9000 \
  -e VIGIL_ENVIRONMENT=production \
  vigil:latest
```

### AgentShield (Control Plane)

```bash
# Standard compute (CPU only)
docker run -d \
  -p 9000:9000 \
  -e DATABASE_URL=postgresql://... \
  -e VAULT_KEY=... \
  agentshield:latest
```

## Monitoring & Observability

### Metrics to Track

1. **Authentication:**
   - API key validation success/failure rate
   - Invalid key attempts per tenant
   - API key usage distribution

2. **Rate Limiting:**
   - Rate limit hits per tenant
   - Average RPM per tier
   - Peak request times

3. **Quota Usage:**
   - Daily/monthly token consumption per tenant
   - Quota exceeded events
   - Token cost by model

4. **Security:**
   - Vector scan threat detections
   - AgentShield BLOCK rate
   - PII redaction count

5. **Performance:**
   - P50/P95/P99 latency by component
   - Vector scan latency (GPU)
   - AgentShield latency
   - LLM latency

6. **Billing:**
   - Total tokens per tenant
   - Revenue by tier
   - Cost per request (LLM API costs)

### Grafana Dashboard Example

```promql
# Request rate per tenant
rate(vigil_requests_total{tenant_id="acme-corp"}[5m])

# Token usage per tenant
increase(vigil_tokens_total{tenant_id="acme-corp"}[1d])

# Rate limit violations
rate(vigil_rate_limit_exceeded_total[5m])

# Security blocks
rate(vigil_blocks_total{reason="vector_threat"}[5m])
```

## Security Considerations

### 1. API Key Storage
- Store API keys hashed in production
- Use Redis AUTH password
- Enable TLS for Redis connections

### 2. LLM Credentials
- AgentShield encrypts keys at rest (Vault)
- Keys transmitted over TLS only
- Never log full API keys

### 3. Tenant Isolation
- All Redis keys prefixed with tenant_id
- Audit logs tagged with tenant_id
- No cross-tenant data leakage

### 4. Fail-Safe
- `VIGIL_FAIL_MODE=closed` - Reject on Redis/AgentShield failure (secure default)
- `VIGIL_FAIL_MODE=open` - Allow on failure (availability priority)

### 5. Rate Limiting
- Sliding window prevents burst attacks
- Per-tenant, not global
- Returns proper 429 with Retry-After

## Billing Integration

### Background Worker

```python
# billing_worker.py
from src.vigil.token_meter import TokenMeter

meter = TokenMeter()

while True:
    # Process billing queue
    count = meter.process_billing_queue(batch_size=100)
    
    if count > 0:
        print(f"Processed {count} billing events")
    
    time.sleep(5)  # Poll every 5 seconds
```

### Stripe Integration Example

```python
def _process_billing_event(event):
    tenant_id = event['tenant_id']
    tokens = event['total_tokens']
    model = event['model']
    
    # Calculate cost
    price_per_1k = {
        'gpt-4': 0.03,
        'gpt-3.5-turbo': 0.002
    }
    cost = (tokens / 1000) * price_per_1k.get(model, 0.01)
    
    # Create Stripe usage record
    stripe.UsageRecord.create(
        subscription_item=tenant_subscription_items[tenant_id],
        quantity=tokens,
        timestamp=event['timestamp']
    )
```

## Next Steps

1. **AgentShield Vault API** - Implement `/vault/credentials` endpoint
2. **Admin Dashboard** - UI for managing tenants, API keys, policies
3. **Analytics** - Real-time usage dashboard for tenants
4. **Multi-Provider** - Support Anthropic, Cohere, etc.
5. **Caching** - Redis cache for common completions
6. **Streaming** - SSE support for streaming responses
7. **Webhooks** - Event notifications for security events

## Files Changed

- ✅ `src/vigil/api_key_auth.py` - NEW: API key authentication
- ✅ `src/vigil/token_meter.py` - NEW: Token metering & billing
- ✅ `src/vigil/agentshield_client.py` - UPDATED: Added `get_llm_credentials()`
- ✅ `src/vigil/local_server.py` - UPDATED: SaaS flow integration
- ✅ `docs/SAAS_ARCHITECTURE.md` - NEW: This documentation
