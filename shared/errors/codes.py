"""
Standard Error Codes - SaaS Edition
Consistent error handling across all services
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standard error codes for the entire platform"""
    
    # Authentication & Authorization (1000-1999)
    UNAUTHORIZED = "E1001"
    INVALID_TOKEN = "E1002"
    TOKEN_EXPIRED = "E1003"
    INSUFFICIENT_PERMISSIONS = "E1004"
    
    # Tenant & Quota (2000-2999)
    TENANT_NOT_FOUND = "E2001"
    QUOTA_EXCEEDED = "E2002"
    RATE_LIMIT_EXCEEDED = "E2003"
    BUDGET_EXCEEDED = "E2004"
    TENANT_SUSPENDED = "E2005"
    
    # Encryption & Security (3000-3999)
    ENCRYPTION_FAILED = "E3001"
    DECRYPTION_FAILED = "E3002"
    SIGNATURE_INVALID = "E3003"
    SIGNATURE_EXPIRED = "E3004"
    HPKE_KEY_MISMATCH = "E3005"
    
    # Threat Detection (4000-4999)
    PROMPT_INJECTION_DETECTED = "E4001"
    SQL_INJECTION_DETECTED = "E4002"
    XSS_DETECTED = "E4003"
    PII_LEAK_PREVENTED = "E4004"
    JAILBREAK_ATTEMPT = "E4005"
    HIGH_RISK_SCORE = "E4006"
    
    # Infrastructure (5000-5999)
    ENCLAVE_UNAVAILABLE = "E5001"
    VSOCK_CONNECTION_FAILED = "E5002"
    INTERNAL_ERROR = "E5003"
    SERVICE_DEGRADED = "E5004"
    
    # Validation (6000-6999)
    INVALID_PAYLOAD = "E6001"
    SCHEMA_VALIDATION_FAILED = "E6002"
    MISSING_REQUIRED_FIELD = "E6003"


class VigilError(Exception):
    """
    Base exception for all Vigil errors
    Always includes an error code and tenant context
    """
    
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        tenant_id: Optional[str] = None,
        details: Optional[dict] = None
    ):
        self.code = code
        self.message = message
        self.tenant_id = tenant_id
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "tenant_id": self.tenant_id,
                "details": self.details
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response format"""
    code: str
    message: str
    tenant_id: Optional[str] = None
    details: Optional[dict] = None
    timestamp: float


# Specific Error Classes for Common Cases

class QuotaExceededError(VigilError):
    """Tenant has exceeded their quota"""
    def __init__(self, tenant_id: str, quota_type: str = "requests"):
        super().__init__(
            code=ErrorCode.QUOTA_EXCEEDED,
            message=f"Tenant quota exceeded: {quota_type}",
            tenant_id=tenant_id,
            details={"quota_type": quota_type}
        )


class RateLimitError(VigilError):
    """Tenant hit rate limit"""
    def __init__(self, tenant_id: str, retry_after: int = 60):
        super().__init__(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            message=f"Rate limit exceeded. Retry after {retry_after}s",
            tenant_id=tenant_id,
            details={"retry_after": retry_after}
        )


class ThreatDetectedError(VigilError):
    """Malicious prompt blocked"""
    def __init__(self, tenant_id: str, threat_type: str, risk_score: float):
        super().__init__(
            code=ErrorCode.HIGH_RISK_SCORE,
            message=f"Threat detected: {threat_type}",
            tenant_id=tenant_id,
            details={"threat_type": threat_type, "risk_score": risk_score}
        )


class UnauthorizedError(VigilError):
    """Invalid or missing authentication"""
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            code=ErrorCode.UNAUTHORIZED,
            message=message
        )
