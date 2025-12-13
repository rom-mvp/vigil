#!/usr/bin/env python3
"""
Stripe Billing Integration for Vigil
Handles subscriptions, payments, and webhooks
"""

import os
import stripe
import sqlite3
from datetime import datetime

# Stripe configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', 'sk_test_...')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', 'whsec_...')

# Pricing plans
PLANS = {
    'free': {
        'name': 'Free',
        'price': 0,
        'agent_limit': 1,
        'request_limit': 10000,
        'features': ['1 AI Agent', '10k requests/month', 'Basic audit logs']
    },
    'starter': {
        'name': 'Starter',
        'price': 99,
        'stripe_price_id': 'price_starter',  # Replace with your Stripe Price ID
        'agent_limit': 5,
        'request_limit': 100000,
        'features': ['5 AI Agents', '100k requests/month', 'Full audit logs', 'Email support']
    },
    'professional': {
        'name': 'Professional',
        'price': 299,
        'stripe_price_id': 'price_professional',  # Replace with your Stripe Price ID
        'agent_limit': 50,
        'request_limit': 1000000,
        'features': ['50 AI Agents', '1M requests/month', 'Advanced analytics', 'Priority support', 'Custom policies']
    },
    'enterprise': {
        'name': 'Enterprise',
        'price': 999,
        'stripe_price_id': 'price_enterprise',  # Replace with your Stripe Price ID
        'agent_limit': 999999,
        'request_limit': 999999999,
        'features': ['Unlimited Agents', 'Unlimited requests', 'Dedicated support', 'SLA guarantee', 'Custom integration']
    }
}


class BillingManager:
    """Manage Stripe billing and subscriptions"""
    
    def __init__(self, db_path='vigil_users.db'):
        self.db_path = db_path
    
    def create_checkout_session(self, tenant_id, plan, success_url, cancel_url):
        """Create Stripe checkout session for subscription"""
        
        if plan not in PLANS or plan == 'free':
            return {"error": "Invalid plan"}, 400
        
        plan_info = PLANS[plan]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get tenant info
        cursor.execute('''
            SELECT stripe_customer_id, owner_user_id FROM tenants WHERE tenant_id = ?
        ''', (tenant_id,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return {"error": "Tenant not found"}, 404
        
        stripe_customer_id, owner_user_id = result
        
        # Get user email
        cursor.execute('SELECT email FROM users WHERE id = ?', (owner_user_id,))
        user_email = cursor.fetchone()[0]
        
        # Create or get Stripe customer
        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=user_email,
                metadata={
                    'tenant_id': tenant_id,
                    'user_id': owner_user_id
                }
            )
            stripe_customer_id = customer.id
            
            # Update tenant with customer ID
            cursor.execute('''
                UPDATE tenants SET stripe_customer_id = ? WHERE tenant_id = ?
            ''', (stripe_customer_id, tenant_id))
            conn.commit()
        
        conn.close()
        
        # Create checkout session
        try:
            session = stripe.checkout.Session.create(
                customer=stripe_customer_id,
                success_url=success_url,
                cancel_url=cancel_url,
                mode='subscription',
                line_items=[{
                    'price': plan_info['stripe_price_id'],
                    'quantity': 1
                }],
                metadata={
                    'tenant_id': tenant_id,
                    'plan': plan
                }
            )
            
            return {
                "checkout_url": session.url,
                "session_id": session.id
            }, 200
            
        except Exception as e:
            return {"error": str(e)}, 500
    
    def handle_webhook(self, payload, sig_header):
        """Handle Stripe webhook events"""
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return {"error": "Invalid payload"}, 400
        except stripe.error.SignatureVerificationError:
            return {"error": "Invalid signature"}, 400
        
        # Handle different event types
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            self._handle_checkout_completed(session)
        
        elif event['type'] == 'customer.subscription.created':
            subscription = event['data']['object']
            self._handle_subscription_created(subscription)
        
        elif event['type'] == 'customer.subscription.updated':
            subscription = event['data']['object']
            self._handle_subscription_updated(subscription)
        
        elif event['type'] == 'customer.subscription.deleted':
            subscription = event['data']['object']
            self._handle_subscription_deleted(subscription)
        
        elif event['type'] == 'invoice.payment_succeeded':
            invoice = event['data']['object']
            self._handle_payment_succeeded(invoice)
        
        elif event['type'] == 'invoice.payment_failed':
            invoice = event['data']['object']
            self._handle_payment_failed(invoice)
        
        return {"success": True}, 200
    
    def _handle_checkout_completed(self, session):
        """Handle successful checkout"""
        tenant_id = session['metadata']['tenant_id']
        plan = session['metadata']['plan']
        subscription_id = session.get('subscription')
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        plan_info = PLANS[plan]
        
        cursor.execute('''
            UPDATE tenants SET
                plan = ?,
                stripe_subscription_id = ?,
                subscription_status = 'active',
                agent_limit = ?,
                request_limit = ?
            WHERE tenant_id = ?
        ''', (plan, subscription_id, plan_info['agent_limit'], 
              plan_info['request_limit'], tenant_id))
        
        conn.commit()
        conn.close()
    
    def _handle_subscription_created(self, subscription):
        """Handle subscription created"""
        customer_id = subscription['customer']
        subscription_id = subscription['id']
        status = subscription['status']
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tenants SET
                stripe_subscription_id = ?,
                subscription_status = ?
            WHERE stripe_customer_id = ?
        ''', (subscription_id, status, customer_id))
        
        conn.commit()
        conn.close()
    
    def _handle_subscription_updated(self, subscription):
        """Handle subscription updated"""
        subscription_id = subscription['id']
        status = subscription['status']
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tenants SET subscription_status = ?
            WHERE stripe_subscription_id = ?
        ''', (status, subscription_id))
        
        conn.commit()
        conn.close()
    
    def _handle_subscription_deleted(self, subscription):
        """Handle subscription cancelled"""
        subscription_id = subscription['id']
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Downgrade to free plan
        free_plan = PLANS['free']
        
        cursor.execute('''
            UPDATE tenants SET
                plan = 'free',
                subscription_status = 'cancelled',
                agent_limit = ?,
                request_limit = ?
            WHERE stripe_subscription_id = ?
        ''', (free_plan['agent_limit'], free_plan['request_limit'], subscription_id))
        
        conn.commit()
        conn.close()
    
    def _handle_payment_succeeded(self, invoice):
        """Handle successful payment"""
        # Log successful payment
        pass
    
    def _handle_payment_failed(self, invoice):
        """Handle failed payment"""
        customer_id = invoice['customer']
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE tenants SET subscription_status = 'past_due'
            WHERE stripe_customer_id = ?
        ''', (customer_id,))
        
        conn.commit()
        conn.close()
    
    def cancel_subscription(self, tenant_id):
        """Cancel user's subscription"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT stripe_subscription_id FROM tenants WHERE tenant_id = ?
        ''', (tenant_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result or not result[0]:
            return {"error": "No active subscription"}, 404
        
        subscription_id = result[0]
        
        try:
            # Cancel at period end (don't immediately cancel)
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
            
            return {
                "success": True,
                "cancels_at": subscription['cancel_at']
            }, 200
            
        except Exception as e:
            return {"error": str(e)}, 500
    
    def get_subscription_info(self, tenant_id):
        """Get subscription information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT plan, subscription_status, stripe_subscription_id, agent_limit, request_limit
            FROM tenants WHERE tenant_id = ?
        ''', (tenant_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        plan, status, sub_id, agent_limit, request_limit = result
        plan_info = PLANS.get(plan, PLANS['free'])
        
        # Get current usage
        today = datetime.utcnow().date()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT request_count, agent_count FROM usage_tracking
            WHERE tenant_id = ? AND date = ?
        ''', (tenant_id, today))
        
        usage = cursor.fetchone()
        conn.close()
        
        current_requests = usage[0] if usage else 0
        current_agents = usage[1] if usage else 0
        
        return {
            "plan": plan,
            "plan_name": plan_info['name'],
            "price": plan_info['price'],
            "status": status,
            "features": plan_info['features'],
            "limits": {
                "agents": agent_limit,
                "requests": request_limit
            },
            "usage": {
                "requests": current_requests,
                "agents": current_agents
            }
        }
