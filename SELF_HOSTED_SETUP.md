# 🚀 Vigil Self-Hosted Setup Guide
## Complete Step-by-Step Instructions

---

## What You Now Have

I've created a complete **self-hosted authentication + billing system** for Vigil:

### 📁 **New Files Created:**

1. **`auth_manager.py`** - User authentication, sessions, multi-tenancy
2. **`billing_manager.py`** - Stripe integration, subscription management
3. **`auth_server.py`** - API endpoints for auth & billing
4. **`landing.html`** - Public landing page with sign-in/sign-up
5. **`pricing.html`** - Pricing page with Stripe integration

---

## 🎯 Step-by-Step Deployment

### **STEP 1: Install Dependencies**

```bash
cd /workspaces/vigil

# Add new requirements
cat >> requirements.txt << 'EOF'

# Authentication & Billing
PyJWT==2.8.0
stripe==7.4.0
flask-cors==4.0.0
EOF

# Install
pip install -r requirements.txt
```

---

### **STEP 2: Set Up Stripe**

#### 2.1 Create Stripe Account
1. Go to https://stripe.com
2. Create account
3. Go to Developers → API Keys
4. Copy your **Secret Key** (starts with `sk_test_...`)
5. Copy your **Publishable Key** (starts with `pk_test_...`)

#### 2.2 Create Products & Prices
```bash
# In Stripe Dashboard:
1. Products → Create Product "Vigil Starter" → Set price $99/month
   → Copy the Price ID (price_xxxx)

2. Create Product "Vigil Professional" → Set price $299/month
   → Copy the Price ID

3. Create Product "Vigil Enterprise" → Set price $999/month
   → Copy the Price ID
```

#### 2.3 Update `billing_manager.py`
```python
# Replace these lines in billing_manager.py:
PLANS = {
    'starter': {
        'stripe_price_id': 'price_YOUR_ACTUAL_STARTER_ID',  # ← Replace
        ...
    },
    'professional': {
        'stripe_price_id': 'price_YOUR_ACTUAL_PRO_ID',  # ← Replace
        ...
    },
    ...
}
```

#### 2.4 Setup Webhook
```bash
# In Stripe Dashboard:
1. Developers → Webhooks → Add endpoint
2. Endpoint URL: https://your-domain.com/api/billing/webhook
3. Select events:
   - checkout.session.completed
   - customer.subscription.created
   - customer.subscription.updated
   - customer.subscription.deleted
   - invoice.payment_succeeded
   - invoice.payment_failed
4. Copy Webhook Secret (whsec_...)
```

---

### **STEP 3: Configure Environment**

Create `.env` file:

```bash
cat > .env << 'EOF'
# JWT Secret (generate with: openssl rand -hex 32)
JWT_SECRET=your-super-secret-jwt-key-change-this

# Stripe Keys
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Database
AUTH_DB_PATH=vigil_users.db

# Server
PORT=8080
HOST=0.0.0.0
EOF
```

---

### **STEP 4: Initialize Database**

```bash
# Run this once to create tables
python3 << 'EOF'
from auth_manager import AuthManager
auth = AuthManager()
print("✅ Database initialized!")
EOF
```

---

### **STEP 5: Start the Server**

```bash
# Start authentication server
python auth_server.py

# Output:
# 🛡️  Vigil Authentication Server
# ============================================================
# Endpoints:
#   POST /api/auth/register    - Register new user
#   POST /api/auth/login       - Login
#   GET  /api/auth/me          - Get current user
#   ...
# ============================================================
# * Running on http://0.0.0.0:8080
```

---

### **STEP 6: Test the Flow**

#### 6.1 Open Landing Page
```bash
# Open browser to:
http://localhost:8080/
```

#### 6.2 Register New User
1. Click "Get Started Free"
2. Enter email, name, company, password
3. Click "Create Account"
4. You'll be redirected to dashboard

#### 6.3 View API Key
Your API key is automatically generated:
- Check the dashboard
- Or check database: `sqlite3 vigil_users.db "SELECT * FROM api_keys;"`

#### 6.4 Subscribe to Plan
1. Go to http://localhost:8080/pricing
2. Click "Subscribe" on any paid plan
3. You'll be redirected to Stripe checkout
4. Use test card: `4242 4242 4242 4242` (any future date, any CVC)
5. Complete checkout
6. You'll be redirected back to dashboard
7. Your plan will be updated!

---

### **STEP 7: Integrate with Existing Vigil Gateway**

Update `legacy/local_server.py` to use authentication:

```python
# Add to top of local_server.py
from auth_manager import AuthManager, require_auth, check_usage_limits

auth = AuthManager()

# Replace the /v1/chat/completions endpoint with:
@app.route('/v1/chat/completions', methods=['POST'])
@require_auth  # ← Add this decorator
@check_usage_limits  # ← Add this decorator
def transparent_proxy():
    # ... existing code ...
    
    # Use request.tenant_id instead of header
    tenant_id = request.tenant_id
    
    # Record usage
    auth.record_usage(tenant_id, requests=1)
    
    # ... rest of code ...
```

---

### **STEP 8: Deploy to Production**

#### Option A: Deploy on DigitalOcean (Easiest)

```bash
# 1. Create droplet (Ubuntu 22.04)
# 2. SSH into server
ssh root@your-server-ip

# 3. Clone repo
git clone https://github.com/rom-mvp/vigil.git
cd vigil

# 4. Install dependencies
apt update && apt install -y python3-pip nginx certbot
pip3 install -r requirements.txt

# 5. Copy .env file (with production Stripe keys)
nano .env

# 6. Setup nginx reverse proxy
cat > /etc/nginx/sites-available/vigil << 'NGINX'
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINX

ln -s /etc/nginx/sites-available/vigil /etc/nginx/sites-enabled/
nginx -t && systemctl restart nginx

# 7. Setup SSL
certbot --nginx -d yourdomain.com

# 8. Run with systemd
cat > /etc/systemd/system/vigil.service << 'SERVICE'
[Unit]
Description=Vigil Security Gateway
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/vigil
Environment="PATH=/usr/bin"
ExecStart=/usr/bin/python3 auth_server.py
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

systemctl enable vigil
systemctl start vigil
```

#### Option B: Deploy on AWS/Google Cloud

```bash
# Use Docker
docker build -t vigil .
docker run -d -p 8080:8080 --env-file .env vigil
```

---

## 🎨 How It Works (User Flow)

### **New User:**
1. Visits `yourdomain.com`
2. Clicks "Get Started Free"
3. Enters email + password
4. Account created with:
   - Free plan (1 agent, 10k requests/month)
   - Tenant ID (for multi-tenancy)
   - API key (for Vigil gateway)
5. Redirected to dashboard
6. Can now use Vigil with their API key

### **Upgrade Flow:**
1. User goes to Pricing page
2. Clicks "Subscribe" on Professional plan
3. Redirected to Stripe checkout
4. Enters payment info
5. Stripe processes payment
6. Webhook updates database:
   - Plan = "professional"
   - Agent limit = 50
   - Request limit = 1M/month
7. User can now use more agents!

### **Usage Enforcement:**
1. User makes request to `/v1/chat/completions`
2. `@require_auth` checks JWT token
3. `@check_usage_limits` checks current usage
4. If under limit → process request
5. If over limit → return 429 error with "Upgrade required"
6. Usage recorded in database for billing

---

## 📊 Database Schema

Your system has 4 tables:

### **users**
- id, email, password_hash, full_name, company
- role, created_at, last_login, is_active

### **tenants**
- id, tenant_id, owner_user_id
- plan, stripe_customer_id, stripe_subscription_id
- agent_limit, request_limit, subscription_status

### **api_keys**
- id, tenant_id, api_key, name
- created_at, last_used, is_active

### **usage_tracking**
- id, tenant_id, date
- request_count, agent_count

---

## 🔧 Customization

### Add More Plans
Edit `billing_manager.py`:
```python
PLANS = {
    'custom_plan': {
        'name': 'Custom',
        'price': 499,
        'stripe_price_id': 'price_xxxx',
        'agent_limit': 100,
        'request_limit': 5000000,
        'features': [...]
    }
}
```

### Change Pricing
Just update Stripe prices - webhook will sync automatically

### Add Features by Plan
```python
# In your code:
tenant = auth.get_tenant_info(tenant_id)
if tenant['plan'] in ['professional', 'enterprise']:
    # Enable advanced features
    enable_custom_policies()
```

---

## 📈 Monitoring

### Check Users
```bash
sqlite3 vigil_users.db "SELECT email, plan, created_at FROM users JOIN tenants ON users.id = tenants.owner_user_id;"
```

### Check Revenue
```bash
# In Stripe Dashboard → Reports
# Shows MRR, churn, new subscriptions, etc.
```

### Check Usage
```bash
sqlite3 vigil_users.db "SELECT tenant_id, SUM(request_count) as total_requests FROM usage_tracking GROUP BY tenant_id;"
```

---

## 🚀 Next Steps

1. **Customize branding** - Update colors, logo in HTML files
2. **Add email notifications** - Use SendGrid/Mailgun for signup/billing emails
3. **Add analytics** - Track signups, conversions, usage
4. **Add support chat** - Integrate Intercom/Crisp
5. **Add documentation** - Create /docs page with API guides
6. **Add status page** - Create status.yourdomain.com

---

## 💰 Revenue Tracking

### Expected Revenue (Example):
- 100 free users → $0
- 20 Starter users → 20 × $99 = $1,980/month
- 10 Pro users → 10 × $299 = $2,990/month
- 2 Enterprise → 2 × $999 = $1,998/month

**Total MRR: $6,968/month** 🎉

---

## 🆘 Troubleshooting

### "Invalid Stripe keys"
→ Check `.env` file has correct `STRIPE_SECRET_KEY`

### "Webhook signature failed"
→ Update `STRIPE_WEBHOOK_SECRET` with correct value from Stripe

### "Database locked"
→ Only one process should write to SQLite. Use PostgreSQL for production.

### "Token expired"
→ User needs to login again. Token expires after 24 hours.

---

## 📞 Support

Need help? 
- Check logs: `tail -f /tmp/vigil_server.log`
- Database: `sqlite3 vigil_users.db`
- Stripe logs: Stripe Dashboard → Developers → Logs

---

## ✅ You're Ready!

Your Vigil self-hosted system now has:
- ✅ User registration & login
- ✅ JWT authentication
- ✅ Multi-tenancy
- ✅ Stripe billing
- ✅ Usage limits & tracking
- ✅ API key management
- ✅ Beautiful landing page
- ✅ Pricing page
- ✅ Dashboard integration

**Start selling Vigil today!** 🚀
