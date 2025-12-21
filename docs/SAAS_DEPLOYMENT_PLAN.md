# 🚀 Vigil SaaS Deployment Plan

## Overview
This document outlines the complete productization strategy to offer Vigil as a fully managed SaaS platform where customers can use the service without any local installation.

## Architecture Components

### 1. Customer-Facing Components (What They Need)

#### A. Self-Service Dashboard (NEW - Need to Build)
**Purpose**: Customer signup, API key management, billing

**Features**:
- Sign up / Login (Email + Password or OAuth)
- Generate API keys (`vk_...`)
- Configure LLM provider credentials (stored encrypted in vault)
- View usage metrics (requests/day, tokens consumed)
- Manage security policies (allow/block rules)
- Billing dashboard (current usage, invoices)
- Webhook configuration for alerts

**Tech Stack**:
- Frontend: React/Next.js (already have frontend/ folder)
- Backend: Python FastAPI (extend current dashboard_server.py)
- Auth: Auth0, Supabase Auth, or custom JWT
- Database: PostgreSQL (tenant info, subscriptions)

**Endpoints to Add**:
```
POST   /api/auth/signup          # Create new tenant
POST   /api/auth/login           # Get JWT token
GET    /api/keys                 # List API keys
POST   /api/keys                 # Generate new key
DELETE /api/keys/{key_id}        # Revoke key
POST   /api/vault/credentials    # Store LLM provider keys
GET    /api/usage/current        # Current billing period usage
GET    /api/policies             # List security policies
PUT    /api/policies/{id}        # Update policy
```

#### B. SDK/Client Libraries (NEW - Need to Build)
**Purpose**: Make it easy for customers to integrate

**Languages to Support**:
- Python (priority)
- JavaScript/TypeScript
- Go
- Ruby
- Java

**Example Python SDK**:
```python
# pip install vigil-sdk

from vigil import VigilClient

# Initialize with API key
client = VigilClient(api_key="vk_your_key_here")

# Use just like OpenAI client
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Same interface, but protected by Vigil
print(response.choices[0].message.content)
```

**SDK Features**:
- Drop-in replacement for OpenAI/Anthropic clients
- Automatic retries with exponential backoff
- Built-in error handling (rate limits, quota exceeded)
- Streaming support
- Async support

#### C. Documentation Site (NEW - Need to Build)
**Purpose**: Help customers integrate quickly

**Sections**:
1. Quick Start (5-minute integration guide)
2. Authentication (API key management)
3. SDK Reference (all languages)
4. API Reference (REST endpoints)
5. Security Policies (how to configure rules)
6. Billing & Usage (how metering works)
7. Examples (common use cases)
8. Migration Guides (from OpenAI → Vigil)

**Tech Stack**:
- Docusaurus, MkDocs, or GitBook
- Host on Vercel/Netlify
- URL: https://docs.vigil.security

### 2. Infrastructure (Hosting Vigil)

#### A. Edge Gateway (Vigil Gateway)
**Deployment**:
- **Cloud Provider**: AWS, GCP, or Azure
- **Regions**: Start with 2-3 (US-East, US-West, EU-Central)
- **Instance Type**: 
  - Production: AWS `g4dn.xlarge` (NVIDIA T4 GPU) - $0.526/hr
  - High Traffic: AWS `g5.xlarge` (NVIDIA A10G GPU) - $1.006/hr
- **Auto-scaling**: 2-10 instances per region based on CPU/GPU utilization
- **Load Balancer**: AWS ALB or CloudFlare Load Balancing

**Deployment Options**:

**Option 1: Kubernetes (Recommended for Scale)**
```yaml
# k8s-vigil-gateway.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vigil-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: vigil-gateway
  template:
    metadata:
      labels:
        app: vigil-gateway
    spec:
      containers:
      - name: vigil
        image: your-registry/vigil:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: redis://redis-cluster:6379/0
        - name: AGENTSHIELD_URL
          value: http://agentshield:9000
        resources:
          limits:
            nvidia.com/gpu: 1  # Request 1 GPU
            memory: 8Gi
            cpu: 4
---
apiVersion: v1
kind: Service
metadata:
  name: vigil-gateway
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8000
  selector:
    app: vigil-gateway
```

**Option 2: Docker Compose (Simple, Single Region)**
```yaml
# docker-compose.production.yml
version: '3.8'
services:
  vigil-gateway:
    image: your-registry/vigil:latest
    deploy:
      replicas: 3
      resources:
        reservations:
          devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - AGENTSHIELD_URL=http://agentshield:9000
    restart: unless-stopped
```

**Option 3: AWS ECS with GPU (Managed)**
```json
{
  "family": "vigil-gateway",
  "taskRoleArn": "arn:aws:iam::...",
  "containerDefinitions": [{
    "name": "vigil",
    "image": "your-registry/vigil:latest",
    "resourceRequirements": [{
      "type": "GPU",
      "value": "1"
    }],
    "portMappings": [{
      "containerPort": 8000,
      "protocol": "tcp"
    }]
  }]
}
```

#### B. Control Plane (AgentShield + Redis + DB)
**Deployment**:
- **Location**: Single region (US-East or EU-Central)
- **High Availability**: 2+ instances behind load balancer
- **Instance Type**: Standard compute (no GPU needed)
  - AWS: `t3.large` (2 vCPU, 8GB RAM) - $0.0832/hr
  - Auto-scaling: 2-5 instances

**Services**:
1. **AgentShield API** (Port 9000)
   - Policy evaluation
   - Vault management (encrypted LLM keys)
   - Decision signing
   
2. **Redis Cluster** (Managed)
   - AWS ElastiCache or GCP Memorystore
   - API keys cache
   - Rate limiting counters
   - Billing queue
   
3. **PostgreSQL** (Managed)
   - AWS RDS or GCP Cloud SQL
   - Tenant data
   - Audit logs (immutable)
   - Policies
   - Billing records

#### C. Networking & Security

**Domain Setup**:
- Main API: `api.vigil.security`
- Dashboard: `app.vigil.security`
- Docs: `docs.vigil.security`

**SSL/TLS**:
- CloudFlare for DDoS protection + CDN
- Let's Encrypt for SSL certificates
- Force HTTPS (redirect HTTP → HTTPS)

**API Authentication**:
- Bearer token: `Authorization: Bearer vk_...`
- Rate limiting headers:
  ```
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 47
  X-RateLimit-Reset: 1640000000
  ```

**Security Hardening**:
- VPC with private subnets for control plane
- Security groups (Vigil → AgentShield only)
- WAF rules (block common attacks)
- API key encryption at rest (AES-256)
- Vault encryption (AWS KMS or HashiCorp Vault)

### 3. Customer Journey (No Local Installation)

#### Step 1: Sign Up
```
Customer visits: https://app.vigil.security/signup
↓
Enters: Email, Company, Password
↓
Receives: Welcome email with verification link
↓
Clicks link → Account activated
```

#### Step 2: Get API Key
```
Customer logs into: https://app.vigil.security/dashboard
↓
Clicks: "Generate API Key"
↓
Copies: vk_abc123def456...
↓
Dashboard shows: "You have 0 requests this month"
```

#### Step 3: Configure LLM Provider
```
Customer navigates to: Settings → LLM Providers
↓
Selects: OpenAI
↓
Pastes their OpenAI key: sk-proj-...
↓
Vigil stores it encrypted in vault
↓
Message: "OpenAI configured successfully"
```

#### Step 4: Configure Security Policy (Optional)
```
Customer navigates to: Policies → Create New
↓
Sets rules:
  - Block: crypto scams, jailbreaks
  - Sanitize: PII (emails, SSNs)
  - Allow: everything else
↓
Saves policy
```

#### Step 5: Integrate (Choose SDK or Direct API)

**Option A: Python SDK (Easiest)**
```python
# Install SDK
pip install vigil-sdk

# Replace OpenAI client
from vigil import VigilClient  # Instead of: from openai import OpenAI

client = VigilClient(api_key="vk_abc123...")

# Same code as before!
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**Option B: Direct API (Any Language)**
```bash
curl -X POST https://api.vigil.security/v1/chat/completions \
  -H "Authorization: Bearer vk_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

**Option C: Proxy Mode (Zero Code Changes)**
```python
# Set environment variable to redirect OpenAI calls
import os
os.environ["OPENAI_API_BASE"] = "https://api.vigil.security/v1"
os.environ["OPENAI_API_KEY"] = "vk_abc123..."  # Use Vigil key

# Existing code works unchanged!
from openai import OpenAI
client = OpenAI()  # Automatically uses env vars
```

#### Step 6: Monitor & Get Billed
```
Customer returns to: https://app.vigil.security/dashboard
↓
Sees metrics:
  - Total Requests: 1,247
  - Blocked Threats: 23 (1.8%)
  - Tokens Used: 2.3M
  - Current Bill: $47.50
↓
Can download audit logs, configure alerts, etc.
```

### 4. Pricing Model

#### Tier Structure
| Tier | Price/Month | Requests/Month | Tokens/Month | GPU Priority | Support |
|------|-------------|----------------|--------------|--------------|---------|
| **Free** | $0 | 1,000 | 100K | Low | Community |
| **Starter** | $49 | 50,000 | 5M | Normal | Email |
| **Pro** | $199 | 250,000 | 25M | High | Email + Chat |
| **Enterprise** | Custom | Unlimited | Unlimited | Highest | Dedicated |

#### Metering & Billing
- Count tokens (input + output) via `token_meter.py`
- Store in Redis → Async job aggregates daily
- Generate invoices monthly via Stripe/Paddle
- Send usage alerts at 80% quota

### 5. Operational Requirements

#### Monitoring
**Metrics to Track**:
- Gateway: Requests/sec, latency p50/p95/p99, GPU utilization
- AgentShield: Decision latency, vault access time
- Redis: Memory usage, connection pool size
- DB: Query time, connection count

**Tools**:
- Prometheus + Grafana for metrics
- DataDog or New Relic for APM
- Sentry for error tracking
- CloudWatch/Stackdriver for cloud metrics

#### Alerting
**Critical Alerts**:
- Gateway down (any region)
- AgentShield unavailable
- Redis out of memory
- Database disk >80%
- Unusual spike in errors (>1%)

**Tool**: PagerDuty or Opsgenie for on-call rotation

#### Logging
**What to Log**:
- Every request (sanitized) to audit logs
- Blocked threats (full details)
- API key usage (for billing)
- System errors

**Storage**:
- Short-term: ElasticSearch/OpenSearch (7 days)
- Long-term: S3/GCS (7 years for compliance)

### 6. Development Roadmap

#### Phase 1: MVP SaaS (4-6 weeks)
- [ ] Build customer dashboard (signup, login, API keys)
- [ ] Build vault credential storage UI
- [ ] Deploy to single region (AWS us-east-1)
- [ ] Create Python SDK
- [ ] Write integration docs
- [ ] Set up billing (Stripe integration)
- [ ] Beta test with 10 customers

#### Phase 2: Scale & SDK (6-8 weeks)
- [ ] Add 2 more regions (us-west, eu-central)
- [ ] Build JavaScript/TypeScript SDK
- [ ] Add streaming support
- [ ] Auto-scaling (Kubernetes HPA)
- [ ] Advanced monitoring (Grafana dashboards)
- [ ] Public launch

#### Phase 3: Enterprise Features (3-4 months)
- [ ] SSO (SAML, OAuth)
- [ ] Custom domains (customer.vigil.security)
- [ ] Dedicated instances (VPC peering)
- [ ] Compliance (SOC2, HIPAA, GDPR)
- [ ] Go, Ruby, Java SDKs
- [ ] Webhook integrations (Slack, MS Teams)

### 7. Estimated Costs

#### Infrastructure (Per Month)
| Component | Unit Cost | Quantity | Monthly |
|-----------|-----------|----------|---------|
| Vigil Gateway (g4dn.xlarge) | $0.526/hr | 6 instances | $2,280 |
| AgentShield (t3.large) | $0.083/hr | 3 instances | $180 |
| Redis (ElastiCache m5.large) | $0.145/hr | 2 nodes | $210 |
| PostgreSQL (RDS db.t3.medium) | $0.068/hr | 1 instance | $50 |
| Load Balancer (ALB) | $22.50 + traffic | 3 LBs | $100 |
| Data Transfer | $0.09/GB | 10TB | $900 |
| **Total** | | | **~$3,720** |

**Notes**:
- Assumes ~100 requests/sec average
- GPU instances scale down at night (50% savings)
- Add 20% buffer for spikes

#### Per-Customer Unit Economics
- Average customer pays: $199/mo (Pro tier)
- Infrastructure cost per customer: ~$15-20/mo
- **Gross Margin**: ~90%

### 8. Security & Compliance

#### Data Protection
- **In Transit**: TLS 1.3 for all connections
- **At Rest**: AES-256 encryption for DB, vault
- **Keys**: Rotate every 90 days
- **Logs**: Sanitize PII before storage

#### Compliance Checklist
- [ ] GDPR (EU customers): Data deletion, portability
- [ ] SOC2 Type II: Audit controls, access logs
- [ ] HIPAA: PHI handling (if healthcare customers)
- [ ] ISO 27001: Information security

#### Penetration Testing
- Run quarterly pen tests (HackerOne, Bugcrowd)
- Maintain bug bounty program
- Fix critical issues within 24 hours

### 9. Customer Support

#### Support Channels
- **Free Tier**: Community forum (Discourse)
- **Starter/Pro**: Email support (48hr SLA)
- **Enterprise**: Dedicated Slack channel, phone support

#### Documentation
- Create interactive tutorials (Replit embeds)
- Record video walkthroughs (Loom/YouTube)
- Build example apps (GitHub repos)

#### Status Page
- https://status.vigil.security
- Show uptime per region
- Post incident reports (RCA)

---

## 10. What You Already Have ✅

Looking at your codebase:
1. ✅ Multi-tenant architecture (API keys, tenant isolation)
2. ✅ Rate limiting (`api_key_auth.py`)
3. ✅ Token metering (`token_meter.py`)
4. ✅ Vault integration (AgentShield stores LLM keys)
5. ✅ Security scanning (vector DB, PII, firewall)
6. ✅ Docker images (CPU + GPU builds)
7. ✅ Frontend starter (`frontend/` with React)

## 11. What You Need to Build 🔨

### Critical (Must Have)
1. **Customer Dashboard**
   - Sign up / login flow
   - API key management
   - Vault credential config
   - Usage metrics display
   
2. **Python SDK**
   - Drop-in OpenAI replacement
   - Error handling & retries
   
3. **Deployment Scripts**
   - Kubernetes manifests or Terraform
   - CI/CD pipeline (GitHub Actions)
   
4. **Billing System**
   - Stripe integration
   - Invoice generation
   
5. **Documentation Site**
   - Quick start guide
   - API reference
   - Migration guides

### Nice to Have (Can Add Later)
1. More SDKs (JS, Go, Ruby, Java)
2. Multi-region deployment
3. Webhooks for alerts
4. SSO for enterprise
5. Custom domains

---

## Summary: How Customers Use Vigil (Zero Local Setup)

1. **Sign up** at https://app.vigil.security
2. **Get API key** (vk_...)
3. **Configure LLM provider** (store OpenAI key in vault)
4. **Replace endpoint** in their code:
   ```python
   # Before
   from openai import OpenAI
   client = OpenAI(api_key="sk-...")
   
   # After (Option 1: SDK)
   from vigil import VigilClient
   client = VigilClient(api_key="vk_...")
   
   # After (Option 2: Proxy)
   from openai import OpenAI
   client = OpenAI(
       api_key="vk_...",  # Vigil key
       base_url="https://api.vigil.security/v1"
   )
   ```
5. **Done!** All requests automatically protected, monitored, billed

No files to download, no Docker to run, no local setup required! 🎉
