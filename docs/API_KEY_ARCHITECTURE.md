# 🔑 API Key Architecture - Where Everything Goes

## TL;DR

| Component | Responsibility | Location |
|-----------|----------------|----------|
| **API Key Generation** | Create new keys when customer signs up | **Customer API** (new service) |
| **API Key Validation** | Check if key is valid on each request | **Vigil Gateway** (existing) |
| **API Key Storage** | Persistent storage of keys | **PostgreSQL** (permanent) + **Redis** (cache) |
| **License Key Validation** | Check if customer can run software | **Vigil Sidecar** (for on-prem) |
| **Vault Management** | Store/retrieve LLM credentials | **AgentShield** |
| **Policy Decisions** | Allow/block decisions | **AgentShield** |

---

## Architecture by Deployment Mode

### 1. SaaS Mode (Cloud Hosted)

```
┌─────────────────────────────────────────────────────────────┐
│ CUSTOMER DASHBOARD (https://app.vigil.security)            │
│                                                             │
│ User Flow:                                                  │
│ 1. Customer signs up                                        │
│ 2. Clicks "Generate API Key"                                │
│ 3. Gets: vk_abc123def456...                                 │
│ 4. Copies and uses in their app                             │
└────────────────────────┬────────────────────────────────────┘
                         │ POST /api/keys
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ CUSTOMER API (Port 3001) - NEW SERVICE                      │
│                                                             │
│ Endpoints:                                                  │
│ • POST /api/auth/signup    → Create tenant                  │
│ • POST /api/keys           → Generate API key ✨            │
│ • GET  /api/keys           → List tenant's keys             │
│ • DELETE /api/keys/{id}    → Revoke key                     │
│                                                             │
│ What it does:                                               │
│ 1. Generates: vk_{random_32_chars}                          │
│ 2. Hashes key: SHA256(vk_...)                               │
│ 3. Stores in PostgreSQL: (tenant_id, key_hash)             │
│ 4. Caches in Redis: api_keys:vk_... → tenant_id            │
│ 5. Returns plain key to customer (only once!)               │
└────────────────────────┬────────────────────────────────────┘
                         │ Stores in DB & Redis
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ POSTGRESQL                     REDIS (Cache)                │
│                                                             │
│ Table: api_keys                Key: api_keys:vk_abc123...   │
│ - tenant_id                    Value: {                     │
│ - key_hash (SHA256)              "tenant_id": "tenant_123", │
│ - key_prefix (vk_abc...)         "tier": "pro",             │
│ - created_at                     "status": "active"         │
│ - last_used                    }                            │
└─────────────────────────────────────────────────────────────┘
                         │
                         │ Customer makes request
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ CUSTOMER APP                                                │
│                                                             │
│ curl -H "Authorization: Bearer vk_abc123..." \              │
│      https://api.vigil.security/v1/chat/completions         │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ VIGIL GATEWAY (Port 8000) - VALIDATES KEYS                  │
│                                                             │
│ File: src/vigil/local_server.py                            │
│ Uses: src/vigil/api_key_auth.py                            │
│                                                             │
│ Request Flow:                                               │
│ 1. Extract: Authorization: Bearer vk_abc123...              │
│ 2. Call: api_key_auth.validate_key("vk_abc123...")         │
│ 3. Redis lookup: GET api_keys:vk_abc123                    │
│ 4. Returns: (tenant_id, metadata) or (None, None)          │
│ 5. If valid: Continue to security checks                    │
│ 6. If invalid: Return 401 Unauthorized                      │
│                                                             │
│ Does NOT generate keys - only validates!                    │
└────────────────────────┬────────────────────────────────────┘
                         │ If valid, continue
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ AGENTSHIELD (Port 9000)                                     │
│                                                             │
│ Responsibilities:                                           │
│ • Policy evaluation (allow/block decisions)                 │
│ • Vault management (store/get LLM API keys)                │
│ • Decision signing (Ed25519)                                │
│                                                             │
│ Does NOT handle Vigil API keys!                             │
│ Only handles: policies, vault, decisions                    │
└─────────────────────────────────────────────────────────────┘
```

### 2. Sidecar Mode (Customer's Infrastructure)

```
┌─────────────────────────────────────────────────────────────┐
│ CUSTOMER'S INFRASTRUCTURE                                   │
│                                                             │
│ ┌──────────────────┐  ┌───────────────────────────────┐    │
│ │ Customer App     │  │ Vigil Sidecar (localhost:8000)│    │
│ │                  │→ │                               │    │
│ │ No API key needed│  │ Mode: SIDECAR                 │    │
│ │ (localhost comm) │  │ API_KEY_VALIDATION=disabled   │    │
│ └──────────────────┘  └───────────────────────────────┘    │
│                              │                              │
│                              ▼                              │
│                       ┌─────────────────┐                   │
│                       │ Local Llama     │                   │
│                       │ (port 11434)    │                   │
│                       └─────────────────┘                   │
│                                                             │
│ License Check:                                              │
│ • On startup, Vigil validates LICENSE_KEY                   │
│ • License key ≠ API key                                     │
│ • License = permission to run software                      │
│ • API key = tenant identification (not needed here)         │
└─────────────────────────────────────────────────────────────┘

Alternative: Multi-tenant Sidecar
┌─────────────────────────────────────────────────────────────┐
│ CUSTOMER RUNS SIDECAR FOR MULTIPLE INTERNAL TEAMS          │
│                                                             │
│ ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│ │ Team A App   │  │ Team B App   │  │ Vigil Sidecar   │    │
│ │ API: vk_team_a│→│ API: vk_team_b│→│                 │    │
│ └──────────────┘  └──────────────┘  │ Multi-tenant    │    │
│                                      │ Separate quotas │    │
│                                      └─────────────────┘    │
│                                                             │
│ In this case:                                               │
│ • Customer generates their own API keys locally             │
│ • Use generate_api_key.py script                            │
│ • Store in local Redis                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Flow: API Key Generation (SaaS)

### Customer API Service (NEW - Need to Build)

**File:** `src/vigil/customer_api.py` (created in CUSTOMER_DASHBOARD.md)

```python
@app.route('/api/keys', methods=['POST'])
def create_key():
    """
    Generate new API key for tenant
    Called when customer clicks "Generate Key" in dashboard
    """
    # 1. Verify customer is logged in (JWT token)
    tenant_id = get_tenant_from_token(request)
    
    # 2. Generate random API key
    api_key = f"vk_{secrets.token_urlsafe(32)}"
    # Result: vk_abc123def456...
    
    # 3. Hash for storage (never store plain key!)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_prefix = api_key[:10] + "..."  # For display
    
    # 4. Store in PostgreSQL (permanent)
    db.execute("""
        INSERT INTO api_keys (tenant_id, key_hash, key_prefix, created_at)
        VALUES (%s, %s, %s, NOW())
    """, (tenant_id, key_hash, key_prefix))
    
    # 5. Cache in Redis (fast lookup)
    redis.hset(f"api_keys:{api_key}", mapping={
        "tenant_id": tenant_id,
        "tier": "pro",
        "status": "active"
    })
    
    # 6. Return plain key (only time customer sees it!)
    return {"api_key": api_key, "warning": "Save this - won't be shown again!"}
```

**Where it runs:**
- Separate service on port 3001
- Behind `https://api.vigil.security/customer/*`
- OR bundled with dashboard if using Flask for both

---

## Detailed Flow: API Key Validation (SaaS)

### Vigil Gateway (EXISTING - Already Works)

**File:** `src/vigil/api_key_auth.py` (already exists!)

```python
class APIKeyAuth:
    def validate_key(self, api_key: str):
        """
        Validate API key on every request
        Called by Vigil Gateway for each incoming request
        """
        # 1. Check format
        if not api_key.startswith('vk_'):
            return None, None
        
        # 2. Look up in Redis (fast)
        data = redis.hgetall(f"api_keys:{api_key}")
        
        if not data:
            # Not in cache - check PostgreSQL
            result = db.execute("""
                SELECT tenant_id, tier, status 
                FROM api_keys 
                WHERE key_hash = %s
            """, (hashlib.sha256(api_key.encode()).hexdigest(),))
            
            if not result:
                return None, None  # Invalid key
            
            # Cache for next time
            redis.hset(f"api_keys:{api_key}", mapping={
                "tenant_id": result['tenant_id'],
                "tier": result['tier'],
                "status": result['status']
            })
            return result['tenant_id'], result
        
        # 3. Check status
        if data.get('status') != 'active':
            return None, None  # Suspended/revoked
        
        # 4. Update last_used (async)
        redis.hset(f"api_keys:{api_key}", "last_used", time.time())
        
        # 5. Return tenant info
        return data['tenant_id'], data
```

**Where it runs:**
- Inside Vigil Gateway (port 8000)
- Called on EVERY incoming request
- Before any LLM processing

---

## What About AgentShield?

**AgentShield does NOT handle Vigil API keys!**

AgentShield's responsibilities:
1. **Policy evaluation** - Should this request be allowed?
2. **Vault management** - Store/retrieve customer's LLM API keys (OpenAI, Anthropic, etc.)
3. **Decision signing** - Sign allow/block decisions

```python
# AgentShield Vault - stores LLM keys, not Vigil keys!

@app.route('/vault/credentials', methods=['POST'])
def get_llm_credentials():
    """
    Return customer's OpenAI/Anthropic API key
    
    Request from Vigil:
    {
        "tenant_id": "tenant_abc123",  # Already validated by Vigil!
        "provider": "openai"
    }
    
    Response:
    {
        "api_key": "sk-proj-...",  # Customer's OpenAI key
        "endpoint": "https://api.openai.com/v1",
        "model": "gpt-4"
    }
    """
    tenant_id = request.json['tenant_id']
    provider = request.json['provider']
    
    # Retrieve from vault
    encrypted_key = db.get_vault_key(tenant_id, provider)
    decrypted_key = decrypt(encrypted_key)
    
    return {"api_key": decrypted_key}
```

---

## License Keys vs API Keys (Sidecar)

### Two Different Concepts!

| Feature | API Key (vk_...) | License Key (VGL-...) |
|---------|------------------|----------------------|
| **Purpose** | Identify tenant/customer | Permission to run software |
| **Used in** | SaaS mode (multi-tenant) | Sidecar mode (on-prem) |
| **Format** | `vk_abc123...` | `VGL-ENTERPRISE-ABC123` |
| **Validated by** | Vigil Gateway (Redis lookup) | Vigil Sidecar (license server) |
| **Stored in** | Redis + PostgreSQL | License file or env var |
| **Example** | Customer A's key to access your API | Customer A's key to run your software |

### Sidecar License Validation

**File:** Add to `src/vigil/local_server.py` startup

```python
def validate_license():
    """
    Check license key on startup (sidecar mode only)
    """
    deployment_mode = os.environ.get('DEPLOYMENT_MODE', 'saas')
    
    if deployment_mode == 'sidecar':
        license_key = os.environ.get('LICENSE_KEY')
        
        if not license_key:
            logger.error("LICENSE_KEY required for sidecar deployment")
            sys.exit(1)
        
        # Validate with license server (or local file if air-gapped)
        if os.environ.get('AIRGAP_MODE') == 'true':
            # Validate against local license file
            with open('/app/config/license.json') as f:
                license_data = json.load(f)
            
            if license_data['key'] != license_key:
                logger.error("Invalid license key")
                sys.exit(1)
            
            if datetime.now() > datetime.fromisoformat(license_data['expires_at']):
                logger.error("License expired")
                sys.exit(1)
        else:
            # Validate with cloud license server
            resp = requests.post('https://license.vigil.security/validate', json={
                'license_key': license_key,
                'machine_id': get_machine_id()
            })
            
            if resp.status_code != 200:
                logger.error("License validation failed")
                sys.exit(1)
        
        logger.info(f"License validated: {license_key[:20]}...")

# Run on startup
if __name__ == '__main__':
    validate_license()
    app.run()
```

---

## Summary: Where Does What Go?

### ✅ API Key Generation (SaaS)
**Location:** Customer API service (port 3001)
**File:** `src/vigil/customer_api.py` (NEW - need to create)
**Triggered by:** Customer clicks "Generate Key" in dashboard
**Stores in:** PostgreSQL + Redis

### ✅ API Key Validation (SaaS)
**Location:** Vigil Gateway (port 8000)
**File:** `src/vigil/api_key_auth.py` (EXISTING - already works!)
**Triggered by:** Every incoming request
**Reads from:** Redis (cache) → PostgreSQL (fallback)

### ✅ License Key Validation (Sidecar)
**Location:** Vigil Sidecar (port 8000)
**File:** `src/vigil/local_server.py` (add license check)
**Triggered by:** On startup
**Validates via:** License server OR local file

### ✅ Vault Management (Both)
**Location:** AgentShield (port 9000)
**File:** AgentShield codebase
**Stores:** Customer's LLM API keys (OpenAI, Anthropic, etc.)
**NOT related to:** Vigil API keys

### ✅ Local Key Generation (Sidecar - Optional)
**Location:** Customer's machine
**File:** `generate_api_key.py` (EXISTING - already works!)
**Used when:** Customer runs multi-tenant sidecar
**Stores in:** Local Redis

---

## Quick Commands

### Generate API Key (SaaS) - Via Dashboard
```bash
# Customer clicks button, calls:
curl -X POST https://api.vigil.security/customer/keys \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Production Key"}'

# Response:
# {"api_key": "vk_abc123...", "warning": "Save this!"}
```

### Generate API Key (Sidecar) - Via Script
```bash
# Customer runs on their machine:
python generate_api_key.py --tenant "internal-team-a"

# Output:
# API Key: vk_local_xyz789...
# Stored in: api_keys.json
# Add to Redis:
redis-cli HSET api_keys:vk_local_xyz789... tenant_id internal-team-a
```

### Validate License (Sidecar) - On Startup
```bash
# Customer sets env var:
export LICENSE_KEY=VGL-ENTERPRISE-ABC123
docker-compose up

# Vigil validates on startup:
# [INFO] Validating license: VGL-ENTERPRISE-ABC123...
# [INFO] License valid until: 2026-12-31
# [INFO] Starting Vigil Gateway...
```

---

## Action Items

### For SaaS Mode
1. ✅ API key validation already works (`api_key_auth.py`)
2. 🔨 **Need to build:** Customer API service (`customer_api.py`)
3. 🔨 **Need to build:** Dashboard UI for key generation
4. ✅ Storage ready: PostgreSQL schema + Redis cache

### For Sidecar Mode
1. ✅ Local key generation works (`generate_api_key.py`)
2. 🔨 **Need to add:** License key validation in `local_server.py`
3. 🔨 **Need to build:** License server API
4. 🔨 **Optional:** Multi-tenant support (if customer wants internal separation)

### For AgentShield
1. ✅ Vault already implemented
2. ✅ Policy decisions already implemented
3. ❌ **Do NOT add:** Vigil API key management (not its job!)
