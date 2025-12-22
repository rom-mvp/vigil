"""
Governance Schemas - Multi-Tenant Policy Management
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional
from datetime import datetime


class TenantPolicy(BaseModel):
    """
    Per-tenant quota and rate limiting policy
    Prevents noisy neighbors and budget overruns
    """
    tenant_id: str = Field(..., description="Unique tenant identifier")
    
    # Budget Controls
    monthly_budget_usd: float = Field(default=100.0, description="Max spend per month")
    current_spend_usd: float = Field(default=0.0, description="Current month spend")
    
    # Rate Limiting
    requests_per_minute: int = Field(default=60, description="Per-tenant rate limit")
    tokens_per_day: int = Field(default=1_000_000, description="Daily token cap")
    
    # Feature Flags
    enable_pii_redaction: bool = Field(default=True, description="Auto-redact PII")
    enable_invisible_wallet: bool = Field(default=True, description="Use enclave credentials")
    strict_mode: bool = Field(default=False, description="Fail-closed on errors")
    
    # Metadata
    tier: str = Field(default="free", description="free|pro|enterprise")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "tenant_prod_xyz",
                "monthly_budget_usd": 500.0,
                "current_spend_usd": 127.45,
                "requests_per_minute": 120,
                "tokens_per_day": 5_000_000,
                "enable_pii_redaction": True,
                "enable_invisible_wallet": True,
                "strict_mode": True,
                "tier": "pro"
            }
        }


class UsageMetrics(BaseModel):
    """
    Real-time usage tracking for billing and metering
    """
    tenant_id: str
    agent_id: str
    model: str
    
    # Counters
    tokens_consumed: int = Field(default=0, description="Prompt + completion tokens")
    requests_count: int = Field(default=0, description="Total requests")
    cost_usd: float = Field(default=0.0, description="Accumulated cost")
    
    # Timing
    avg_latency_ms: float = Field(default=0.0, description="Rolling average latency")
    
    # Security
    blocked_requests: int = Field(default=0, description="Threats blocked")
    
    # Time Window
    window_start: datetime = Field(default_factory=datetime.utcnow)
    window_end: Optional[datetime] = None


class AgentQuota(BaseModel):
    """
    Per-agent quotas within a tenant
    Useful for multi-user SaaS apps
    """
    agent_id: str
    tenant_id: str
    
    # Quotas
    max_tokens_per_request: int = Field(default=4096)
    max_requests_per_hour: int = Field(default=100)
    
    # Current Usage
    tokens_used_today: int = Field(default=0)
    requests_this_hour: int = Field(default=0)
