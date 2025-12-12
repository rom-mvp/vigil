"""
Vigil Dashboard Server
Serves the audit dashboard UI and handles authentication/RBAC
"""
from flask import Flask, send_from_directory, request, jsonify, session
from functools import wraps
import os
import secrets
import hashlib

app = Flask(__name__, static_folder='.')
app.secret_key = os.environ.get('DASHBOARD_SECRET_KEY', secrets.token_hex(32))

# Simple in-memory user store (replace with database in production)
USERS = {
    "admin": {
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
        "role": "admin"
    },
    "auditor": {
        "password_hash": hashlib.sha256("auditor123".encode()).hexdigest(),
        "role": "auditor"
    }
}

# Role-based access control
ROLE_PERMISSIONS = {
    "admin": ["read_logs", "write_policies", "view_keys", "export_logs", "manage_users"],
    "auditor": ["read_logs", "export_logs"],
    "viewer": ["read_logs"]
}

def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

def require_permission(permission):
    """Decorator to require specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return jsonify({"error": "Authentication required"}), 401
            
            user = session['user']
            role = USERS.get(user, {}).get('role', 'viewer')
            permissions = ROLE_PERMISSIONS.get(role, [])
            
            if permission not in permissions:
                return jsonify({"error": "Insufficient permissions"}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
@require_auth
def index():
    """Serve the dashboard HTML."""
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Authenticate user."""
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    user = USERS.get(username)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if password_hash != user['password_hash']:
        return jsonify({"error": "Invalid credentials"}), 401
    
    session['user'] = username
    session['role'] = user['role']
    
    return jsonify({
        "success": True,
        "username": username,
        "role": user['role'],
        "permissions": ROLE_PERMISSIONS.get(user['role'], [])
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user."""
    session.pop('user', None)
    session.pop('role', None)
    return jsonify({"success": True})

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get current authenticated user."""
    username = session.get('user')
    user = USERS.get(username, {})
    return jsonify({
        "username": username,
        "role": user.get('role', 'viewer'),
        "permissions": ROLE_PERMISSIONS.get(user.get('role'), [])
    })

@app.route('/login.html')
def login_page():
    """Serve login page."""
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vigil Security - Login</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }

        .login-container {
            background: white;
            border-radius: 16px;
            padding: 48px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 400px;
        }

        h1 {
            text-align: center;
            margin-bottom: 32px;
            font-size: 28px;
            color: #333;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #555;
        }

        input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 15px;
        }

        input:focus {
            outline: none;
            border-color: #667eea;
        }

        button {
            width: 100%;
            padding: 14px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }

        button:hover {
            background: #5568d3;
        }

        .error {
            color: #ff3b30;
            font-size: 14px;
            margin-top: 8px;
            display: none;
        }

        .demo-users {
            margin-top: 24px;
            padding: 16px;
            background: #f5f5f5;
            border-radius: 8px;
            font-size: 13px;
            color: #666;
        }

        .demo-users strong {
            display: block;
            margin-bottom: 8px;
            color: #333;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>🔭 Vigil Security</h1>
        <form id="login-form">
            <div class="form-group">
                <label>Username</label>
                <input type="text" id="username" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" id="password" required>
            </div>
            <button type="submit">Sign In</button>
            <div class="error" id="error"></div>
        </form>

        <div class="demo-users">
            <strong>Demo Accounts:</strong>
            Admin: admin / admin123<br>
            Auditor: auditor / auditor123
        </div>
    </div>

    <script>
        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const error = document.getElementById('error');

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                if (response.ok) {
                    window.location.href = '/';
                } else {
                    error.textContent = 'Invalid credentials';
                    error.style.display = 'block';
                }
            } catch (err) {
                error.textContent = 'Login failed. Please try again.';
                error.style.display = 'block';
            }
        });
    </script>
</body>
</html>
    '''

if __name__ == '__main__':
    print("🔭 Vigil Dashboard running on http://0.0.0.0:3000")
    print("\nDemo Accounts:")
    print("  Admin:   admin / admin123")
    print("  Auditor: auditor / auditor123")
    app.run(host='0.0.0.0', port=3000, debug=False)
