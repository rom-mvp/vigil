"""
Shared Errors Module
"""

from .codes import (
    ErrorCode,
    VigilError,
    ErrorResponse,
    QuotaExceededError,
    RateLimitError,
    ThreatDetectedError,
    UnauthorizedError,
)

__all__ = [
    "ErrorCode",
    "VigilError",
    "ErrorResponse",
    "QuotaExceededError",
    "RateLimitError",
    "ThreatDetectedError",
    "UnauthorizedError",
]
