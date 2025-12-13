#!/usr/bin/env python3
"""
Authentication & User Management for Vigil
Handles user registration, login, session management
"""

import os
import jwt
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session

# Secret key for JWT - CHANGE THIS IN PRODUCTION
JWT_SECRET = os.getenv('JWT_SECRET', 'change-this-secret-key-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# Database for users
DB_PATH = os.getenv('AUTH_DB_PATH', 'vigil_users.db')


class AuthManager:
    """Manage user authentication and sessions"""
    
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize user database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                company TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                role TEXT DEFAULT 'user'
            )
        ''')
        
        # Tenants table (for multi-tenancy)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT UNIQUE NOT NULL,
                owner_user_id INTEGER,
                name TEXT NOT NULL,
                plan TEXT DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                subscription_status TEXT DEFAULT 'inactive',
                agent_limit INTEGER DEFAULT 1,
                request_limit INTEGER DEFAULT 10000,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_user_id) REFERENCES users(id)
            )
        ''')
        
        # API keys table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            )
        ''')
        
        # Usage tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                date DATE NOT NULL,
                request_count INTEGER DEFAULT 0,
                agent_count INTEGER DEFAULT 0,
                UNIQUE(tenant_id, date),
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def hash_password(self, password):
        """Hash password with salt"""
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"{salt}${pwd_hash.hex()}"
    
    def verify_password(self, password, password_hash):
        """Verify password against hash"""
        try:
            salt, hash_value = password_hash.split('$')
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return pwd_hash.hex() == hash_value
        except:
            return False
    
    def register_user(self, email, password, full_name=None, company=None):
        """Register new user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Check if email already exists
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                return {"error": "Email already registered"}, 400
            
            # Hash password
            password_hash = self.hash_password(password)
            
            # Create user
            cursor.execute('''
                INSERT INTO users (email, password_hash, full_name, company, role)
                VALUES (?, ?, ?, ?, ?)
            ''', (email, password_hash, full_name, company, 'user'))
            
            user_id = cursor.lastrowid
            
            # Create default tenant for user
            tenant_id = f"tenant-{secrets.token_hex(8)}"
            tenant_name = company or email.split('@')[0]
            
            cursor.execute('''
                INSERT INTO tenants (tenant_id, owner_user_id, name)
                VALUES (?, ?, ?)
            ''', (tenant_id, user_id, tenant_name))
            
            # Create initial API key
            api_key = f"vigil_{secrets.token_hex(24)}"
            cursor.execute('''
                INSERT INTO api_keys (tenant_id, api_key, name)
                VALUES (?, ?, ?)
            ''', (tenant_id, api_key, 'Default Key'))
            
            conn.commit()
            
            # Generate JWT token
            token = self.generate_token(user_id, email, tenant_id)
            
            return {
                "success": True,
                "user_id": user_id,
                "email": email,
                "tenant_id": tenant_id,
                "api_key": api_key,
                "token": token
            }, 201
            
        except Exception as e:
            conn.rollback()
            return {"error": str(e)}, 500
        finally:
            conn.close()
    
    def login_user(self, email, password):
        """Login user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Get user
            cursor.execute('''
                SELECT u.id, u.email, u.password_hash, u.is_active, t.tenant_id
                FROM users u
                LEFT JOIN tenants t ON u.id = t.owner_user_id
                WHERE u.email = ?
            ''', (email,))
            
            result = cursor.fetchone()
            
            if not result:
                return {"error": "Invalid credentials"}, 401
            
            user_id, email, password_hash, is_active, tenant_id = result
            
            if not is_active:
                return {"error": "Account is deactivated"}, 403
            
            # Verify password
            if not self.verify_password(password, password_hash):
                return {"error": "Invalid credentials"}, 401
            
            # Update last login
            cursor.execute('''
                UPDATE users SET last_login = ? WHERE id = ?
            ''', (datetime.utcnow(), user_id))
            conn.commit()
            
            # Generate JWT token
            token = self.generate_token(user_id, email, tenant_id)
            
            # Get API keys
            cursor.execute('''
                SELECT api_key, name FROM api_keys 
                WHERE tenant_id = ? AND is_active = 1
            ''', (tenant_id,))
            api_keys = [{"key": key, "name": name} for key, name in cursor.fetchall()]
            
            return {
                "success": True,
                "user_id": user_id,
                "email": email,
                "tenant_id": tenant_id,
                "api_keys": api_keys,
                "token": token
            }, 200
            
        finally:
            conn.close()
    
    def generate_token(self, user_id, email, tenant_id):
        """Generate JWT token"""
        payload = {
            'user_id': user_id,
            'email': email,
            'tenant_id': tenant_id,
            'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
            'iat': datetime.utcnow()
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def verify_token(self, token):
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def get_tenant_info(self, tenant_id):
        """Get tenant information and limits"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT tenant_id, name, plan, agent_limit, request_limit, subscription_status
            FROM tenants WHERE tenant_id = ?
        ''', (tenant_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        return {
            "tenant_id": result[0],
            "name": result[1],
            "plan": result[2],
            "agent_limit": result[3],
            "request_limit": result[4],
            "subscription_status": result[5]
        }
    
    def check_usage_limits(self, tenant_id):
        """Check if tenant is within usage limits"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get tenant limits
        cursor.execute('''
            SELECT agent_limit, request_limit FROM tenants WHERE tenant_id = ?
        ''', (tenant_id,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False, "Tenant not found"
        
        agent_limit, request_limit = result
        
        # Get current usage (today)
        today = datetime.utcnow().date()
        cursor.execute('''
            SELECT request_count, agent_count FROM usage_tracking
            WHERE tenant_id = ? AND date = ?
        ''', (tenant_id, today))
        
        usage = cursor.fetchone()
        conn.close()
        
        if not usage:
            return True, None  # No usage yet
        
        request_count, agent_count = usage
        
        if request_count >= request_limit:
            return False, f"Request limit exceeded ({request_count}/{request_limit})"
        
        if agent_count > agent_limit:
            return False, f"Agent limit exceeded ({agent_count}/{agent_limit})"
        
        return True, None
    
    def record_usage(self, tenant_id, requests=1, agents=0):
        """Record usage for billing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.utcnow().date()
        
        cursor.execute('''
            INSERT INTO usage_tracking (tenant_id, date, request_count, agent_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(tenant_id, date) DO UPDATE SET
                request_count = request_count + ?,
                agent_count = MAX(agent_count, ?)
        ''', (tenant_id, today, requests, agents, requests, agents))
        
        conn.commit()
        conn.close()


def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        token = auth_header.split(' ')[1]
        auth = AuthManager()
        payload = auth.verify_token(token)
        
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401
        
        # Add user info to request context
        request.user_id = payload['user_id']
        request.user_email = payload['email']
        request.tenant_id = payload['tenant_id']
        
        return f(*args, **kwargs)
    
    return decorated_function


def check_usage_limits(f):
    """Decorator to check usage limits before processing"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        tenant_id = getattr(request, 'tenant_id', None)
        
        if not tenant_id:
            return jsonify({"error": "Tenant ID not found"}), 400
        
        auth = AuthManager()
        allowed, error_msg = auth.check_usage_limits(tenant_id)
        
        if not allowed:
            return jsonify({"error": error_msg, "upgrade_required": True}), 429
        
        return f(*args, **kwargs)
    
    return decorated_function
