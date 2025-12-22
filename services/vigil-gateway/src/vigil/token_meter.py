"""
Token Metering and Billing Module
Counts tokens for requests/responses and pushes to billing queue
"""

import os
import json
import logging
import time
import redis
from typing import Dict, Optional, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class TokenMeter:
    """
    Tracks token usage for billing and quota enforcement.
    
    SaaS Flow:
    1. Before LLM: Estimate input tokens
    2. After LLM: Count actual input + output tokens
    3. Push usage event to billing queue (async)
    4. Update tenant quota counters
    """
    
    def __init__(self, redis_url: str = None):
        """
        Initialize token metering with Redis queue backend.
        
        Args:
            redis_url: Redis connection URL (default: from REDIS_URL env)
        """
        self.redis_url = redis_url or os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        self.redis_client = None
        self._connect()
        
        # Queue names
        self.billing_queue = "billing:events"
        self.usage_key_prefix = "usage"
        
    def _connect(self):
        """Connect to Redis for billing queue."""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=1.0
            )
            self.redis_client.ping()
            logger.info(f"TokenMeter connected to Redis: {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
    
    def estimate_tokens(self, text: str, model: str = "gpt-4") -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Input text
            model: Model name (affects tokenization)
            
        Returns:
            Estimated token count
            
        Note: This is a rough estimate. Use actual token counts from LLM response when available.
        """
        # Rough estimation: ~4 chars per token for English
        # More accurate: use tiktoken library
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except (ImportError, KeyError):
            # Fallback: rough estimate
            return len(text) // 4
    
    def count_message_tokens(self, messages: List[Dict], model: str = "gpt-4") -> int:
        """
        Count tokens in a list of chat messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name
            
        Returns:
            Total token count
        """
        total = 0
        for msg in messages:
            # Count role overhead (varies by model)
            total += 4  # Approximate overhead per message
            
            # Count content
            content = msg.get('content', '')
            if isinstance(content, str):
                total += self.estimate_tokens(content, model)
            elif isinstance(content, list):
                # Handle multi-modal content
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'text':
                        total += self.estimate_tokens(item.get('text', ''), model)
        
        return total
    
    def record_usage(
        self,
        tenant_id: str,
        request_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Record token usage for billing.
        
        Args:
            tenant_id: Tenant identifier
            request_id: Unique request ID
            model: Model used (gpt-4, gpt-3.5-turbo, etc.)
            input_tokens: Input token count
            output_tokens: Output token count
            metadata: Additional metadata (agent_id, policy_id, etc.)
            
        Returns:
            True if recorded successfully
        """
        if not self.redis_client:
            logger.warning(f"Redis unavailable - usage not recorded: {tenant_id}/{request_id}")
            return False
        
        try:
            # Build usage event
            event = {
                'tenant_id': tenant_id,
                'request_id': request_id,
                'model': model,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens,
                'timestamp': int(time.time()),
                'metadata': metadata or {}
            }
            
            # Push to billing queue (for async processing)
            self.redis_client.rpush(self.billing_queue, json.dumps(event))
            
            # Update real-time usage counters (for quota checks)
            self._update_usage_counters(tenant_id, input_tokens, output_tokens)
            
            logger.info(f"Recorded usage: {tenant_id} - {input_tokens}+{output_tokens} tokens ({model})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to record usage: {e}")
            return False
    
    def _update_usage_counters(self, tenant_id: str, input_tokens: int, output_tokens: int):
        """
        Update real-time usage counters for quota enforcement.
        
        Counters:
            - usage:{tenant_id}:daily - Daily token count
            - usage:{tenant_id}:monthly - Monthly token count
        """
        if not self.redis_client:
            return
        
        try:
            now = int(time.time())
            today = time.strftime('%Y-%m-%d', time.gmtime(now))
            month = time.strftime('%Y-%m', time.gmtime(now))
            
            total_tokens = input_tokens + output_tokens
            
            pipe = self.redis_client.pipeline()
            
            # Daily counter
            daily_key = f"{self.usage_key_prefix}:{tenant_id}:daily:{today}"
            pipe.incrby(daily_key, total_tokens)
            pipe.expire(daily_key, 86400 * 2)  # Keep for 2 days
            
            # Monthly counter
            monthly_key = f"{self.usage_key_prefix}:{tenant_id}:monthly:{month}"
            pipe.incrby(monthly_key, total_tokens)
            pipe.expire(monthly_key, 86400 * 60)  # Keep for 60 days
            
            # All-time counter
            alltime_key = f"{self.usage_key_prefix}:{tenant_id}:total"
            pipe.incrby(alltime_key, total_tokens)
            
            pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to update usage counters: {e}")
    
    def get_usage(self, tenant_id: str, period: str = 'daily') -> Dict:
        """
        Get usage statistics for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            period: 'daily', 'monthly', or 'total'
            
        Returns:
            Usage statistics dict
        """
        if not self.redis_client:
            return {'tokens': 0, 'error': 'Redis unavailable'}
        
        try:
            now = int(time.time())
            
            if period == 'daily':
                today = time.strftime('%Y-%m-%d', time.gmtime(now))
                key = f"{self.usage_key_prefix}:{tenant_id}:daily:{today}"
            elif period == 'monthly':
                month = time.strftime('%Y-%m', time.gmtime(now))
                key = f"{self.usage_key_prefix}:{tenant_id}:monthly:{month}"
            else:  # total
                key = f"{self.usage_key_prefix}:{tenant_id}:total"
            
            tokens = self.redis_client.get(key)
            return {
                'tenant_id': tenant_id,
                'period': period,
                'tokens': int(tokens) if tokens else 0,
                'timestamp': now
            }
            
        except Exception as e:
            logger.error(f"Failed to get usage: {e}")
            return {'tokens': 0, 'error': str(e)}
    
    def check_quota(self, tenant_id: str, tier: str, requested_tokens: int = 0) -> Dict:
        """
        Check if tenant is within quota limits.
        
        Args:
            tenant_id: Tenant identifier
            tier: Subscription tier (free|pro|enterprise)
            requested_tokens: Tokens about to be used
            
        Returns:
            Dict with quota status
        """
        # Define quota limits by tier
        quotas = {
            'free': {
                'daily': 10000,
                'monthly': 100000
            },
            'pro': {
                'daily': 100000,
                'monthly': 2000000
            },
            'enterprise': {
                'daily': -1,  # Unlimited
                'monthly': -1
            }
        }
        
        tier_limits = quotas.get(tier, quotas['free'])
        
        # Get current usage
        daily_usage = self.get_usage(tenant_id, 'daily')
        monthly_usage = self.get_usage(tenant_id, 'monthly')
        
        daily_tokens = daily_usage.get('tokens', 0)
        monthly_tokens = monthly_usage.get('tokens', 0)
        
        # Check limits
        daily_limit = tier_limits['daily']
        monthly_limit = tier_limits['monthly']
        
        daily_exceeded = daily_limit > 0 and (daily_tokens + requested_tokens) > daily_limit
        monthly_exceeded = monthly_limit > 0 and (monthly_tokens + requested_tokens) > monthly_limit
        
        within_quota = not (daily_exceeded or monthly_exceeded)
        
        return {
            'within_quota': within_quota,
            'daily': {
                'used': daily_tokens,
                'limit': daily_limit,
                'remaining': max(0, daily_limit - daily_tokens) if daily_limit > 0 else -1
            },
            'monthly': {
                'used': monthly_tokens,
                'limit': monthly_limit,
                'remaining': max(0, monthly_limit - monthly_tokens) if monthly_limit > 0 else -1
            }
        }
    
    def process_billing_queue(self, batch_size: int = 100) -> int:
        """
        Process billing events from queue (for background worker).
        
        Args:
            batch_size: Number of events to process
            
        Returns:
            Number of events processed
        """
        if not self.redis_client:
            return 0
        
        try:
            processed = 0
            
            for _ in range(batch_size):
                # Pop event from queue
                event_json = self.redis_client.lpop(self.billing_queue)
                if not event_json:
                    break
                
                event = json.loads(event_json)
                
                # Process event (send to billing system, write to DB, etc.)
                self._process_billing_event(event)
                
                processed += 1
            
            if processed > 0:
                logger.info(f"Processed {processed} billing events")
            
            return processed
            
        except Exception as e:
            logger.error(f"Failed to process billing queue: {e}")
            return 0
    
    def _process_billing_event(self, event: Dict):
        """
        Process a single billing event.
        
        This is a placeholder - implement actual billing logic here:
        - Write to database
        - Send to billing service (Stripe, etc.)
        - Generate invoices
        - Update tenant balances
        """
        # Placeholder: Just log the event
        logger.debug(f"Billing event: {event['tenant_id']} used {event['total_tokens']} tokens")
        
        # In production, you would:
        # 1. Calculate cost based on model pricing
        # 2. Update tenant balance in database
        # 3. Trigger alerts if approaching limits
        # 4. Generate line items for invoices
