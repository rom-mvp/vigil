"""
Decision Signer Module

Cryptographically signs enforcement decisions with Ed25519 to provide
tamper-proof receipts that Vigil can verify.

This implements RULE 6 of the security audit:
- Every decision must be signed by the enclave's private key
- Vigil must verify the signature using the enclave's public key (via JWKS)
"""

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import json
import time
import base64
import logging

logger = logging.getLogger(__name__)


class DecisionSigner:
    """
    Signs enclave decisions with Ed25519 private key.
    
    Produces a canonical JSON payload + signature that can be verified
    by Vigil using the public key distributed via JWKS endpoint.
    """
    
    def __init__(self, key_manager):
        """
        Initialize signer with enclave's identity key.
        
        Args:
            key_manager: Object with get_identity_private_key() method
        
        Raises:
            ValueError: If key manager doesn't provide valid Ed25519 private key
        """
        self._private_key = key_manager.get_identity_private_key()
        
        if not isinstance(self._private_key, ed25519.Ed25519PrivateKey):
            raise ValueError(
                f"Expected Ed25519PrivateKey, got {type(self._private_key)}"
            )
        
        self._public_key = self._private_key.public_key()
        logger.info("DecisionSigner initialized with Ed25519 key")
    
    def sign_decision(
        self,
        decision: str,
        risk_score: float,
        reasons: list,
        context: dict,
        decision_id: str = None
    ) -> dict:
        """
        Create a cryptographically-signed decision receipt.
        
        The signature binds together:
        - The decision verdict (ALLOW/BLOCK)
        - The risk score (0.0 - 1.0)
        - The policy hash (ensures policy wasn't changed)
        - The tenant ID (prevents cross-tenant confusion)
        - The timestamp (prevents replay attacks)
        
        Args:
            decision: "ALLOW" or "BLOCK"
            risk_score: Float between 0.0 and 1.0
            reasons: List of human-readable enforcement reasons
            context: Dict with 'tenant', 'policy_hash', 'request_id'
            decision_id: Optional decision ID (UUID); generated if omitted
        
        Returns:
            Dict with:
            - payload: The canonical decision object
            - signature: Base64-encoded Ed25519 signature
            - public_key: Base64-encoded public key for verification
            - algorithm: "Ed25519"
        
        Raises:
            ValueError: If decision not in ['ALLOW', 'BLOCK']
            TypeError: If risk_score not a number
        """
        # Validate inputs
        if decision not in ("ALLOW", "BLOCK"):
            raise ValueError(f"Invalid decision: {decision}. Must be ALLOW or BLOCK.")
        
        if not isinstance(risk_score, (int, float)) or not (0.0 <= risk_score <= 1.0):
            raise ValueError(f"risk_score must be between 0.0 and 1.0, got {risk_score}")
        
        if not isinstance(reasons, list):
            raise ValueError(f"reasons must be a list, got {type(reasons)}")
        
        # Canonical Payload (Order matters for signature verification!)
        # Use short keys to minimize signature footprint
        payload = {
            "v": "1.0",                              # Version
            "d": decision,                           # Decision (ALLOW/BLOCK)
            "r": round(risk_score, 4),              # Risk score (0.0 - 1.0)
            "t": context.get("tenant", "unknown"),  # Tenant ID
            "ts": int(time.time()),                 # Timestamp (unix seconds)
            "ph": context.get("policy_hash", ""),   # Policy hash (bind to policy version)
            "req_id": context.get("request_id", ""),# Request ID (traceability)
        }
        
        # Add decision reasons (non-sensitive summaries only)
        if reasons:
            payload["reasons"] = reasons[:5]  # Limit to 5 reasons
        
        # Add decision ID if provided
        if decision_id:
            payload["id"] = decision_id
        
        # Create canonical JSON (deterministic ordering, compact)
        canonical_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        )
        
        logger.debug(
            f"Signing decision: {decision} for tenant={context.get('tenant')} "
            f"risk_score={risk_score} policy_hash={context.get('policy_hash', 'unknown')[:12]}"
        )
        
        # Sign with Ed25519
        try:
            signature_bytes = self._private_key.sign(canonical_json.encode('utf-8'))
            signature_b64 = base64.b64encode(signature_bytes).decode('ascii')
        except Exception as e:
            logger.error(f"Signature generation failed: {e}")
            raise RuntimeError(f"Failed to sign decision: {e}")
        
        # Construct response with public key for verification
        result = {
            "payload": payload,
            "signature": signature_b64,
            "public_key": self.get_public_key_b64(),
            "algorithm": "Ed25519",
            "key_id": "agentshield-ed25519-v1"
        }
        
        logger.info(
            f"Decision signed: {decision} "
            f"sig={signature_b64[:16]}... "
            f"risk={risk_score}"
        )
        
        return result
    
    def get_public_key_b64(self) -> str:
        """
        Get Base64-encoded public key for JWKS distribution.
        
        Returns:
            Base64-encoded raw Ed25519 public key (32 bytes)
        """
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        return base64.b64encode(pub_bytes).decode('ascii')
    
    def get_public_key_pem(self) -> str:
        """
        Get PEM-encoded public key for certificate distribution.
        
        Returns:
            PEM-encoded Ed25519 public key
        """
        pub_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pub_bytes.decode('ascii')
    
    def verify_signature(self, signature_b64: str, canonical_json: str) -> bool:
        """
        Verify a signature (used for testing/debugging).
        
        Args:
            signature_b64: Base64-encoded signature
            canonical_json: Original canonical JSON that was signed
        
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            signature_bytes = base64.b64decode(signature_b64)
            self._public_key.verify(signature_bytes, canonical_json.encode('utf-8'))
            return True
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False
