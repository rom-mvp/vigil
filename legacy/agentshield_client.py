import base64
import json
import os
import time
from typing import Any, Dict, Optional

import requests

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, ed25519, rsa
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
        self.jwks_url = os.getenv("AGENTSHIELD_JWKS_URL")
        self.mtls_cert = os.getenv("AGENTSHIELD_MTLS_CERT")
        self.mtls_key = os.getenv("AGENTSHIELD_MTLS_KEY")
        self._jwks_cache: Optional[Dict] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl = int(os.getenv("AGENTSHIELD_JWKS_TTL", "3600"))
        self._pubkey = self._load_pubkey()

    def _fetch_jwks(self) -> Dict:
        if not self.jwks_url:
            return {}
        now = time.time()
        if self._jwks_cache and (now - self._jwks_cache_time) < self._jwks_cache_ttl:
            return self._jwks_cache
        try:
            resp = requests.get(self.jwks_url, timeout=self.timeout_ms / 1000.0)
            resp.raise_for_status()
            self._jwks_cache = resp.json()
            self._jwks_cache_time = now
            return self._jwks_cache
        except Exception:
            return self._jwks_cache or {}

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

    def _get_key_from_jwks(self, key_id: str):
        jwks = self._fetch_jwks()
        keys = jwks.get("keys", [])
        for key_data in keys:
            if key_data.get("kid") == key_id:
                kty = key_data.get("kty")
                if kty == "OKP" and key_data.get("crv") == "Ed25519":
                    x_b64 = key_data.get("x")
                    if x_b64:
                        x_bytes = base64.urlsafe_b64decode(x_b64 + "==")
                        return ed25519.Ed25519PublicKey.from_public_bytes(x_bytes)
                elif kty == "RSA":
                    # Future: decode RSA from JWK if needed
                    pass
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

        signature_b64 = decision.get("signature")
        signature_key_id = decision.get("signature_key_id") or decision.get("key_id")
        if not signature_b64 or not signature_key_id:
            raise ValueError("Unsigned decision or missing signature_key_id")

        # Validate context_echo if present
        context_echo = decision.get("context_echo")
        if context_echo:
            req_tenant = enforcement_request.get("tenant_id")
            req_user = enforcement_request.get("agent_id")
            req_policy = enforcement_request.get("policy_version")
            if context_echo.get("tenant_id") != req_tenant:
                raise ValueError(f"Context mismatch: tenant {context_echo.get('tenant_id')} != {req_tenant}")
            if context_echo.get("user_id") != req_user:
                raise ValueError(f"Context mismatch: user {context_echo.get('user_id')} != {req_user}")
            if context_echo.get("policy_version") != req_policy:
                raise ValueError(f"Context mismatch: policy {context_echo.get('policy_version')} != {req_policy}")

        # Load key from JWKS or pinned
        pubkey = None
        if self.jwks_url:
            pubkey = self._get_key_from_jwks(signature_key_id)
        if not pubkey:
            pubkey = self._pubkey
        if not pubkey:
            raise RuntimeError("No public key available for signature verification")

        try:
            signature = base64.urlsafe_b64decode(signature_b64 + "==")
        except Exception as exc:
            raise ValueError("Invalid signature encoding") from exc

        # Verify based on key type
        if isinstance(pubkey, ed25519.Ed25519PublicKey):
            # Ed25519: verify against canonical_payload_hash if provided, else canonical payload
            canonical_hash = decision.get("canonical_payload_hash")
            if canonical_hash:
                message = base64.urlsafe_b64decode(canonical_hash + "==")
            else:
                message = self._canonical_payload(enforcement_request, decision)
            pubkey.verify(signature, message)
        elif isinstance(pubkey, rsa.RSAPublicKey):
            # RSA: verify against canonical payload
            payload = self._canonical_payload(enforcement_request, decision)
            pubkey.verify(
                signature,
                payload,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        else:
            raise ValueError("Unsupported key type for verification")
        return True

    def enforce(self, enforcement_request: dict) -> dict:
        if self.mode != "http":
            # vsock mode not implemented in dev; stub
            raise RuntimeError("vsock mode not implemented")
        url = f"{self.base_url}/v1/enforce"
        cert = None
        if self.mtls_cert and self.mtls_key:
            cert = (self.mtls_cert, self.mtls_key)
        resp = requests.post(url, json=enforcement_request, timeout=self.timeout_ms / 1000.0, cert=cert)
        resp.raise_for_status()
        decision = resp.json()
        if self.require_signed:
            self._verify_signature(enforcement_request, decision)
            decision["sig_verified"] = True
        else:
            decision["sig_verified"] = False
        return decision
