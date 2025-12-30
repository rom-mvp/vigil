#!/usr/bin/env python3
"""Fail-closed behavior tests for Vigil SaaS mode."""

import types
import pytest

from src.vigil import local_server as ls


@pytest.fixture
def client(monkeypatch):
    # Force SaaS mode for the handler
    monkeypatch.setattr(ls, "VIGIL_MODE", "saas")
    monkeypatch.setattr(ls, "VIGIL_ENVIRONMENT", "test")

    # Bypass Redis-backed API key validation in tests
    monkeypatch.setattr(ls.api_key_auth, "validate_key", lambda api_key: ("tenant-test", {"tenant_name": "Test", "tier": "pro"}))
    monkeypatch.setattr(ls.api_key_auth, "get_tenant_rate_limit", lambda tenant_id, tier: 100)
    monkeypatch.setattr(ls.api_key_auth, "check_rate_limit", lambda tenant_id, limit: (True, {"limit": limit, "remaining": limit, "reset": 60, "current_count": 0}))

    return ls.app.test_client()


def test_fail_closed_when_agentshield_unreachable(monkeypatch, client):
    def raise_unreachable(_req):
        raise RuntimeError("AgentShield unreachable")

    monkeypatch.setattr(ls.agentshield, "enforce", raise_unreachable)

    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer vk_test"},
    )

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"]["message"].lower().startswith("agentshield")


def test_fail_closed_on_enforcement_exception(monkeypatch, client):
    class CustomError(Exception):
        pass

    def raise_custom(_req):
        err = CustomError("boom")
        err.vigil_error_code = ls.VigilErrorCode.AGENTSHIELD_UNREACHABLE
        raise err

    monkeypatch.setattr(ls.agentshield, "enforce", raise_custom)

    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer vk_test"},
    )

    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"]["error_code"] == ls.VigilErrorCode.AGENTSHIELD_UNREACHABLE.value
