#!/usr/bin/env python3
"""
Authentication & Billing API Endpoints
Add these to your local_server.py or create separate auth_server.py
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os

from auth_manager import AuthManager, require_auth, check_usage_limits
from billing_manager import BillingManager, PLANS

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

auth = AuthManager()
billing = BillingManager()

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register new user"""
    data = request.json
    
    email = data.get('email')
    password = data.get('password')
    full_name = data.get('full_name')
    company = data.get('company')
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    
    result, status = auth.register_user(email, password, full_name, company)
    return jsonify(result), status


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    data = request.json
    
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    
    result, status = auth.login_user(email, password)
    return jsonify(result), status


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get current user info"""
    tenant_info = auth.get_tenant_info(request.tenant_id)
    subscription_info = billing.get_subscription_info(request.tenant_id)
    
    return jsonify({
        "user_id": request.user_id,
        "email": request.user_email,
        "tenant": tenant_info,
        "subscription": subscription_info
    })


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    """Logout user (client should delete token)"""
    return jsonify({"success": True, "message": "Logged out successfully"})


# ============================================================================
# BILLING ENDPOINTS
# ============================================================================

@app.route('/api/billing/plans', methods=['GET'])
def get_plans():
    """Get available pricing plans"""
    return jsonify({"plans": PLANS})


@app.route('/api/billing/subscribe', methods=['POST'])
@require_auth
def subscribe():
    """Create subscription checkout session"""
    data = request.json
    plan = data.get('plan')
    
    if not plan or plan not in PLANS:
        return jsonify({"error": "Invalid plan"}), 400
    
    # Build success/cancel URLs
    base_url = request.host_url.rstrip('/')
    success_url = f"{base_url}/dashboard?payment=success"
    cancel_url = f"{base_url}/pricing?payment=cancelled"
    
    result, status = billing.create_checkout_session(
        request.tenant_id, plan, success_url, cancel_url
    )
    
    return jsonify(result), status


@app.route('/api/billing/subscription', methods=['GET'])
@require_auth
def get_subscription():
    """Get current subscription info"""
    info = billing.get_subscription_info(request.tenant_id)
    
    if not info:
        return jsonify({"error": "Subscription not found"}), 404
    
    return jsonify(info)


@app.route('/api/billing/cancel', methods=['POST'])
@require_auth
def cancel_subscription():
    """Cancel subscription"""
    result, status = billing.cancel_subscription(request.tenant_id)
    return jsonify(result), status


@app.route('/api/billing/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    result, status = billing.handle_webhook(payload, sig_header)
    return jsonify(result), status


# ============================================================================
# TENANT & API KEY MANAGEMENT
# ============================================================================

@app.route('/api/tenants/keys', methods=['GET'])
@require_auth
def get_api_keys():
    """Get tenant's API keys"""
    import sqlite3
    
    conn = sqlite3.connect('vigil_users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT api_key, name, created_at, last_used, is_active
        FROM api_keys WHERE tenant_id = ?
    ''', (request.tenant_id,))
    
    keys = []
    for row in cursor.fetchall():
        keys.append({
            "key": row[0],
            "name": row[1],
            "created_at": row[2],
            "last_used": row[3],
            "is_active": bool(row[4])
        })
    
    conn.close()
    return jsonify({"keys": keys})


@app.route('/api/tenants/keys', methods=['POST'])
@require_auth
def create_api_key():
    """Create new API key"""
    import sqlite3
    import secrets
    
    data = request.json
    name = data.get('name', 'API Key')
    
    api_key = f"vigil_{secrets.token_hex(24)}"
    
    conn = sqlite3.connect('vigil_users.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO api_keys (tenant_id, api_key, name)
        VALUES (?, ?, ?)
    ''', (request.tenant_id, api_key, name))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "api_key": api_key,
        "name": name
    }), 201


@app.route('/api/tenants/usage', methods=['GET'])
@require_auth
def get_usage():
    """Get usage statistics"""
    import sqlite3
    from datetime import datetime, timedelta
    
    conn = sqlite3.connect('vigil_users.db')
    cursor = conn.cursor()
    
    # Get last 30 days usage
    start_date = (datetime.utcnow() - timedelta(days=30)).date()
    
    cursor.execute('''
        SELECT date, request_count, agent_count
        FROM usage_tracking
        WHERE tenant_id = ? AND date >= ?
        ORDER BY date DESC
    ''', (request.tenant_id, start_date))
    
    usage_data = []
    total_requests = 0
    max_agents = 0
    
    for row in cursor.fetchall():
        date_str, requests, agents = row
        usage_data.append({
            "date": date_str,
            "requests": requests,
            "agents": agents
        })
        total_requests += requests
        max_agents = max(max_agents, agents)
    
    conn.close()
    
    # Get limits
    tenant_info = auth.get_tenant_info(request.tenant_id)
    
    return jsonify({
        "usage": usage_data,
        "summary": {
            "total_requests": total_requests,
            "max_agents": max_agents,
            "request_limit": tenant_info['request_limit'],
            "agent_limit": tenant_info['agent_limit']
        }
    })


# ============================================================================
# SERVE DASHBOARD
# ============================================================================

@app.route('/')
def serve_landing():
    """Serve landing page"""
    return send_from_directory('.', 'landing.html')


@app.route('/dashboard')
@app.route('/dashboard/<path:path>')
def serve_dashboard(path=''):
    """Serve dashboard (requires auth)"""
    return send_from_directory('.', 'dashboard_auth.html')


@app.route('/pricing')
def serve_pricing():
    """Serve pricing page"""
    return send_from_directory('.', 'pricing.html')


if __name__ == '__main__':
    print("🛡️  Vigil Authentication Server")
    print("=" * 60)
    print("Endpoints:")
    print("  POST /api/auth/register    - Register new user")
    print("  POST /api/auth/login       - Login")
    print("  GET  /api/auth/me          - Get current user")
    print("  GET  /api/billing/plans    - Get pricing plans")
    print("  POST /api/billing/subscribe - Subscribe to plan")
    print("  GET  /api/billing/subscription - Get subscription info")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8080, debug=True)
