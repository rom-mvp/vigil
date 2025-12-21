# 🎨 Customer Dashboard Setup Guide

## Overview

The customer-facing dashboard is where users sign up, manage API keys, configure their LLM providers, and monitor usage. This is different from the internal audit dashboard you currently have.

## Current State

**What You Have:**
- Internal audit dashboard at `frontend/` (for viewing logs/policies)
- Backend at `dashboard_server.py` (basic auth, log viewing)

**What You Need:**
- Customer-facing SaaS dashboard (signup, API keys, billing)
- Authentication system (email/password or OAuth)
- Vault management UI (store OpenAI/Anthropic keys)
- Usage metrics display

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Customer Dashboard (Public)                             │
│ URL: https://app.vigil.security                         │
│                                                         │
│ Pages:                                                  │
│ - /signup          → Create account                     │
│ - /login           → Sign in                            │
│ - /dashboard       → Usage metrics                      │
│ - /keys            → API key management                 │
│ - /vault           → LLM provider credentials           │
│ - /policies        → Security policies                  │
│ - /billing         → Usage & invoices                   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ Customer API (Backend)                                  │
│ Port: 3001                                              │
│                                                         │
│ Endpoints:                                              │
│ POST   /api/auth/signup                                 │
│ POST   /api/auth/login                                  │
│ GET    /api/keys                                        │
│ POST   /api/keys                                        │
│ DELETE /api/keys/{key_id}                               │
│ POST   /api/vault/credentials                           │
│ GET    /api/vault/credentials                           │
│ GET    /api/usage/current                               │
│ GET    /api/policies                                    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ PostgreSQL Database                                     │
│                                                         │
│ Tables:                                                 │
│ - tenants (id, email, company, created_at)              │
│ - api_keys (key_id, tenant_id, key_hash, created_at)   │
│ - vault_credentials (tenant_id, provider, api_key_enc) │
│ - usage_records (tenant_id, date, requests, tokens)    │
│ - subscriptions (tenant_id, tier, status)              │
└─────────────────────────────────────────────────────────┘
```

## Deployment Options

### Option 1: Extend Current Frontend (Recommended)

Your `frontend/` already has React + TypeScript. Extend it with customer pages:

```bash
cd frontend/

# Add new components
mkdir -p src/components/customer
touch src/components/customer/SignUpForm.tsx
touch src/components/customer/LoginForm.tsx
touch src/components/customer/APIKeyManager.tsx
touch src/components/customer/VaultConfig.tsx
touch src/components/customer/UsageDashboard.tsx

# Add routing
# Update src/App.tsx to include customer routes
```

**New Routes in App.tsx:**
```tsx
// Add to frontend/src/App.tsx
import SignUpForm from './components/customer/SignUpForm';
import LoginForm from './components/customer/LoginForm';
import APIKeyManager from './components/customer/APIKeyManager';
import VaultConfig from './components/customer/VaultConfig';
import UsageDashboard from './components/customer/UsageDashboard';

// Inside Routes:
<Route path="/signup" element={<SignUpForm />} />
<Route path="/login" element={<LoginForm />} />
<Route path="/dashboard" element={<UsageDashboard />} />
<Route path="/keys" element={<APIKeyManager />} />
<Route path="/vault" element={<VaultConfig />} />
```

### Option 2: Separate Customer App (Clean Separation)

Create a new React app specifically for customers:

```bash
# Create new customer app
npx create-react-app customer-dashboard --template typescript
cd customer-dashboard

# Install dependencies
npm install react-router-dom axios @tanstack/react-query
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

## Backend API Setup

### Create Customer API Service

Create `src/vigil/customer_api.py`:

```python
"""
Customer-facing API for SaaS dashboard
Handles signup, login, API key management, vault config
"""
from flask import Flask, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import psycopg2
import os
import jwt
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

app = Flask(__name__)
app.secret_key = os.environ.get('CUSTOMER_API_SECRET', secrets.token_hex(32))

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://vigil:vigil_password@localhost:5432/vigil_audit')

# Encryption key for vault (store securely in production!)
VAULT_ENCRYPTION_KEY = os.environ.get('VAULT_ENCRYPTION_KEY', Fernet.generate_key())
cipher = Fernet(VAULT_ENCRYPTION_KEY)

# JWT settings
JWT_SECRET = os.environ.get('JWT_SECRET', secrets.token_hex(32))
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

def get_db():
    """Get database connection"""
    return psycopg2.connect(DATABASE_URL)

def generate_api_key():
    """Generate a new API key with vk_ prefix"""
    return f"vk_{secrets.token_urlsafe(32)}"

def hash_api_key(api_key):
    """Hash API key for storage"""
    from hashlib import sha256
    return sha256(api_key.encode()).hexdigest()

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """
    Create new tenant account
    
    Request:
    {
        "email": "user@example.com",
        "password": "secure_password",
        "company": "Acme Corp"
    }
    
    Response:
    {
        "tenant_id": "tenant_abc123",
        "email": "user@example.com",
        "api_key": "vk_..."
    }
    """
    data = request.json
    email = data.get('email')
    password = data.get('password')
    company = data.get('company', '')
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    # Validate email format
    import re
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({"error": "Invalid email format"}), 400
    
    # Hash password
    password_hash = generate_password_hash(password)
    
    # Generate tenant ID
    tenant_id = f"tenant_{secrets.token_urlsafe(16)}"
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Check if email already exists
        cur.execute("SELECT id FROM tenants WHERE email = %s", (email,))
        if cur.fetchone():
            return jsonify({"error": "Email already registered"}), 409
        
        # Create tenant
        cur.execute("""
            INSERT INTO tenants (id, email, password_hash, company, tier, created_at)
            VALUES (%s, %s, %s, %s, 'free', NOW())
            RETURNING id
        """, (tenant_id, email, password_hash, company))
        
        # Generate initial API key
        api_key = generate_api_key()
        api_key_hash = hash_api_key(api_key)
        
        cur.execute("""
            INSERT INTO api_keys (tenant_id, key_hash, name, created_at)
            VALUES (%s, %s, 'Default', NOW())
        """, (tenant_id, api_key_hash))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "tenant_id": tenant_id,
            "email": email,
            "api_key": api_key,  # Only shown once!
            "message": "Account created successfully. Save your API key - it won't be shown again."
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Login and get JWT token
    
    Request:
    {
        "email": "user@example.com",
        "password": "secure_password"
    }
    
    Response:
    {
        "token": "eyJ...",
        "tenant_id": "tenant_abc123"
    }
    """
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, password_hash, tier 
            FROM tenants 
            WHERE email = %s
        """, (email,))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result:
            return jsonify({"error": "Invalid credentials"}), 401
        
        tenant_id, password_hash, tier = result
        
        if not check_password_hash(password_hash, password):
            return jsonify({"error": "Invalid credentials"}), 401
        
        # Generate JWT token
        token = jwt.encode({
            'tenant_id': tenant_id,
            'email': email,
            'tier': tier,
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        return jsonify({
            "token": token,
            "tenant_id": tenant_id,
            "tier": tier
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/keys', methods=['GET'])
def list_keys():
    """
    List all API keys for tenant (excluding the actual key values)
    
    Headers: Authorization: Bearer <jwt_token>
    
    Response:
    {
        "keys": [
            {
                "id": "key_123",
                "name": "Production",
                "prefix": "vk_abc...",
                "created_at": "2025-01-15T10:00:00Z",
                "last_used": "2025-01-19T14:30:00Z"
            }
        ]
    }
    """
    tenant_id = get_tenant_from_token(request)
    if not tenant_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, name, key_prefix, created_at, last_used
            FROM api_keys
            WHERE tenant_id = %s
            ORDER BY created_at DESC
        """, (tenant_id,))
        
        keys = []
        for row in cur.fetchall():
            keys.append({
                "id": row[0],
                "name": row[1],
                "prefix": row[2],
                "created_at": row[3].isoformat(),
                "last_used": row[4].isoformat() if row[4] else None
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"keys": keys})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/keys', methods=['POST'])
def create_key():
    """
    Create new API key
    
    Request:
    {
        "name": "Production API Key"
    }
    
    Response:
    {
        "api_key": "vk_...",
        "message": "Save this key - it won't be shown again!"
    }
    """
    tenant_id = get_tenant_from_token(request)
    if not tenant_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    name = data.get('name', 'Unnamed Key')
    
    api_key = generate_api_key()
    api_key_hash = hash_api_key(api_key)
    key_prefix = api_key[:10] + "..."
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO api_keys (tenant_id, key_hash, key_prefix, name, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (tenant_id, api_key_hash, key_prefix, name))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "api_key": api_key,
            "message": "Save this key - it won't be shown again!"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/keys/<key_id>', methods=['DELETE'])
def revoke_key(key_id):
    """Revoke an API key"""
    tenant_id = get_tenant_from_token(request)
    if not tenant_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            DELETE FROM api_keys
            WHERE id = %s AND tenant_id = %s
        """, (key_id, tenant_id))
        
        if cur.rowcount == 0:
            return jsonify({"error": "Key not found"}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"message": "Key revoked successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/vault/credentials', methods=['POST'])
def store_credentials():
    """
    Store LLM provider credentials (encrypted)
    
    Request:
    {
        "provider": "openai",
        "api_key": "sk-proj-...",
        "endpoint": "https://api.openai.com/v1",  // optional
        "model": "gpt-4"  // optional default model
    }
    
    Response:
    {
        "message": "Credentials stored successfully"
    }
    """
    tenant_id = get_tenant_from_token(request)
    if not tenant_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    provider = data.get('provider')  # openai, anthropic, llama, etc.
    api_key = data.get('api_key')
    endpoint = data.get('endpoint', '')
    model = data.get('model', '')
    
    if not provider or not api_key:
        return jsonify({"error": "Provider and api_key required"}), 400
    
    # Encrypt the API key
    encrypted_key = cipher.encrypt(api_key.encode()).decode()
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Upsert credentials
        cur.execute("""
            INSERT INTO vault_credentials (tenant_id, provider, api_key_encrypted, endpoint, model, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, provider) 
            DO UPDATE SET 
                api_key_encrypted = EXCLUDED.api_key_encrypted,
                endpoint = EXCLUDED.endpoint,
                model = EXCLUDED.model,
                updated_at = NOW()
        """, (tenant_id, provider, encrypted_key, endpoint, model))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({"message": f"{provider.title()} credentials stored successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/vault/credentials', methods=['GET'])
def get_credentials():
    """
    Get configured providers (without showing API keys)
    
    Response:
    {
        "providers": [
            {
                "provider": "openai",
                "configured": true,
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4",
                "updated_at": "2025-01-19T10:00:00Z"
            }
        ]
    }
    """
    tenant_id = get_tenant_from_token(request)
    if not tenant_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT provider, endpoint, model, updated_at
            FROM vault_credentials
            WHERE tenant_id = %s
        """, (tenant_id,))
        
        providers = []
        for row in cur.fetchall():
            providers.append({
                "provider": row[0],
                "configured": True,
                "endpoint": row[1],
                "model": row[2],
                "updated_at": row[3].isoformat()
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"providers": providers})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/usage/current', methods=['GET'])
def get_usage():
    """
    Get current billing period usage
    
    Response:
    {
        "period": "2025-01",
        "requests": 12547,
        "tokens": 2345678,
        "blocked_threats": 23,
        "quota": {
            "requests_limit": 50000,
            "tokens_limit": 5000000,
            "requests_remaining": 37453,
            "tokens_remaining": 2654322
        }
    }
    """
    tenant_id = get_tenant_from_token(request)
    if not tenant_id:
        return jsonify({"error": "Unauthorized"}), 401
    
    # TODO: Query usage from Redis and database
    return jsonify({
        "period": datetime.now().strftime("%Y-%m"),
        "requests": 12547,
        "tokens": 2345678,
        "blocked_threats": 23,
        "quota": {
            "requests_limit": 50000,
            "tokens_limit": 5000000
        }
    })

def get_tenant_from_token(request):
    """Extract tenant_id from JWT token"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.replace('Bearer ', '')
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get('tenant_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3001, debug=True)
```

## Database Schema

Add these tables to your `schema.sql`:

```sql
-- Tenants (customers)
CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(64) PRIMARY KEY,  -- tenant_abc123
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    tier VARCHAR(20) DEFAULT 'free',  -- free, starter, pro, enterprise
    created_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'active'  -- active, suspended, deleted
);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA256 of vk_...
    key_prefix VARCHAR(20),  -- vk_abc... for display
    name VARCHAR(100),  -- "Production", "Staging", etc.
    created_at TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP,
    revoked BOOLEAN DEFAULT FALSE
);

-- Vault (encrypted LLM credentials)
CREATE TABLE IF NOT EXISTS vault_credentials (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,  -- openai, anthropic, llama, etc.
    api_key_encrypted TEXT NOT NULL,  -- Fernet encrypted
    endpoint VARCHAR(255),  -- Custom endpoint if needed
    model VARCHAR(100),  -- Default model
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, provider)
);

-- Usage tracking
CREATE TABLE IF NOT EXISTS usage_records (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    requests INT DEFAULT 0,
    tokens INT DEFAULT 0,
    blocked_threats INT DEFAULT 0,
    UNIQUE(tenant_id, date)
);

-- Subscriptions
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) REFERENCES tenants(id) ON DELETE CASCADE UNIQUE,
    tier VARCHAR(20) NOT NULL,  -- free, starter, pro, enterprise
    stripe_customer_id VARCHAR(100),
    stripe_subscription_id VARCHAR(100),
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active'  -- active, canceled, past_due
);

-- Indexes
CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_vault_tenant ON vault_credentials(tenant_id);
CREATE INDEX idx_usage_tenant_date ON usage_records(tenant_id, date);
```

## Docker Compose Update

Add the customer API service:

```yaml
# Add to docker-compose.yml

services:
  # ... existing services ...
  
  # Customer-facing API
  customer-api:
    build:
      context: .
      dockerfile: Dockerfile.customer-api
    container_name: vigil-customer-api
    ports:
      - "3001:3001"
    environment:
      - DATABASE_URL=postgresql://vigil:vigil_password@db:5432/vigil_audit
      - JWT_SECRET=${JWT_SECRET}
      - VAULT_ENCRYPTION_KEY=${VAULT_ENCRYPTION_KEY}
    depends_on:
      - db
    networks:
      - vigil-network
    restart: always

  # Customer Dashboard (React SPA)
  customer-dashboard:
    build:
      context: ./customer-dashboard
      dockerfile: Dockerfile
    container_name: vigil-customer-dashboard
    ports:
      - "3000:80"  # Nginx serving React build
    depends_on:
      - customer-api
    networks:
      - vigil-network
    restart: always
```

## Quick Start

### 1. Set up database
```bash
psql -U vigil -d vigil_audit -f schema.sql
```

### 2. Generate secrets
```bash
export JWT_SECRET=$(openssl rand -hex 32)
export VAULT_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

### 3. Run customer API
```bash
cd src/vigil
python customer_api.py
```

### 4. Build dashboard
```bash
cd frontend  # or customer-dashboard
npm install
npm run build
npm start
```

### 5. Access dashboard
- Local: http://localhost:3000
- Production: https://app.vigil.security

## URLs Summary

| Service | Local | Production |
|---------|-------|------------|
| Customer Dashboard | http://localhost:3000 | https://app.vigil.security |
| Customer API | http://localhost:3001 | https://api.vigil.security/customer |
| Vigil Gateway | http://localhost:8000 | https://api.vigil.security/v1 |
| Internal Audit Dashboard | http://localhost:9000 | (Internal only) |

---

## Next Steps

1. **Implement frontend components** (SignUpForm, LoginForm, etc.)
2. **Add Stripe integration** for billing
3. **Set up email service** (SendGrid/Mailgun) for verification
4. **Deploy to cloud** (Vercel for frontend, AWS for backend)
5. **Add OAuth** (Google, GitHub login)
