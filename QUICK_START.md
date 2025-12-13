# 🎯 Quick Start: Self-Hosted Vigil

Your complete **sign-in/out dashboard with Stripe billing** is ready!

---

## ⚡ Ultra-Quick Start (5 minutes)

```bash
# 1. Clone the repo (if not already)
git clone https://github.com/rom-mvp/vigil.git
cd vigil

# 2. Run the setup script
./start_auth.sh

# 3. Open browser
# → http://localhost:8080
```

That's it! You now have:
- ✅ Landing page with sign-up/sign-in
- ✅ User authentication (JWT)
- ✅ Multi-tenant system
- ✅ API key generation
- ✅ Pricing page ready for Stripe

---

## 🏗️ What You Got

### **System Architecture:**

```
User Visits Landing Page (landing.html)
    ↓
Clicks "Get Started" → Register (auth_manager.py)
    ↓
Account Created:
  • User record
  • Tenant ID (for multi-tenancy)
  • API key (for Vigil gateway)
  • Free plan (1 agent, 10k requests)
    ↓
Redirected to Dashboard
    ↓
User Can Now:
  • Make API requests with API key
  • View usage stats
  • Upgrade to paid plan
    ↓
Upgrade Flow:
  • Goes to Pricing Page
  • Clicks "Subscribe"
  • Redirected to Stripe Checkout
  • Pays → Webhook → Plan upgraded!
```

---

## 📂 Files You Have

| File | Purpose |
|------|---------|
| **auth_manager.py** | User login, sessions, multi-tenancy, usage tracking |
| **billing_manager.py** | Stripe integration, subscriptions, webhooks |
| **auth_server.py** | API endpoints (register, login, billing) |
| **landing.html** | Public landing page with modals for sign-in/up |
| **pricing.html** | Pricing page with 4 plans |
| **SELF_HOSTED_SETUP.md** | Complete detailed setup guide |
| **start_auth.sh** | One-command startup script |

---

## 🎨 User Journey

### **New User Signs Up:**

1. **Visit:** `http://localhost:8080/`
2. **Click:** "Get Started Free" button
3. **Fill form:**
   - Email: user@example.com
   - Name: John Doe
   - Company: Acme Inc
   - Password: mypassword123
4. **Click:** "Create Account"
5. **Result:** 
   ```json
   {
     "success": true,
     "email": "user@example.com",
     "tenant_id": "tenant-abc123",
     "api_key": "vigil_xyz789...",
     "token": "eyJ..."
   }
   ```
6. **Redirected to:** Dashboard (logged in!)

### **Existing User Logs In:**

1. **Visit:** `http://localhost:8080/`
2. **Click:** "Sign In" button
3. **Enter:** email + password
4. **Click:** "Sign In"
5. **Redirected to:** Dashboard

### **User Upgrades Plan:**

1. **Visit:** `http://localhost:8080/pricing`
2. **Click:** "Subscribe" on Professional plan
3. **Redirected to:** Stripe checkout (secure payment)
4. **Enter:** Credit card (test card: `4242 4242 4242 4242`)
5. **Complete:** Payment
6. **Stripe webhook:** Updates plan in database
7. **Result:** User now has Professional limits (50 agents, 1M requests)

---

## 💳 Stripe Setup (One-Time)

### **Step 1: Get Stripe Account**
```
1. Go to https://stripe.com
2. Sign up (free)
3. Go to Developers → API Keys
4. Copy "Secret key" (sk_test_...)
```

### **Step 2: Create Products**
```
1. Products → "Create product"
2. Name: "Vigil Starter"
3. Price: $99/month (recurring)
4. Save → Copy "Price ID" (price_...)
5. Repeat for Pro ($299) and Enterprise ($999)
```

### **Step 3: Add Keys to .env**
```bash
nano .env

# Update these:
STRIPE_SECRET_KEY=sk_test_your_actual_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
```

### **Step 4: Update Price IDs**
```bash
nano billing_manager.py

# Line ~30, update:
'starter': {
    'stripe_price_id': 'price_YOUR_STARTER_ID',  # ← Replace
    ...
},
```

### **Step 5: Setup Webhook**
```
1. Stripe Dashboard → Webhooks
2. Add endpoint: http://your-domain.com/api/billing/webhook
3. Select all subscription events
4. Copy "Signing secret" (whsec_...)
5. Add to .env
```

**Done!** Stripe is now integrated.

---

## 🔑 API Endpoints Available

### **Authentication:**
```bash
# Register
POST /api/auth/register
Body: {"email": "...", "password": "...", "full_name": "...", "company": "..."}
Response: {"token": "...", "api_key": "...", "tenant_id": "..."}

# Login
POST /api/auth/login
Body: {"email": "...", "password": "..."}
Response: {"token": "...", "tenant_id": "..."}

# Get current user
GET /api/auth/me
Headers: Authorization: Bearer <token>
Response: {"email": "...", "tenant": {...}, "subscription": {...}}
```

### **Billing:**
```bash
# Get plans
GET /api/billing/plans
Response: {"plans": {...}}

# Subscribe
POST /api/billing/subscribe
Headers: Authorization: Bearer <token>
Body: {"plan": "professional"}
Response: {"checkout_url": "https://checkout.stripe.com/..."}

# Cancel subscription
POST /api/billing/cancel
Headers: Authorization: Bearer <token>
Response: {"success": true, "cancels_at": 1234567890}
```

### **Tenant Management:**
```bash
# Get API keys
GET /api/tenants/keys
Headers: Authorization: Bearer <token>
Response: {"keys": [{key: "...", name: "..."}]}

# Create API key
POST /api/tenants/keys
Headers: Authorization: Bearer <token>
Body: {"name": "Production Key"}
Response: {"api_key": "vigil_..."}

# Get usage
GET /api/tenants/usage
Headers: Authorization: Bearer <token>
Response: {"usage": [...], "summary": {...}}
```

---

## 🎯 Pricing Plans

| Plan | Price | Agents | Requests | Features |
|------|-------|--------|----------|----------|
| **Free** | $0 | 1 | 10k/mo | Basic audit logs |
| **Starter** | $99/mo | 5 | 100k/mo | Full logs, email support |
| **Professional** | $299/mo | 50 | 1M/mo | Analytics, priority support, SLA |
| **Enterprise** | $999/mo | Unlimited | Unlimited | Dedicated support, on-premise |

---

## 🚀 Deploy to Production

### **Option 1: DigitalOcean (Easiest)**
```bash
# 1. Create $5/month droplet
# 2. SSH in
ssh root@your-ip

# 3. Clone and setup
git clone https://github.com/rom-mvp/vigil.git
cd vigil
./start_auth.sh

# 4. Setup domain
# Point your-domain.com → your-ip
# Install nginx + certbot for HTTPS
```

### **Option 2: Docker**
```bash
docker build -t vigil .
docker run -d -p 8080:8080 --env-file .env vigil
```

### **Option 3: Heroku**
```bash
heroku create your-app-name
git push heroku main
heroku open
```

---

## 📊 How to Make Money

### **Pricing Strategy:**
```
Free Plan → Get users hooked
Starter $99 → Small teams (target: 50 users)
Pro $299 → Growing companies (target: 20 users)
Enterprise $999 → Large orgs (target: 5 users)

Expected Monthly Revenue:
- 50 × $99 = $4,950
- 20 × $299 = $5,980
- 5 × $999 = $4,995
━━━━━━━━━━━━━━━━━━━━━
Total MRR: $15,925/month 🎉
```

### **Growth Tactics:**
1. **Product Hunt Launch** - Get initial users
2. **GitHub README** - Drive organic traffic
3. **Dev.to Articles** - Share integration guides
4. **Twitter** - Share security tips, tag #aiagents
5. **Cold Email** - Reach out to AI companies

---

## ✅ Testing Checklist

```bash
# Test 1: Register new user
curl -X POST http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'

# Test 2: Login
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'

# Test 3: Get user info (use token from login)
curl http://localhost:8080/api/auth/me \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test 4: Check plans
curl http://localhost:8080/api/billing/plans
```

---

## 🎉 You're Ready to Sell!

Your system now has everything you need:

✅ **Landing page** - Beautiful, converts visitors  
✅ **Sign-up/Login** - Secure JWT auth  
✅ **Multi-tenancy** - Isolated per customer  
✅ **API keys** - Auto-generated per tenant  
✅ **Usage tracking** - Know who uses what  
✅ **Billing** - Stripe integration  
✅ **Plans** - Free → Paid upgrade path  
✅ **Limits** - Enforce plan restrictions  
✅ **Webhooks** - Sync subscription status  

**Start promoting and watch the signups roll in!** 🚀

---

## 📞 Next Steps

1. **Setup Stripe** (10 minutes)
2. **Customize branding** - Change colors, logo
3. **Deploy to production** - Use DigitalOcean
4. **Setup domain** - your-product.com
5. **Launch on Product Hunt** - Get first users
6. **Add analytics** - Track conversions

**Need help?** Check `SELF_HOSTED_SETUP.md` for detailed instructions.

---

**Happy Selling! 💰**
