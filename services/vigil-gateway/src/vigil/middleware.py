"""
JWT Authentication Middleware for SaaS
Validates Auth0/Clerk/Cognito tokens and extracts tenant_id
"""

import os
import jwt
from functools import wraps
from flask import request, jsonify
from typing import Tuple, Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from shared.errors import UnauthorizedError, ErrorCode


class JWTAuth:
    """
    JWT Token Validator for SaaS multi-tenancy
    """
    
    def __init__(self):
        # In production, fetch JWKS from your auth provider
        self.jwks_url = os.getenv("AUTH_JWKS_URL", "https://auth.vigil.ai/.well-known/jwks.json")
        self.issuer = os.getenv("AUTH_ISSUER", "https://auth.vigil.ai")
        self.audience = os.getenv("AUTH_AUDIENCE", "vigil-api")
        
        # For local dev, allow test tokens
        self.dev_mode = os.getenv("VIGIL_ENV", "local") == "local"
    
    def extract_token(self, auth_header: Optional[str]) -> str:
        """
        Extract JWT from Authorization header
        """
        if not auth_header:
            raise UnauthorizedError("Missing Authorization header")
        
        if not auth_header.startswith("Bearer "):
            raise UnauthorizedError("Invalid Authorization format (expected 'Bearer <token>')")
        
        return auth_header.replace("Bearer ", "")
    
    def validate_saas_token(self, auth_header: str) -> Tuple[str, str]:
        """
        Decode and validate JWT token
        
        Returns:
            (tenant_id, user_id) - Extracted from token claims
        
        Raises:
            UnauthorizedError: If token is invalid
        """
        token = self.extract_token(auth_header)
        
        # Dev mode: allow test tokens
        if self.dev_mode and token == "test-key":
            return "tenant_local_dev", "user_dev_001"
        
        try:
            # In production, verify signature against JWKS
            # For now, decode without verification (UNSAFE - for demo only)
            payload = jwt.decode(
                token,
                options={"verify_signature": False},  # TODO: Enable in production
                algorithms=["RS256"]
            )
            
            # Extract tenant ID (Auth0: org_id, Clerk: org_id, Cognito: custom:tenant_id)
            tenant_id = (
                payload.get("org_id") or
                payload.get("custom:tenant_id") or
                payload.get("tenant_id") or
                "tenant_unknown"
            )
            
            # Extract user ID
            user_id = payload.get("sub", "user_unknown")
            
            return tenant_id, user_id
        
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token expired")
        except jwt.PyJWTError as e:
            raise UnauthorizedError(f"Invalid token: {str(e)}")
    
    def require_auth(self, f):
        """
        Flask decorator to enforce JWT authentication
        
        Usage:
            @app.route("/protected")
            @jwt_auth.require_auth
            def protected_endpoint():
                tenant_id = request.tenant_id
                user_id = request.user_id
                ...
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get("Authorization")
            
            try:
                tenant_id, user_id = self.validate_saas_token(auth_header)
                
                # Attach to request context for downstream use
                request.tenant_id = tenant_id
                request.user_id = user_id
                
                return f(*args, **kwargs)
            
            except UnauthorizedError as e:
                return jsonify(e.to_dict()), 401
        
        return decorated_function


# Singleton instance
jwt_auth = JWTAuth()
