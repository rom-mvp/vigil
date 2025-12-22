"""
Multi-Tenant Governance Engine
Handles budget enforcement and rate limiting per SaaS customer
"""

import time
from typing import Dict, Optional
from collections import defaultdict

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from shared.schemas.governance import TenantPolicy, UsageMetrics
from shared.errors import QuotaExceededError, RateLimitError


class TenantGovernance:
    """
    SaaS Multi-Tenant Governance
    Prevents noisy neighbors and ensures budget isolation
    """
    
    def __init__(self):
        # Structure: { "tenant_id": TenantPolicy }
        self.policy_cache: Dict[str, TenantPolicy] = {}
        
        # Usage tracking: { "tenant_id": UsageMetrics }
        self.usage_metrics: Dict[str, UsageMetrics] = {}
        
        # Rate limiting windows: { "tenant_id": [timestamps] }
        self.rate_limit_windows: Dict[str, list] = defaultdict(list)
        
        print("🛡️  TenantGovernance initialized (SaaS Edition)")
    
    def load_policy(self, tenant_id: str) -> TenantPolicy:
        """
        Load tenant policy from cache or database
        In production, this syncs with Redis/PostgreSQL
        """
        if tenant_id not in self.policy_cache:
            # Default policy for new tenants
            self.policy_cache[tenant_id] = TenantPolicy(
                tenant_id=tenant_id,
                monthly_budget_usd=100.0,
                current_spend_usd=0.0,
                requests_per_minute=60,
                tokens_per_day=1_000_000,
                tier="free"
            )
        
        return self.policy_cache[tenant_id]
    
    def check_budget(self, tenant_id: str, estimated_cost: float) -> bool:
        """
        Check if tenant has budget remaining
        
        Raises:
            QuotaExceededError: If budget exceeded
        """
        policy = self.load_policy(tenant_id)
        
        if policy.current_spend_usd + estimated_cost > policy.monthly_budget_usd:
            raise QuotaExceededError(
                tenant_id=tenant_id,
                quota_type=f"budget (${policy.monthly_budget_usd:.2f}/month)"
            )
        
        return True
    
    def check_rate_limit(self, tenant_id: str) -> bool:
        """
        Check if tenant is within rate limit
        
        Raises:
            RateLimitError: If rate limit exceeded
        """
        policy = self.load_policy(tenant_id)
        now = time.time()
        
        # Clean up timestamps older than 60 seconds
        window = self.rate_limit_windows[tenant_id]
        self.rate_limit_windows[tenant_id] = [
            ts for ts in window if now - ts < 60
        ]
        
        # Check rate limit
        current_requests = len(self.rate_limit_windows[tenant_id])
        if current_requests >= policy.requests_per_minute:
            raise RateLimitError(
                tenant_id=tenant_id,
                retry_after=60
            )
        
        # Record this request
        self.rate_limit_windows[tenant_id].append(now)
        return True
    
    def record_usage(
        self,
        tenant_id: str,
        agent_id: str,
        model: str,
        tokens: int,
        cost: float,
        latency_ms: float
    ):
        """
        Record usage for billing and metering
        """
        # Update tenant spend
        policy = self.load_policy(tenant_id)
        policy.current_spend_usd += cost
        
        # Update usage metrics
        if tenant_id not in self.usage_metrics:
            self.usage_metrics[tenant_id] = UsageMetrics(
                tenant_id=tenant_id,
                agent_id=agent_id,
                model=model
            )
        
        metrics = self.usage_metrics[tenant_id]
        metrics.tokens_consumed += tokens
        metrics.requests_count += 1
        metrics.cost_usd += cost
        
        # Update rolling average latency
        n = metrics.requests_count
        metrics.avg_latency_ms = (
            (metrics.avg_latency_ms * (n - 1) + latency_ms) / n
        )
    
    def get_usage(self, tenant_id: str) -> Optional[UsageMetrics]:
        """
        Get current usage metrics for a tenant
        """
        return self.usage_metrics.get(tenant_id)
    
    def enforce_tenant_isolation(
        self,
        tenant_id: str,
        agent_id: str,
        estimated_cost: float = 0.001
    ) -> bool:
        """
        Full tenant isolation check
        
        1. Rate limiting
        2. Budget enforcement
        3. Return True if allowed, raise exception if blocked
        """
        # Check rate limit first (cheap operation)
        self.check_rate_limit(tenant_id)
        
        # Check budget (more expensive, query DB)
        self.check_budget(tenant_id, estimated_cost)
        
        return True


# Singleton instance
tenant_governance = TenantGovernance()
