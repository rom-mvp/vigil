import base64
import json
import os
from typing import Any, Dict

import requests

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


class AgentShieldClient:
    def __init__(self):
        self.base_url = os.getenv("AGENTSHIELD_URL", "http://localhost:9000")
        self.timeout_ms = int(os.getenv("AGENTSHIELD_TIMEOUT_MS", "3000"))
        self.mode = os.getenv("AGENTSHIELD_MODE", "http")
        self.require_signed = os.getenv("AGENTSHIELD_REQUIRE_SIGNED", "true").lower() == "true"
        self.key_id = os.getenv("AGENTSHIELD_KEY_ID", "default")
        self.pubkey_path = os.getenv("AGENTSHIELD_PUBKEY_PATH")
        self.pubkey_pem = os.getenv("AGENTSHIELD_PUBKEY_PEM")
        self._pubkey = self._load_pubkey()

    def _load_pubkey(self):
        data = None
        if self.pubkey_path and os.path.exists(self.pubkey_path):
            with open(self.pubkey_path, "rb") as f:
                data = f.read()
        elif self.pubkey_pem:
            data = self.pubkey_pem.encode("utf-8")
        if data and _CRYPTO_AVAILABLE:
            return load_pem_public_key(data)
        return None

    @staticmethod
    def _canonical_payload(enforcement_request: Dict[str, Any], decision: Dict[str, Any]) -> bytes:
        payload = {
            "request_context": {
                "request_id": enforcement_request.get("request_id"),
                "tenant_id": enforcement_request.get("tenant_id"),
                "agent_id": enforcement_request.get("agent_id"),
                "policy_version": enforcement_request.get("policy_version"),
                "environment": enforcement_request.get("environment"),
            },
            "decision": {
                "action": decision.get("action"),
                "risk_score": decision.get("risk_score"),
                "reasons": decision.get("reasons"),
                "audit_event_id": decision.get("audit_event_id"),
                "signature_hash": decision.get("signature_hash"),
                "sanitized": decision.get("sanitized"),
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _verify_signature(self, enforcement_request: dict, decision: dict):
        if not self.require_signed:
            return True
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography not installed; cannot verify signature")
        if not self._pubkey:
            raise RuntimeError("No pinned public key configured for AgentShield verification")

        signature_b64 = decision.get("signature")
        key_id = decision.get("key_id")
        if not signature_b64 or not key_id:
            raise ValueError("Unsigned decision or missing key_id")
        if key_id != self.key_id:
            raise ValueError(f"Unexpected key_id {key_id}; expected {self.key_id}")

        try:
            signature = base64.urlsafe_b64decode(signature_b64 + "==")
        except Exception as exc:
            raise ValueError("Invalid signature encoding") from exc

        payload = self._canonical_payload(enforcement_request, decision)
        self._pubkey.verify(
            signature,
            payload,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True

    def enforce(self, enforcement_request: dict) -> dict:
        if self.mode != "http":
            # vsock mode not implemented in dev; stub
            raise RuntimeError("vsock mode not implemented")
        url = f"{self.base_url}/v1/enforce"
        resp = requests.post(url, json=enforcement_request, timeout=self.timeout_ms / 1000.0)
        resp.raise_for_status()
        decision = resp.json()
        if self.require_signed:
            self._verify_signature(enforcement_request, decision)
            decision["sig_verified"] = True
        else:
            decision["sig_verified"] = False
        return decision
