# Vigil SaaS - Quick Start Guide

## 🚀 What Changed

Vigil now operates as a **multi-tenant SaaS gateway** where:
- Customers use **API keys** (`vk_...`) instead of direct OpenAI keys
- **Vigil** handles authentication, rate limiting, security, and billing
- **AgentShield** manages policies and stores tenant LLM credentials in a vault
- All existing security features remain intact (vector scan, PII, firewall)

## 📊 Request Flow (30 seconds)

```
Customer
  ↓ POST /chat/completions + Authorization: Bearer vk_abc123
Vigil Gateway (Port 8000)
  ↓ [1] Validate API key → Get tenant_id from Redis
  ↓ [2] Check rate limit (RPM per tenant)
  ↓ [3] Check token quota (daily/monthly)
  ↓ [4] Run security scans (Vector DB, PII, Firewall)
AgentShield (Port 9000)
  ↓ [5] Get policy decision (ALLOW/BLOCK)
  ↓ [6] If ALLOW: Get tenant's OpenAI key from vault
Vigil
  ↓ [7] Forward to OpenAI with tenant's key
OpenAI API
  ↓ [8] Return completion
Vigil
  ↓ [9] Count tokens → Push to billing queue
  ↓ [10] Return response with Vigil metadata
Customer
```

## 🔑 API Key Format

```
vk_abc123def456...  # 32+ character alphanumeric
```

## 📦 New Files

1. **`src/vigil/api_key_auth.py`** - API key validation & tenant resolution
2. **`src/vigil/token_meter.py`** - Token counting & billing queue
3. **`docs/SAAS_ARCHITECTURE.md`** - Complete documentation

## 🔄 Modified Files

1. **`src/vigil/agentshield_client.py`** - Added `get_llm_credentials()` method
2. **`src/vigil/local_server.py`** - Integrated SaaS flow

## 🎯 Key Features

### Authentication
```python
# Validates API keys from Redis
# Returns (tenant_id, metadata) or (None, None)
api_key_auth.validate_key("vk_abc123...")
```

### Rate Limiting
```python
# Per-tenant, per-minute limits
# Free: 10 RPM, Pro: 100 RPM, Enterprise: 1000 RPM
api_key_auth.check_rate_limit(tenant_id, limit_rpm)
```

### Token Metering
```python
# Counts tokens and pushes to billing queue
token_meter.record_usage(
    tenant_id="acme-corp",
    request_id="req_123",
    model="gpt-4",
    input_tokens=150,
    output_tokens=200
)
```

### Vault Integration
```python
# Gets tenant's LLM API key from AgentShield vault
credentials = agentshield.get_llm_credentials({
    "tenant_id": "acme-corp",
    "provider": "openai"
})
# Returns: {api_key: "sk-...", endpoint: "...", model: "..."}
```

## 📝 Example Request

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Authorization: Bearer vk_test_abc123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

## ✅ Response Example

```json
{
  "id": "chatcmpl-xyz",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    }
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 12,
    "total_tokens": 22
  },
  "vigil": {
    "request_id": "req_123",
    "tenant_id": "test-tenant",
    "action": "ALLOW",
    "risk_score": 0.05,
    "audit_event_id": "ae_xyz",
    "vector_scan": {
      "scanned": true,
      "threat_detected": false
    },
    "usage": {
      "input_tokens": 10,
      "output_tokens": 12,
      "total_tokens": 22
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

## 🔧 Setup (Redis + API Key)

```bash
# 1. Start Redis
redis-server --daemonize yes

# 2. Create test API key
redis-cli HSET "api_keys:vk_test_abc123" \
  tenant_id "test-tenant" \
  tenant_name "Test Company" \
  tier "enterprise" \
  status "active" \
  created_at "$(date +%s)"

# 3. Start Vigil
cd /workspaces/vigil
python3 -m src.vigil.local_server

# 4. Test request (see example above)
```

## 🎛️ Configuration

```bash
# Required
export REDIS_URL=redis://localhost:6379/0
export AGENTSHIELD_URL=http://localhost:9000

# Optional
export VIGIL_ENVIRONMENT=production  # or 'development'
export VIGIL_FAIL_MODE=closed  # or 'open'
```

## 📈 Monitoring

```bash
# Check rate limit usage
redis-cli ZCARD "rate_limit:test-tenant:rpm"

# Check token usage (today)
redis-cli GET "usage:test-tenant:daily:$(date +%Y-%m-%d)"

# Check billing queue length
redis-cli LLEN "billing:events"

# Process billing queue (background worker)
python3 -c "
from src.vigil.token_meter import TokenMeter
meter = TokenMeter()
count = meter.process_billing_queue(100)
print(f'Processed {count} events')
"
```

## 🔒 Security Features Preserved

All existing security functions remain unchanged:
- ✅ Vector Threat Scan (GPU VRAM)
- ✅ PII Redaction
- ✅ Firewall Rules
- ✅ Input Normalization
- ✅ AgentShield Policy Enforcement
- ✅ Signature Verification
- ✅ Audit Logging

**NEW Security:**
- ✅ API Key Authentication
- ✅ Tenant Isolation
- ✅ Rate Limiting (per tenant)
- ✅ Token Quota Enforcement
- ✅ Vault-based Credential Management

## 📚 Full Documentation

See [SAAS_ARCHITECTURE.md](SAAS_ARCHITECTURE.md) for:
- Complete architecture diagrams
- Detailed request flow
- Redis schema documentation
- Deployment guide
- Billing integration examples
- Monitoring & observability setup

## 🎉 Summary

**Before (Self-Hosted):**
```
Customer → Vigil → AgentShield → [Customer forwards to OpenAI]
```

**After (SaaS):**
```
Customer (API key vk_...) → Vigil (auth + security) → AgentShield (policy + vault) → Vigil → OpenAI → Customer
```

**Benefits:**
- Multi-tenancy with isolation
- Centralized billing & metering
- Secure credential management
- Usage analytics per tenant
- Tiered rate limiting
- All security features intact

## 🚀 Ready to Deploy!

All changes committed to `main` branch:
- Commit: `cc68d41`
- Files: 5 changed, 1556 insertions
- Status: ✅ Syntax validated, pushed to GitHub
