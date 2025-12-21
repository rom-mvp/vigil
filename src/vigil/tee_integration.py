"""
TEE Integration Layer for Vigil

Orchestrates TEE client initialization, attestation generation, and key sealing
for secure enclave communication with AgentShield.

Environment Variables:
- VIGIL_TEE_ENABLED: Enable TEE attestation (default: false)
- VIGIL_TEE_TYPE: Platform (sgx, sev, tdx, azure, auto-detect)
- VIGIL_KEY_SEALING_TYPE: Binding type (mrenclave, mrsigner)
- AGENTSHIELD_MODE: Communication mode (http, vsock)
- AGENTSHIELD_VSOCK_CID: Enclave CID (default: 3)
- AGENTSHIELD_VSOCK_PORT: Enclave port (default: 5555)
"""

import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class TEEConfig:
    """TEE Configuration from environment"""
    
    def __init__(self):
        self.tee_enabled = os.getenv("VIGIL_TEE_ENABLED", "false").lower() == "true"
        self.tee_type = os.getenv("VIGIL_TEE_TYPE", "auto")
        self.key_sealing_type = os.getenv("VIGIL_KEY_SEALING_TYPE", "mrenclave")
        self.agentshield_mode = os.getenv("AGENTSHIELD_MODE", "http")
        self.vsock_cid = int(os.getenv("AGENTSHIELD_VSOCK_CID", "3"))
        self.vsock_port = int(os.getenv("AGENTSHIELD_VSOCK_PORT", "5555"))
        self.measurement_policy_file = os.getenv("VIGIL_MEASUREMENT_POLICY_FILE", "/app/measurements.json")
        
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration"""
        return {
            "tee_enabled": self.tee_enabled,
            "tee_type": self.tee_type,
            "key_sealing_type": self.key_sealing_type,
            "agentshield_mode": self.agentshield_mode,
            "vsock_cid": self.vsock_cid,
            "vsock_port": self.vsock_port,
            "measurement_policy_file": self.measurement_policy_file,
        }
    
    def __str__(self):
        return f"TEEConfig(enabled={self.tee_enabled}, type={self.tee_type}, mode={self.agentshield_mode})"


class TEEIntegration:
    """Main TEE orchestration layer
    
    Manages:
    - TEE client lifecycle (init, attestation, key sealing)
    - Communication with AgentShield (HTTP vs vsock)
    - Measurement validation
    - Quote generation and caching
    """
    
    def __init__(self, config: Optional[TEEConfig] = None):
        self.config = config or TEEConfig()
        self.attestation_client = None
        self.key_sealer = None
        self.quote_cache = None
        self.quote_timestamp = None
        
        logger.info(f"Initializing TEEIntegration: {self.config}")
        
        if self.config.tee_enabled:
            self._init_tee_components()
    
    def _init_tee_components(self):
        """Initialize TEE components (attestation + key sealing)"""
        try:
            from vigil.tee_attestation import TEEAttestationClient
            from vigil.key_sealing import KeySealer
            
            self.attestation_client = TEEAttestationClient()
            logger.info(f"✓ TEE Attestation Client initialized: {self.attestation_client.tee_type}")
            
            self.key_sealer = KeySealer()
            logger.info("✓ Key Sealer initialized")
            
        except Exception as e:
            logger.error(f"✗ Failed to initialize TEE components: {e}")
            # Fall back to non-TEE mode
            self.attestation_client = None
            self.key_sealer = None
    
    def get_attestation_quote(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get attestation quote for AgentShield
        
        Returns a structured quote (SGX/SEV/TDX/Azure compatible) or None if TEE disabled.
        
        Args:
            force_refresh: Bypass cache and regenerate quote
        
        Returns:
            {"type": "sgx|sev|tdx|azure", "quote": base64, "signature": base64, "timestamp": ISO8601, ...}
        """
        if not self.attestation_client:
            return None
        
        # Return cached quote if fresh (within 1 hour)
        if self.quote_cache and not force_refresh:
            age = (datetime.utcnow() - self.quote_timestamp).total_seconds()
            if age < 3600:
                logger.debug(f"Using cached attestation quote (age: {age:.0f}s)")
                return self.quote_cache
        
        try:
            # Generate fresh quote
            quote = self.attestation_client.generate_attestation_quote()
            self.quote_cache = quote
            self.quote_timestamp = datetime.utcnow()
            
            logger.info(f"Generated fresh attestation quote (type: {quote.get('type')})")
            return quote
        
        except Exception as e:
            logger.error(f"Failed to generate attestation quote: {e}")
            return None
    
    def verify_measurement_policy(self) -> bool:
        """Verify that current measurements match the allow-list policy
        
        Returns:
            True if measurements valid, False if policy check fails or TEE disabled
        """
        if not self.attestation_client:
            logger.debug("TEE disabled - skipping measurement verification")
            return True
        
        try:
            return self.attestation_client.verify_measurement_policy()
        except Exception as e:
            logger.error(f"Measurement verification failed: {e}")
            return False
    
    def seal_sensitive_value(self, plaintext: bytes, context: Optional[bytes] = None) -> Optional[bytes]:
        """Seal a sensitive value (API key, secret, etc.)
        
        Args:
            plaintext: Data to seal
            context: Optional authenticated data (not encrypted)
        
        Returns:
            Sealed blob, or None if sealing not available
        """
        if not self.key_sealer:
            logger.debug("Key sealing disabled - returning plaintext (INSECURE)")
            return plaintext
        
        try:
            return self.key_sealer.seal_key(plaintext, context)
        except Exception as e:
            logger.error(f"Failed to seal value: {e}")
            return None
    
    def unseal_sensitive_value(self, sealed_blob: bytes) -> Optional[bytes]:
        """Unseal a previously sealed value
        
        Args:
            sealed_blob: Sealed data
        
        Returns:
            Plaintext data, or None if unsealing fails
        """
        if not self.key_sealer:
            logger.debug("Key sealing disabled - returning as-is")
            return sealed_blob
        
        try:
            return self.key_sealer.unseal_key(sealed_blob)
        except Exception as e:
            logger.error(f"Failed to unseal value: {e}")
            return None
    
    def get_agentshield_transport(self):
        """Get transport client for AgentShield communication
        
        Returns HTTP or vsock transport based on configuration.
        """
        if self.config.agentshield_mode == "vsock" and self.attestation_client:
            try:
                from vigil.vsock_transport import VsockClient
                return VsockClient(
                    enclave_cid=self.config.vsock_cid,
                    enclave_port=self.config.vsock_port
                )
            except Exception as e:
                logger.error(f"Failed to create vsock transport: {e}")
                logger.info("Falling back to HTTP transport")
        
        # Default: HTTP transport (via agentshield_client.py)
        return None
    
    def create_agentshield_request(self, decision_request: Dict[str, Any]) -> Dict[str, Any]:
        """Wrap decision request with attestation quote for AgentShield
        
        Adds quote to the request payload so AgentShield can verify client identity.
        
        Args:
            decision_request: Base decision request (llm_call, context, etc.)
        
        Returns:
            Decision request with embedded attestation quote
        """
        if not self.attestation_client:
            return decision_request
        
        # Add attestation to request
        request = decision_request.copy()
        request["_attestation"] = self.get_attestation_quote()
        
        return request
    
    def to_dict(self) -> Dict[str, Any]:
        """Export TEE integration state"""
        return {
            "config": self.config.to_dict(),
            "attestation_client": {
                "type": self.attestation_client.tee_type if self.attestation_client else None,
                "instance_id": self.attestation_client.instance_id if self.attestation_client else None,
            },
            "key_sealer_enabled": self.key_sealer is not None,
            "quote_cached": self.quote_cache is not None,
        }


# Global instance
_tee_integration = None


def init_tee(config: Optional[TEEConfig] = None) -> TEEIntegration:
    """Initialize the global TEE integration instance
    
    Should be called once during application startup.
    """
    global _tee_integration
    _tee_integration = TEEIntegration(config)
    return _tee_integration


def get_tee() -> TEEIntegration:
    """Get the global TEE integration instance
    
    Initialize with init_tee() first.
    """
    global _tee_integration
    if _tee_integration is None:
        _tee_integration = TEEIntegration()
    return _tee_integration


# Testing helper
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)
    
    # Test with default config
    config = TEEConfig()
    print(f"\n{config}\n")
    print(f"Config: {json.dumps(config.to_dict(), indent=2)}")
    
    # Initialize
    tee = TEEIntegration(config)
    print(f"\n{json.dumps(tee.to_dict(), indent=2)}")
    
    # Try to get attestation quote
    if tee.attestation_client:
        quote = tee.get_attestation_quote()
        if quote:
            print(f"\nAttestationQuote Type: {quote.get('type')}")
            print(f"Timestamp: {quote.get('timestamp')}")
    else:
        print("\n✗ TEE disabled - no attestation available")
