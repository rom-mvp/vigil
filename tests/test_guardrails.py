from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from vigil.guardrails import (
    RbacViolation,
    TenantIsolationError,
    UsageEvent,
    detect_rate_limit_violations,
    enforce_rbac,
    enforce_tenant_isolation,
    estimate_quota_remaining,
    rollup_billing,
    QuotaExceeded,
)


def make_event(
    tenant: str,
    agent: str,
    model: str,
    *,
    seconds: int,
    tokens: int = 100,
    cost: float = 0.25,
) -> UsageEvent:
    base = datetime(2025, 1, 1)
    return UsageEvent(
        tenant_id=tenant,
        agent_id=agent,
        model=model,
        tokens=tokens,
        cost=cost,
        timestamp=base + timedelta(seconds=seconds),
    )


def test_rate_limit_violation_detects_bursts():
    events = [
        make_event("tenant-a", "agent-1", "gpt-4o-mini", seconds=i) for i in range(6)
    ] + [
        make_event("tenant-b", "agent-9", "gpt-4o-mini", seconds=i * 30) for i in range(4)
    ]

    violations = detect_rate_limit_violations(events, per_minute_limit=5)

    assert violations == {"tenant-a": 6}


def test_rate_limit_allows_even_distribution():
    events = [
        make_event("tenant-a", "agent-1", "gpt-4o-mini", seconds=i * 15) for i in range(6)
    ]

    violations = detect_rate_limit_violations(events, per_minute_limit=5)

    assert violations == {}


def test_quota_enforcement_returns_remaining_and_blocks_overages():
    quota = {"requests": 1000, "tokens": 500_000}
    usage = {"requests": 750, "tokens": 400_000}

    remaining = estimate_quota_remaining(quota, usage)

    assert remaining == {"requests": 250, "tokens": 100_000}

    with pytest.raises(QuotaExceeded):
        estimate_quota_remaining(quota, {"requests": 1001})


def test_billing_rollup_groups_models_and_agents():
    events = [
        make_event("tenant-a", "agent-1", "gpt-4o", seconds=1, cost=0.9),
        make_event("tenant-a", "agent-1", "gpt-4o", seconds=2, cost=0.9),
        make_event("tenant-a", "agent-2", "gpt-4o-mini", seconds=3, cost=0.4),
    ]

    summary = rollup_billing(events)

    assert summary["totals"]["requests"] == 3
    assert summary["totals"]["cost"] == pytest.approx(2.2)
    assert summary["by_model"]["gpt-4o"]["requests"] == 2
    assert summary["by_agent"]["agent-2"]["cost"] == pytest.approx(0.4)


def test_rbac_violation_for_billing_access():
    enforce_rbac("VIEWER", "view_billing")  # should not raise

    with pytest.raises(RbacViolation):
        enforce_rbac("DEVELOPER", "view_billing")


def test_tenant_switching_isolation_detects_leakage():
    events = [
        make_event("tenant-a", "agent-1", "gpt-4o", seconds=1),
        make_event("tenant-b", "agent-9", "gpt-4o", seconds=2),
    ]

    with pytest.raises(TenantIsolationError):
        enforce_tenant_isolation(events, active_tenant="tenant-a")


def test_tenant_switching_isolation_returns_clean_data():
    events = [
        make_event("tenant-a", "agent-1", "gpt-4o", seconds=1),
        make_event("tenant-a", "agent-2", "gpt-4o-mini", seconds=2),
    ]

    isolated = enforce_tenant_isolation(events, active_tenant="tenant-a")

    assert len(isolated) == 2
    assert all(evt.tenant_id == "tenant-a" for evt in isolated)
