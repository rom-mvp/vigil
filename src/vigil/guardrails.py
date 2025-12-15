"""Guardrail helpers for multi-tenant billing, RBAC, and quota safety."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List


class RateLimitViolation(Exception):
    """Raised when a tenant exceeds the configured rate limit."""


class QuotaExceeded(Exception):
    """Raised when a tenant exhausts or exceeds an assigned quota."""


class RbacViolation(Exception):
    """Raised when a role attempts an action it is not entitled to perform."""


class TenantIsolationError(Exception):
    """Raised when cross-tenant data is detected during an isolation boundary check."""


@dataclass(frozen=True)
class UsageEvent:
    """Represents a billed agent request."""

    tenant_id: str
    agent_id: str
    model: str
    tokens: int
    cost: float
    timestamp: datetime


ROLE_CAPABILITIES: Dict[str, set[str]] = {
    "TENANT_ADMIN": {
        "view_analytics",
        "manage_policies",
        "manage_agents",
        "view_billing",
    },
    "DEVELOPER": {"view_analytics", "manage_policies"},
    "VIEWER": {"view_analytics", "view_billing"},
}


def detect_rate_limit_violations(
    events: Iterable[UsageEvent],
    per_minute_limit: int,
) -> Dict[str, int]:
    """Return tenants that burst past the configured per-minute rate limit.

    Sliding windows prevent false positives when events span multiple minutes.
    """

    if per_minute_limit < 1:
        raise ValueError("per_minute_limit must be positive")

    violations: Dict[str, int] = {}
    windows: Dict[str, deque[datetime]] = defaultdict(deque)

    for event in sorted(events, key=lambda e: e.timestamp):
        window = windows[event.tenant_id]
        window.append(event.timestamp)

        cutoff = event.timestamp - timedelta(minutes=1)
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) > per_minute_limit:
            violations[event.tenant_id] = len(window)

    return violations


def estimate_quota_remaining(
    quota_limits: Dict[str, int],
    usage: Dict[str, int],
) -> Dict[str, int]:
    """Return remaining quota per dimension, raising if a limit is exceeded."""

    remaining: Dict[str, int] = {}
    for resource, limit in quota_limits.items():
        consumed = usage.get(resource, 0)
        remaining_capacity = limit - consumed
        if remaining_capacity < 0:
            raise QuotaExceeded(f"{resource} quota exceeded by {-remaining_capacity}")
        remaining[resource] = remaining_capacity
    return remaining


def rollup_billing(events: Iterable[UsageEvent]) -> Dict[str, Dict[str, float]]:
    """Summarize billed usage per model and per agent."""

    by_model: Dict[str, Dict[str, float]] = defaultdict(lambda: {"requests": 0, "cost": 0.0})
    by_agent: Dict[str, Dict[str, float]] = defaultdict(lambda: {"requests": 0, "cost": 0.0})
    totals = {"requests": 0, "tokens": 0, "cost": 0.0}

    for event in events:
        by_model[event.model]["requests"] += 1
        by_model[event.model]["cost"] += event.cost

        by_agent[event.agent_id]["requests"] += 1
        by_agent[event.agent_id]["cost"] += event.cost

        totals["requests"] += 1
        totals["tokens"] += event.tokens
        totals["cost"] += event.cost

    return {
        "totals": totals,
        "by_model": dict(by_model),
        "by_agent": dict(by_agent),
    }


def enforce_rbac(role: str, capability: str) -> None:
    """Raise if the supplied role cannot execute the requested capability."""

    allowed = ROLE_CAPABILITIES.get(role)
    if allowed is None:
        raise RbacViolation(f"Unknown role: {role}")
    if capability not in allowed:
        raise RbacViolation(f"{role} may not perform {capability}")


def enforce_tenant_isolation(
    events: Iterable[UsageEvent],
    active_tenant: str,
) -> List[UsageEvent]:
    """Ensure the active tenant only receives its own records."""

    isolated: List[UsageEvent] = []
    leaked: List[UsageEvent] = []

    for event in events:
        if event.tenant_id == active_tenant:
            isolated.append(event)
        else:
            leaked.append(event)

    if leaked:
        raise TenantIsolationError(
            f"Detected {len(leaked)} records belonging to other tenants: "
            f"{sorted({evt.tenant_id for evt in leaked})}"
        )

    return isolated


__all__ = [
    "UsageEvent",
    "detect_rate_limit_violations",
    "estimate_quota_remaining",
    "rollup_billing",
    "enforce_rbac",
    "enforce_tenant_isolation",
    "RateLimitViolation",
    "QuotaExceeded",
    "RbacViolation",
    "TenantIsolationError",
]
