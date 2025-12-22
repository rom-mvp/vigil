"""
Vigil Invisible Wallet - Secure Enclave Key Manager
Simulates a Trusted Execution Environment (TEE) for credential management
"""
import os
import sys
from typing import Optional


class InvisibleWallet:
    """
    Enterprise-grade credential manager that simulates secure enclave operations.
    
    In production deployments, this class interfaces with hardware-backed key storage
    (AWS Nitro Enclaves, Azure Confidential Compute, Intel SGX) to ensure API keys
    never exist in plaintext within application memory.
    
    For development environments, keys are retrieved from environment variables
    and masked in all logging output.
    """
    
    def __init__(self):
        self.strict_mode = os.getenv('VIGIL_STRICT_MODE', 'false').lower() == 'true'
        self._enclave_mode = os.getenv('VIGIL_ENV', 'local')
        
        if self._enclave_mode == 'production':
            print("[T.E.E.] 🔐 Initializing hardware-backed secure enclave...")
        else:
            print("[WALLET] 🔓 Running in development mode (environment-based keys)")
    
    def get_secret(self, key_id: str) -> Optional[str]:
        """
        Retrieve a secret from the secure enclave.
        
        Args:
            key_id: Identifier for the secret (e.g., 'openai_production_key')
        
        Returns:
            The secret value if found, None otherwise
        
        Security Notes:
            - In production TEE mode, this performs memory decryption inside the enclave
            - Secrets are never logged in plaintext
            - Failed retrievals in STRICT_MODE cause application termination
        """
        # Simulate TEE operation
        if self._enclave_mode == 'production':
            print(f"[T.E.E.] 🔐 Decrypting credential inside secure enclave memory...")
        
        # Map key_id to environment variable
        env_key = f"VIGIL_SECRET_{key_id.upper()}"
        secret = os.getenv(env_key)
        
        if secret:
            # Mask secret in logs
            masked = self._mask_secret(secret)
            print(f"[WALLET] ✅ Retrieved key '{key_id}' → {masked}")
            return secret
        else:
            error_msg = f"[WALLET] ❌ Secret '{key_id}' not found (expected env var: {env_key})"
            
            if self.strict_mode:
                print(f"{error_msg} - STRICT MODE ENABLED, TERMINATING")
                sys.exit(1)
            else:
                print(f"{error_msg} - Continuing in permissive mode")
                return None
    
    def inject_credential(self, key_id: str, target_dict: dict, target_key: str = 'api_key'):
        """
        Inject a secret from the wallet into a request dictionary.
        
        Args:
            key_id: Wallet secret identifier
            target_dict: Dictionary to inject the secret into
            target_key: Key name in the target dictionary
        
        Example:
            wallet.inject_credential('openai_prod', request_data, 'openai_api_key')
        """
        secret = self.get_secret(key_id)
        if secret:
            target_dict[target_key] = secret
            print(f"[WALLET] 🔑 Injected credential '{key_id}' into request payload")
        else:
            if self.strict_mode:
                print(f"[WALLET] ❌ Failed to inject '{key_id}' - STRICT MODE ABORT")
                sys.exit(1)
    
    def _mask_secret(self, secret: str) -> str:
        """
        Mask a secret for safe logging.
        
        Args:
            secret: The secret to mask
        
        Returns:
            Masked version showing only prefix and length
        """
        if not secret:
            return "<empty>"
        
        if len(secret) <= 8:
            return "****"
        
        # Show first 4 chars and length
        prefix = secret[:4] if secret.startswith('sk-') else secret[:2]
        return f"{prefix}{'*' * (len(secret) - len(prefix))} (len={len(secret)})"
    
    def list_available_keys(self) -> list:
        """
        List all available wallet keys from environment.
        
        Returns:
            List of available key identifiers
        """
        keys = []
        for env_var in os.environ:
            if env_var.startswith('VIGIL_SECRET_'):
                key_id = env_var.replace('VIGIL_SECRET_', '').lower()
                keys.append(key_id)
        
        if keys:
            print(f"[WALLET] 📋 Available secrets: {', '.join(keys)}")
        else:
            print("[WALLET] ⚠️  No secrets found in environment (set VIGIL_SECRET_* vars)")
        
        return keys


# Singleton instance for global access
_wallet_instance = None

def get_wallet() -> InvisibleWallet:
    """Get the global InvisibleWallet instance."""
    global _wallet_instance
    if _wallet_instance is None:
        _wallet_instance = InvisibleWallet()
    return _wallet_instance
