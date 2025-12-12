# Vigil Dashboard - Audit & Compliance UI

**iOS-inspired security dashboard for Vigil audit logs, policy management, and compliance reporting.**

---

## 🎯 Features

### 📊 Audit Logs (Most Important - This is What Companies Pay For)

**Table View:**
- Timestamp
- Decision (ALLOW/BLOCK/CHALLENGE)
- Risk score
- Tenant ID
- Agent ID
- Policy version
- Request ID
- Signature verified (✅ / ❌)

**Detail View (Click any row):**
- Full decision object
- Reasons array
- Signature hash
- Merkle link (prev_hash)
- Enforcement result
- Timings (t_agentshield_ms, t_total_ms)
- Complete request context

**Filters:**
- Filter by tenant
- Filter by agent
- Filter by decision type (ALLOW/BLOCK/ERROR)
- Filter by signature verification status

---

### 🔐 Policy Configuration (Admins Only)

**Editable Settings:**
- ✅ Max risk score threshold (0.00 - 1.00)
- ✅ Disallowed reasons (comma-separated)
- ✅ Enforcement mode (DENY vs CHALLENGE)
- ✅ Request timeout limits (ms)

**Cannot Disable (Hard-Coded Security):**
- ❌ Signature verification (always enabled)
- ❌ Fail-closed behavior (always enabled)
- ❌ Request ID binding (always enabled)
- ❌ Replay prevention (always enabled)

---

### 🔑 Keys & Trust (Admins Only)

**Active Signing Keys:**
- Key ID (kid)
- Algorithm (EdDSA Ed25519)
- Status (Active/Rotated)
- Last used timestamp

**Verification Failures:**
- Timestamp
- Request ID
- Failure reason
- Key ID attempted

---

### 📋 Compliance / Export (Auditors)

**Audit Log Export:**
- Export format: JSON or CSV
- Time-bounded export (from/to filters)
- Download audit logs for compliance

**Merkle Chain Verification:**
- Verify audit log integrity
- Detect tampering in log chain
- Generate verification report

---

## 🚀 Quick Start

### Local Development

```bash
# Start dashboard
python dashboard_server.py

# Access at http://localhost:3000
```

### Docker Compose (Full Stack)

```bash
# Build and start all services
docker-compose up -d

# Access services:
# - Vigil Gateway: http://localhost:8000
# - Dashboard UI: http://localhost:3000
# - AgentShield: http://localhost:9000 (internal)

# View logs
docker-compose logs -f vigil-dashboard
```

### Kubernetes Deployment

```bash
kubectl apply -f k8s-dashboard.yaml
kubectl port-forward -n vigil-system svc/vigil-dashboard 3000:3000
```

---

## 🔒 Authentication

### Demo Accounts

| Username | Password | Role | Permissions |
|----------|----------|------|-------------|
| admin | admin123 | Admin | Full access (read logs, write policies, manage keys, export) |
| auditor | auditor123 | Auditor | Read-only access (read logs, export) |

### Production Setup

Replace in-memory user store with:
- **Database**: PostgreSQL, MySQL
- **LDAP/AD**: Enterprise directory
- **OAuth2/SAML**: SSO integration

Example:
```python
# dashboard_server.py
import ldap

def authenticate_user(username, password):
    conn = ldap.initialize('ldap://your-ldap-server')
    conn.simple_bind_s(f'uid={username},dc=company,dc=com', password)
    return True
```

---

## 🎨 Design System

### iOS-Inspired Style

**Colors:**
- Primary Blue: `#007AFF`
- Green (Success): `#34C759`
- Red (Danger): `#FF3B30`
- Orange (Warning): `#FF9500`
- Gray Background: `#F2F2F7`

**Typography:**
- Font: `-apple-system` (San Francisco on iOS/macOS)
- Headers: 600 weight
- Body: 400 weight

**Components:**
- Rounded corners (8-12px border-radius)
- Subtle shadows (`box-shadow: 0 1px 3px rgba(0,0,0,0.1)`)
- Card-based layout
- Modal sheets for details

---

## 📡 API Endpoints

### Public Endpoints (No Auth)

- `POST /api/auth/login` - Authenticate user
- `GET /login.html` - Login page

### Protected Endpoints (Auth Required)

- `GET /` - Dashboard UI
- `GET /api/auth/me` - Current user info
- `POST /api/auth/logout` - Logout

### Admin API (Proxied to Vigil Gateway)

Dashboard proxies these to Vigil:
- `GET /api/v1/audit/logs` - Get audit logs
- `GET /api/v1/audit/logs/{request_id}` - Get log detail
- `GET /api/v1/policies` - Get policy config
- `POST /api/v1/policies/update` - Update policies
- `GET /api/v1/keys/active` - Get active signing keys
- `POST /api/v1/compliance/export` - Export logs
- `GET /api/v1/compliance/verify-merkle` - Verify Merkle chain

---

## 🔐 RBAC (Role-Based Access Control)

### Roles & Permissions

```python
ROLE_PERMISSIONS = {
    "admin": [
        "read_logs",
        "write_policies",
        "view_keys",
        "export_logs",
        "manage_users"
    ],
    "auditor": [
        "read_logs",
        "export_logs"
    ],
    "viewer": [
        "read_logs"
    ]
}
```

### Adding New Users

```python
# dashboard_server.py
USERS = {
    "new_user": {
        "password_hash": hashlib.sha256("password".encode()).hexdigest(),
        "role": "auditor"
    }
}
```

---

## 💰 OSS vs Paid Feature Split

### Open Source (Free)

- ✅ Audit log viewer (basic)
- ✅ Policy configuration
- ✅ Docker Compose demo
- ✅ Basic authentication
- ✅ Export to JSON/CSV

### Paid (Enterprise)

- 💎 **Hosted Vigil endpoint** (SaaS)
- 💎 **SSO/SAML integration** (Okta, Auth0, Azure AD)
- 💎 **Advanced RBAC** (custom roles, team permissions)
- 💎 **Real-time alerts** (Slack, PagerDuty, email)
- 💎 **Compliance reports** (SOC2, ISO27001, GDPR)
- 💎 **Retention policies** (30/60/90 days)
- 💎 **Multi-tenancy** (white-label dashboard)
- 💎 **SLA monitoring** (uptime, latency dashboards)
- 💎 **Professional support** (24/7)

---

## 🌐 Hosted SaaS Model

### Architecture

```
Customer App
     ↓
Vigil Gateway (Customer VPC)
     ↓
AgentShield (Our Backend)
     ↓
Dashboard (Hosted - dashboard.vigil.ai)
```

### Pricing Tiers

| Tier | Price | Audit Logs | Retention | Support |
|------|-------|------------|-----------|---------|
| **Free** | $0/mo | 1K logs/mo | 7 days | Community |
| **Starter** | $49/mo | 10K logs/mo | 30 days | Email |
| **Pro** | $299/mo | 100K logs/mo | 90 days | Priority |
| **Enterprise** | Custom | Unlimited | Custom | 24/7 Dedicated |

---

## 📦 Deployment Options

### Option 1: Docker Compose (Development)

```bash
docker-compose up -d
```

Access: `http://localhost:3000`

### Option 2: Kubernetes (Production)

```bash
kubectl apply -f k8s-dashboard.yaml
```

Access via Ingress: `https://vigil-dashboard.yourdomain.com`

### Option 3: Hosted SaaS

Sign up at: `https://dashboard.vigil.ai`

---

## 🔧 Configuration

### Environment Variables

```bash
# Dashboard Server
DASHBOARD_SECRET_KEY=your-secret-key-here
VIGIL_GATEWAY_URL=http://localhost:8000
APPEND_LOG_PATH=/app/logs/vigil_audit.jsonl

# Authentication (Optional)
AUTH_PROVIDER=local  # local, ldap, oauth2, saml
LDAP_SERVER=ldap://your-ldap-server
OAUTH2_CLIENT_ID=your-client-id
OAUTH2_CLIENT_SECRET=your-client-secret

# Session
SESSION_TIMEOUT_MINUTES=60
```

---

## 📸 Screenshots

### Audit Logs
![Audit Logs](docs/screenshots/audit-logs.png)

### Policy Configuration
![Policies](docs/screenshots/policies.png)

### Detail Modal
![Detail View](docs/screenshots/detail-modal.png)

---

## 🧪 Testing

```bash
# Start services
docker-compose up -d

# Test login
curl -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Test audit logs (requires session cookie)
curl http://localhost:3000/api/v1/audit/logs \
  -H "Cookie: session=..."
```

---

## 🚨 Security Best Practices

### Production Checklist

- [ ] Change default passwords
- [ ] Use strong `DASHBOARD_SECRET_KEY`
- [ ] Enable HTTPS (TLS certificates)
- [ ] Configure session timeout
- [ ] Enable audit logging for dashboard access
- [ ] Restrict network access (VPN, IP whitelist)
- [ ] Use database-backed authentication
- [ ] Enable rate limiting on login endpoint
- [ ] Regular security updates

---

## 📄 License

Apache 2.0

---

## 🤝 Contributing

Contributions welcome! Focus areas:
- SSO integrations (OAuth2, SAML)
- Database backends (PostgreSQL, MongoDB)
- Advanced visualizations (charts, graphs)
- Mobile-responsive design improvements

---

## 📬 Support

- **Community**: GitHub Issues
- **Pro/Enterprise**: support@vigil.ai
- **Documentation**: https://docs.vigil.ai
- **Slack**: https://vigil-community.slack.com

---

**The audit dashboard is the core monetization feature. Companies pay for visibility, compliance, and governance.**
