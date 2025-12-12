import os
import requests


class AgentShieldClient:
    def __init__(self):
        self.base_url = os.getenv("AGENTSHIELD_URL", "http://localhost:9000")
        self.timeout_ms = int(os.getenv("AGENTSHIELD_TIMEOUT_MS", "3000"))
        self.mode = os.getenv("AGENTSHIELD_MODE", "http")

    def enforce(self, enforcement_request: dict) -> dict:
        if self.mode != "http":
            # vsock mode not implemented in dev; stub
            raise RuntimeError("vsock mode not implemented")
        url = f"{self.base_url}/v1/enforce"
        resp = requests.post(url, json=enforcement_request, timeout=self.timeout_ms / 1000.0)
        resp.raise_for_status()
        return resp.json()
