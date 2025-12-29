"""
API Key Authentication Module for SaaS
Validates Bearer tokens (vk_...) against Redis and resolves tenant_id
"""

import os
import redis
import logging
import hashlib
import time
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class InvalidAPIKey(Exception):
    """Raised when an API key does not meet required format."""



class APIKeyAuth:
    """
    Validates API keys and resolves tenant identity.
    
    SaaS Flow:
    1. Client sends: Authorization: Bearer vk_abc123...
    2. Vigil validates against Redis: api_keys:vk_abc123 -> tenant_id
    3. If valid, returns (tenant_id, tenant_metadata)
    4. If invalid, returns (None, None) -> 401 Unauthorized
    """
    
    def __init__(self, redis_url: str = None):
        """
        Initialize API Key authentication with Redis backend.
        
        Args:
            redis_url: Redis connection URL (default: from REDIS_URL env)
        """
        self.redis_url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_client = None
        self._connect()
        
    def _connect(self):
        """Connect to Redis for API key lookup."""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=1.0
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"APIKeyAuth connected to Redis: {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def validate_key(self, api_key: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Validate API key and resolve tenant identity.
        
        Args:
            api_key: API key from Authorization header (e.g., "vk_abc123...")
            
        Returns:
            (tenant_id, metadata) if valid, (None, None) if invalid
            
        Redis Schema:
            api_keys:{api_key} -> Hash with:
                - tenant_id: string
                - tenant_name: string
                - tier: string (free|pro|enterprise)
                - created_at: timestamp
                - status: string (active|suspended)
        """
        if not api_key or not api_key.startswith('vk_'):
            raise InvalidAPIKey("Invalid API key format")
        
        if not self.redis_client:
            logger.error("Redis not available for API key validation")
            # Fail open in development (allow without validation)
            if os.environ.get('VIGIL_ENVIRONMENT', 'production') == 'development':
                logger.warning("Development mode: bypassing API key validation")
                return 'dev-tenant', {'tenant_name': 'Development', 'tier': 'enterprise'}
            return None, None
        
        try:
            # Lookup API key in Redis
            key_data = self.redis_client.hgetall(f"api_keys:{api_key}")
            
            if not key_data:
                logger.warning(f"API key not found: {api_key[:20]}...")
                return None, None
            
            # Check if key is active
            status = key_data.get('status', 'active')
            if status != 'active':
                logger.warning(f"API key suspended: {api_key[:20]}... (status: {status})")
                return None, None
            
            tenant_id = key_data.get('tenant_id')
            if not tenant_id:
                logger.error(f"API key missing tenant_id: {api_key[:20]}...")
                return None, None
            
            # Return tenant info
            metadata = {
                'tenant_name': key_data.get('tenant_name', 'Unknown'),
                'tier': key_data.get('tier', 'free'),
                'created_at': key_data.get('created_at'),
                'api_key_id': hashlib.sha256(api_key.encode()).hexdigest()[:16]
            }
            
            logger.info(f"API key validated: tenant={tenant_id} tier={metadata['tier']}")
            return tenant_id, metadata
            
        except redis.RedisError as e:
            logger.error(f"Redis error during API key validation: {e}")
            # Fail open or closed based on config
            fail_mode = os.environ.get('VIGIL_FAIL_MODE', 'closed')
            if fail_mode == 'open':
                logger.warning("Redis down - failing OPEN (allowing request)")
                return 'fallback-tenant', {'tenant_name': 'Fallback', 'tier': 'free'}
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error in API key validation: {e}")
            return None, None
    
    def extract_api_key(self, authorization_header: str) -> Optional[str]:
        """
        Extract API key from Authorization header.
        
        Args:
            authorization_header: Full Authorization header value
            
        Returns:
            API key string or None
            
        Examples:
            "Bearer vk_abc123..." -> "vk_abc123..."
            "vk_abc123..." -> "vk_abc123..."
        """
        if not authorization_header:
            return None
        
        # Handle "Bearer vk_..." format
        if authorization_header.startswith('Bearer '):
            return authorization_header[7:].strip()
        
        # Handle raw "vk_..." format
        if authorization_header.startswith('vk_'):
            return authorization_header.strip()
        
        return None
    
    def get_tenant_rate_limit(self, tenant_id: str, tier: str) -> int:
        """
        Get rate limit for tenant based on tier.
        
        Args:
            tenant_id: Tenant identifier
            tier: Subscription tier (free|pro|enterprise)
            
        Returns:
            Requests per minute allowed
        """
        # Default rate limits by tier
        rate_limits = {
            'free': 10,
            'pro': 100,
            'enterprise': 1000,
            'unlimited': 10000
        }
        
        # Check for custom tenant limit in Redis
        if self.redis_client:
            try:
                custom_limit = self.redis_client.hget(f"tenant:{tenant_id}", "rate_limit_rpm")
                if custom_limit:
                    return int(custom_limit)
            except Exception as e:
                logger.warning(f"Failed to get custom rate limit for {tenant_id}: {e}")
        
        return rate_limits.get(tier, 10)
    
    def check_rate_limit(self, tenant_id: str, limit_rpm: int) -> Tuple[bool, Dict]:
        """
        Check if tenant is within rate limit.
        
        Args:
            tenant_id: Tenant identifier
            limit_rpm: Requests per minute limit
            
        Returns:
            (allowed, info) where info contains remaining/reset details
        """
        if not self.redis_client:
            # Without Redis, allow by default
            return True, {'remaining': limit_rpm, 'reset': 60}
        
        try:
            # Use sliding window rate limiter
            now = int(time.time())
            window_start = now - 60  # 1 minute window
            
            key = f"rate_limit:{tenant_id}:rpm"
            
            # Add current request timestamp
            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
            pipe.zadd(key, {str(now): now})  # Add current request
            pipe.zcard(key)  # Count requests in window
            pipe.expire(key, 120)  # Expire after 2 minutes
            results = pipe.execute()
            
            request_count = results[2]
            
            allowed = request_count <= limit_rpm
            remaining = max(0, limit_rpm - request_count)
            
            info = {
                'limit': limit_rpm,
                'remaining': remaining,
                'reset': 60 - (now % 60),  # Seconds until next minute
                'current_count': request_count
            }
            
            if not allowed:
                logger.warning(f"Rate limit exceeded for {tenant_id}: {request_count}/{limit_rpm}")
            
            return allowed, info
            
        except Exception as e:
            logger.error(f"Rate limit check failed for {tenant_id}: {e}")
            # Fail open on error
            return True, {'remaining': limit_rpm, 'reset': 60}
    
    def create_api_key(self, tenant_id: str, tenant_name: str, tier: str = 'free') -> str:
        """
        Create a new API key for a tenant (admin function).
        
        Args:
            tenant_id: Tenant identifier
            tenant_name: Human-readable tenant name
            tier: Subscription tier
            
        Returns:
            Generated API key (vk_...)
        """
        if not self.redis_client:
            raise RuntimeError("Redis not available")
        
        # Generate API key
        import secrets
        api_key = f"vk_{secrets.token_urlsafe(32)}"
        
        # Store in Redis
        key_data = {
            'tenant_id': tenant_id,
            'tenant_name': tenant_name,
            'tier': tier,
            'created_at': str(int(time.time())),
            'status': 'active'
        }
        
        self.redis_client.hset(f"api_keys:{api_key}", mapping=key_data)
        
        # Also add to tenant's key list
        self.redis_client.sadd(f"tenant:{tenant_id}:keys", api_key)
        
        logger.info(f"Created API key for tenant {tenant_id}: {api_key[:20]}...")
        return api_key
