
import os
import signal
import socket
import subprocess
import time

import pytest


# Default auth headers used by archived integration tests
_DEFAULT_AUTH_HEADERS = {
    "Authorization": "Bearer vk_test_key",
    "X-Tenant-ID": "test-tenant",
    "X-Agent-ID": "test-agent",
    "X-Policy-ID": "policy-test",
    "Content-Type": "application/json",
}


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.25)
    return False


@pytest.fixture(scope="session", autouse=True)
def vigil_server_session():
    """Ensure a local Vigil server is running for archived integration tests."""
    if _wait_for_port("localhost", 8000, timeout=1):
        # Assume an external server is already running.
        yield
        return

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", "src")
    env.setdefault("VIGIL_ENVIRONMENT", "development")
    env.setdefault("VIGIL_ENV", "development")
    # Force API key validation to bypass in dev by disabling Redis
    env.setdefault("REDIS_URL", "redis://127.0.0.1:0/0")
    # Explicitly fail-open if backend dependencies are unavailable
    env.setdefault("VIGIL_FAIL_MODE", "open")
    env.setdefault("AGENTSHIELD_REQUIRED", "false")
    env.setdefault("AGENTSHIELD_URL", "http://localhost:9000")

    proc = subprocess.Popen(
        ["python", "-m", "vigil.local_server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_port("localhost", 8000, timeout=20):
        proc.terminate()
        pytest.skip("Vigil server failed to start on port 8000 for archived tests")

    yield

    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def auth_headers() -> dict:
    """Shared authorization headers for archived HTTP requests."""
    return dict(_DEFAULT_AUTH_HEADERS)
