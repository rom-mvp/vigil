"""
Vigil Dashboard Server
Serves the React audit dashboard UI and handles authentication/RBAC
"""
from flask import Flask, send_from_directory, request, jsonify, session
from functools import wraps
import os
import secrets
import hashlib
import json
import time

# Use our updated MerkleLogStore
try:
    from merkle_log_store import MerkleLogStore
except ImportError:
    # Fallback if running directly in dev without package context
    try:
        from .merkle_log_store import MerkleLogStore
    except ImportError:
        # Fallback for direct execution
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from merkle_log_store import MerkleLogStore

# Define static folder as the build output
STATIC_FOLDER = os.path.join(os.getcwd(), 'static_build')
app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path='')

app.secret_key = os.environ.get('DASHBOARD_SECRET_KEY', secrets.token_hex(32))
ADMIN_TOKEN = os.environ.get('DASHBOARD_ADMIN_TOKEN')
APPEND_LOG_PATH = os.getenv("APPEND_LOG_PATH", "/app/logs/vigil_audit.jsonl")

# Initialize store
log_store = MerkleLogStore(APPEND_LOG_PATH)

# Public paths that don't require authentication
# Note: In a SPA, most paths are handled by the client router, 
# but we need to allow the initial load of index.html and assets.
PUBLIC_PATHS = {"/", "/health", "/favicon.ico", "/assets"}

# Simple in-memory user store (replace with Redis/DB in production if desired)
# For now, we are keeping this simple as requested only for Rate Limiting to go to Redis.
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

def enforce_auth():
    """Enforce authentication for API endpoints."""
    hdr = request.headers.get("Authorization", "")
    bearer = hdr.replace("Bearer ", "") if hdr.startswith("Bearer ") else None
    x_token = request.headers.get("X-Admin-Token")

    # Accept admin token OR existing session login
    if ADMIN_TOKEN and (bearer == ADMIN_TOKEN or x_token == ADMIN_TOKEN):
        return None

    if session.get("user"):
        return None

    return jsonify({"error": "Authentication required"}), 401


def require_permission(permission):
    """Decorator to require specific permission (after enforce_auth)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                return jsonify({"error": "Authentication required"}), 401
            
            role = 'admin' if user == 'admin-token' else USERS.get(user, {}).get('role', 'viewer')
            permissions = ROLE_PERMISSIONS.get(role, [])
            
            if permission not in permissions:
                return jsonify({"error": "Insufficient permissions"}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.before_request
def auth_gate():
    """Allow public assets; protect APIs with token/session."""
    p = request.path

    # Allow health check
    if p == "/health":
        return None

    # Protect API endpoints only
    if p.startswith("/api/"):
        # Allow login endpoint
        if p == "/api/auth/login":
            return None
        return enforce_auth()

    return None


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Serve React App or Static Assets."""
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        # Fallback to index.html for React Router
        if os.path.exists(os.path.join(app.static_folder, 'index.html')):
            return send_from_directory(app.static_folder, 'index.html')
        else:
            return "Dashboard build not found. Please run the build step.", 404

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
def get_current_user():
    """Get current authenticated user."""
    username = session.get('user')
    if not username:
        return jsonify({"error": "Not authenticated"}), 401
    
    if username == 'admin-token':
        return jsonify({
            "username": "admin-token",
            "role": "admin",
            "permissions": ROLE_PERMISSIONS.get('admin', [])
        })

    user = USERS.get(username, {})
    return jsonify({
        "username": username,
        "role": user.get('role', 'viewer'),
        "permissions": ROLE_PERMISSIONS.get(user.get('role'), [])
    })

@app.get('/health')
def health():
    """Health check endpoint (no auth required)."""
    return jsonify({"status": "healthy", "service": "vigil-dashboard"})


@app.get('/api/status')
def api_status():
    """Status endpoint for UI sanity checks."""
    return jsonify({
        "status": "ok",
        "gateway_url": os.getenv("VIGIL_GATEWAY_URL"),
        "append_log_path": APPEND_LOG_PATH,
        "time": time.time(),
        "backend": "postgres" if log_store._use_db else "file"
    }), 200


@app.get('/api/events')
def api_events():
    """Return recent audit events using MerkleLogStore."""
    limit = int(request.args.get("limit", "200"))
    
    # Use the unified store to get logs (File or DB)
    events = log_store.get_logs(limit=limit)
    
    # Transform for frontend if needed (current structure seems compatible)
    # The frontend expects { "events": [...] }
    # Each event in logs is { "ts", "hash", "prev_hash", "entry": {...} }
    # We might need to flatten it or ensure frontend handles it.
    # Looking at legacy code:
    # It read the line, parsed it (obj), and appended. 
    # obj was: { "entry": {...}, "prev_hash": ..., "hash": ..., "ts": ... }
    # So the structure returned by get_logs seems to match the file structure.
    
    return jsonify({"events": events, "count": len(events)}), 200


# Ingest endpoint for the Gateway to ship logs to
@app.route('/api/v1/audit/ingest', methods=['POST'])
def ingest_log():
    """Receive logs from Gateway (if not sharing volume/DB)."""
    # Note: In the new architecture, if both share the DB, this might be redundant,
    # but useful if they are decoupled or if Gateway just pushes here.
    # However, Gateway calls 'ship_log_async' which does:
    # 1. append_store.append(payload) (Local DB/File)
    # 2. requests.post(LOG_SERVER_URL, ...)
    # If both use the SAME DB URL, we might get duplicates if we write here too.
    # But usually Gateway and Dashboard might be separate services.
    # For now, let's just log it or no-op if using DB.
    
    payload = request.json or {}
    
    # If we are using a shared DB, the Gateway likely already wrote it.
    # But Gateway uses its own MerkleLogStore instance.
    # If they point to the same DB, the Gateway's append() wrote it.
    # So we don't need to write it again here.
    # But if Gateway failed to write to DB and fell back to file, it might try to ship here?
    # The Gateway code does BOTH: append() AND post().
    
    # To be safe and avoid duplicates in DB mode:
    # If we are in DB mode, we assume Gateway is also in DB mode and wrote it.
    # If we are in File mode, we append it.
    
    if not log_store._use_db:
        # We are file based, so we accept the push
        # But wait, payload is just the 'entry'. append() wraps it.
        # Gateway sends the raw payload (entry).
        log_store.append(payload)
    
    return jsonify({"status": "received"}), 200


if __name__ == '__main__':
    print("🔭 Vigil Dashboard running on http://0.0.0.0:3000")
    print(f"\nAdmin Token: {ADMIN_TOKEN or '(not set)'}")
    print("\nDemo Accounts:")
    print("  Admin:   admin / admin123")
    print("  Auditor: auditor / auditor123")
    app.run(host='0.0.0.0', port=3000, debug=False)
