"""
Protocol Schemas - The Wire Format
Defines the exact structure sent over VSOCK/HTTP between services
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime


class EnclaveRequest(BaseModel):
    """
    The request packet sent from Vigil Gateway → AgentShield Enclave
    This is the ENCRYPTED payload wrapper
    """
    request_id: str = Field(..., description="Distributed trace ID for logs")
    tenant_id: str = Field(..., description="SaaS Customer ID - CRITICAL for isolation")
    agent_id: str = Field(..., description="End-user agent identifier")
    payload_encrypted: str = Field(..., description="Base64 HPKE encrypted blob")
    timestamp: float = Field(..., description="Unix timestamp for replay protection")
    schema_version: str = Field(default="1.0", description="Protocol version")
    
    class Config:
        schema_extra = {
            "example": {
                "request_id": "req_abc123",
                "tenant_id": "tenant_prod_xyz",
                "agent_id": "agent_gpt4_001",
                "payload_encrypted": "aGVsbG8gd29ybGQ=...",
                "timestamp": 1703203200.0,
                "schema_version": "1.0"
            }
        }


class DecryptedPayload(BaseModel):
    """
    The DECRYPTED payload structure - only exists inside enclave memory
    This is what AgentShield analyzes
    """
    prompt: str = Field(..., description="User's raw input")
    model: str = Field(..., description="Target LLM model")
    wallet_id: Optional[str] = Field(default="default", description="Invisible Wallet key ID")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional context")
    messages: Optional[List[Dict[str, str]]] = Field(default=None, description="Chat history")


class EnclaveResponse(BaseModel):
    """
    The response sent from AgentShield Enclave → Vigil Gateway
    """
    request_id: str = Field(..., description="Echoed from request for correlation")
    decision: str = Field(..., description="ALLOW or BLOCK")
    risk_score: float = Field(..., description="Threat confidence 0.0-1.0")
    reasons: List[str] = Field(default_factory=list, description="Detection rule hits")
    latency_ms: float = Field(..., description="Processing time inside enclave")
    signature: str = Field(..., description="Ed25519 signature of decision")
    signature_key_id: str = Field(..., description="Key ID for signature verification")
    timestamp: float = Field(..., description="Decision timestamp")
    
    # Tenant echo for audit trail
    tenant_id: str = Field(..., description="Echoed tenant ID")
    cost_estimate: Optional[float] = Field(None, description="Estimated token cost")
    
    class Config:
        schema_extra = {
            "example": {
                "request_id": "req_abc123",
                "decision": "ALLOW",
                "risk_score": 0.12,
                "reasons": ["clean"],
                "latency_ms": 15.3,
                "signature": "ed25519_sig_...",
                "signature_key_id": "key_001",
                "timestamp": 1703203215.3,
                "tenant_id": "tenant_prod_xyz",
                "cost_estimate": 0.0015
            }
        }


class HealthCheck(BaseModel):
    """Service health status"""
    status: str = Field(..., description="ok or degraded")
    timestamp: float
    enclave_ready: bool
    signature_verified: bool
