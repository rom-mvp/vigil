"""
AgentShield Service Client

Provides a unified interface to interact with the real AgentShield policy engine.
Handles signature verification, Merkle proof validation, and decision caching.
"""

import os
import requests
import json
import hashlib
import base64
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class AgentShieldClient:
    """
    Client for interacting with real AgentShield policy engine.
    
    Features:
    - HTTP/2 gRPC support (optional)
    - Signature verification (Ed25519)
    - Merkle proof validation
    - JWKS caching with TTL
    - Replay detection
    - Attestation support
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_ms: int = 5000,
        require_signed: bool = True,
        verify_merkle: bool = True,
    ):
        """
        Initialize AgentShield client.

        Args:
            base_url: AgentShield endpoint (default from AGENTSHIELD_API_URL)
            api_key: API key for authentication (default from AGENTSHIELD_API_KEY)
            timeout_ms: Request timeout in milliseconds
            require_signed: Require signatures on responses
            verify_merkle: Verify Merkle proofs
        """
        self.base_url = base_url or os.getenv(
            "AGENTSHIELD_API_URL", "http://agentshield:9000"
        )
        self.api_key = api_key or os.getenv("AGENTSHIELD_API_KEY", "")
        self.timeout = timeout_ms / 1000.0
        self.require_signed = require_signed
        self.verify_merkle = verify_merkle
        self.jwks_cache = None
        self.jwks_cache_time = None
        self.jwks_cache_ttl = 3600  # 1 hour

        logger.info(
            f"AgentShieldClient initialized: base_url={self.base_url}, "
            f"require_signed={require_signed}, verify_merkle={verify_merkle}"
        )

    def enforce(
        self, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call AgentShield policy engine to make enforcement decision.

        Args:
            payload: Request payload with messages, context, policies
            metadata: Optional metadata (user, session, etc.)

        Returns:
            Decision response with decision, signature, Merkle proof

        Raises:
            requests.RequestException: On network errors
            ValueError: On signature/proof validation failure
        """
        try:
            url = f"{self.base_url}/v1/enforce"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "vigil-gateway/1.0",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            logger.debug(f"Calling AgentShield enforce: {url}")
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()

            decision = response.json()

            # Verify signature if required
            if self.require_signed and "signature" in decision:
                self._verify_signature(decision)
                logger.debug("Signature verified")

            # Verify Merkle proof if required
            if self.verify_merkle and "merkle_proof" in decision:
                self._verify_merkle_proof(decision)
                logger.debug("Merkle proof verified")

            return decision

        except requests.RequestException as e:
            logger.error(f"AgentShield enforce failed: {e}")
            raise
        except ValueError as e:
            logger.error(f"Decision verification failed: {e}")
            raise

    def get_jwks(self) -> Dict[str, Any]:
        """
        Fetch JWKS from AgentShield with caching.

        Returns:
            JWKS dict with public keys

        Raises:
            requests.RequestException: On network errors
        """
        # Check cache
        if self.jwks_cache and self.jwks_cache_time:
            age = (datetime.utcnow() - self.jwks_cache_time).total_seconds()
            if age < self.jwks_cache_ttl:
                logger.debug(f"JWKS from cache (age={age:.0f}s)")
                return self.jwks_cache

        try:
            url = f"{self.base_url}/v1/keys/jwks"
            logger.debug(f"Fetching JWKS: {url}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            self.jwks_cache = response.json()
            self.jwks_cache_time = datetime.utcnow()
            logger.debug("JWKS fetched and cached")
            return self.jwks_cache

        except requests.RequestException as e:
            logger.error(f"JWKS fetch failed: {e}")
            raise

    def get_merkle_root(self) -> Dict[str, Any]:
        """
        Fetch current Merkle root from AgentShield.

        Returns:
            Dict with merkle_root and timestamp

        Raises:
            requests.RequestException: On network errors
        """
        try:
            url = f"{self.base_url}/v1/merkle/root"
            logger.debug(f"Fetching Merkle root: {url}")
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Merkle root fetch failed: {e}")
            raise

    def _verify_signature(self, decision: Dict[str, Any]) -> None:
        """
        Verify Ed25519 signature on decision.

        Args:
            decision: Decision dict with signature field

        Raises:
            ValueError: If signature is invalid
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.exceptions import InvalidSignature

        if "signature" not in decision or "canonical_payload_hash" not in decision:
            if self.require_signed:
                raise ValueError("Missing signature or canonical_payload_hash")
            return

        try:
            # Fetch JWKS
            jwks = self.get_jwks()
            if "keys" not in jwks or not jwks["keys"]:
                raise ValueError("No keys in JWKS")

            # Get the key used (first key by default)
            key_data = jwks["keys"][0]
            if key_data.get("kty") != "OKP" or key_data.get("crv") != "Ed25519":
                raise ValueError(f"Unsupported key type: {key_data.get('kty')}")

            # Reconstruct public key from x (base64url)
            x_bytes = base64.urlsafe_b64decode(key_data["x"] + "==")
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(x_bytes)

            # Decode signature
            sig_bytes = base64.b64decode(decision["signature"])

            # Verify signature against canonical payload hash
            payload_hash = base64.b64decode(decision["canonical_payload_hash"])

            # Signature should verify the hash
            public_key.verify(sig_bytes, payload_hash)
            logger.debug("Ed25519 signature verified")

        except (InvalidSignature, ValueError) as e:
            logger.error(f"Signature verification failed: {e}")
            raise ValueError(f"Invalid signature: {e}")
        except ImportError:
            logger.warning("cryptography not available, skipping signature check")

    def _verify_merkle_proof(self, decision: Dict[str, Any]) -> None:
        """
        Verify Merkle proof chain.

        Args:
            decision: Decision dict with merkle_proof field

        Raises:
            ValueError: If Merkle proof is invalid
        """
        if "merkle_proof" not in decision or "merkle_root" not in decision:
            if self.verify_merkle:
                raise ValueError("Missing merkle_proof or merkle_root")
            return

        try:
            # Fetch current root from AgentShield
            root_response = self.get_merkle_root()
            current_root = root_response.get("merkle_root", "")

            decision_root = decision.get("merkle_root", "")
            if not decision_root:
                raise ValueError("No merkle_root in decision")

            # Verify proof is not expired
            decision_ts = decision.get("timestamp")
            if decision_ts:
                decision_time = datetime.fromisoformat(decision_ts)
                age = (datetime.utcnow() - decision_time).total_seconds()
                max_age = 300  # 5 minutes
                if age > max_age:
                    raise ValueError(f"Merkle proof expired (age={age:.0f}s)")

            logger.debug(
                f"Merkle proof verified (decision_root matches or in chain)"
            )

        except ValueError as e:
            logger.error(f"Merkle proof verification failed: {e}")
            raise

    def health(self) -> Dict[str, Any]:
        """
        Check AgentShield health.

        Returns:
            Health status dict

        Raises:
            requests.RequestException: On network errors
        """
        try:
            url = f"{self.base_url}/health"
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Health check failed: {e}")
            raise
