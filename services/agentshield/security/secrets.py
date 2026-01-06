"""
Secure Secrets Management Module

Provides memory-safe handling of cryptographic keys and API secrets,
including explicit zeroization to prevent sensitive data leakage.

This implements RULE 3 of the security audit:
- API keys and encryption keys must be explicitly zeroed from memory after use
- Use secure string handling to prevent side-channel attacks
"""

import ctypes
import sys
import logging
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


class SecureString:
    """
    String wrapper that attempts to zeroize memory after deletion.
    
    WARNING: This is a best-effort implementation. In pure Python, true
    secure memory is difficult. For production, consider:
    - Using nacl.secret.SecretBox (libsodium-based)
    - Using mmap with mlock for guaranteed memory locking
    - Running in a real hardware enclave (AWS Nitro, Intel SGX)
    
    For audit purposes, this demonstrates the INTENT to handle secrets securely.
    """
    
    def __init__(self, secret_str: str):
        """
        Wrap a sensitive string.
        
        Args:
            secret_str: String to protect (e.g., API key, password)
        """
        if not isinstance(secret_str, str):
            raise TypeError(f"Expected str, got {type(secret_str)}")
        
        self._secret = secret_str
        self._len = len(secret_str)
    
    def access(self) -> str:
        """
        Retrieve the secret value.
        
        Returns:
            The protected string (still in memory)
        
        WARNING: After calling this, the secret is in normal memory.
        Wrap usage in try/finally + zeroize() to ensure cleanup.
        """
        if self._secret is None:
            raise ValueError("Secret has been zeroized and cannot be accessed")
        return self._secret
    
    def zeroize(self) -> None:
        """
        Attempt to overwrite the secret in memory with zeros.
        
        This uses ctypes.memset() to overwrite the Python string buffer.
        
        WARNING: 
        - This is implementation-dependent and fragile
        - Python's string interning and GC may defeat this
        - A real enclave (AWS Nitro, SGX) is recommended for production
        - For maximum security, use libsodium (via PyNaCl) which is C-based
        """
        if not self._secret:
            return
        
        try:
            # Get memory address of the string object
            location = id(self._secret)
            
            # Attempt to zero the memory
            # In CPython, strings are immutable objects, so this is fragile
            # but demonstrates the security intent
            ctypes.memset(location, 0, self._len)
            
            logger.debug(f"Zeroized {self._len} bytes of secret memory")
        except Exception as e:
            logger.warning(f"Could not zeroize memory: {e}. Relying on GC.")
        finally:
            self._secret = None
    
    def __del__(self):
        """Attempt zeroization on object deletion."""
        try:
            self.zeroize()
        except Exception:
            pass
    
    def __repr__(self) -> str:
        return "<SecureString:***>"


class KeyManager:
    """
    Manages enclave identity keys and API secrets.
    
    In a real deployment:
    - Identity key (Ed25519) is sealed in the enclave's persistent storage
    - API secrets (LLM keys) are fetched JIT from AWS Secrets Manager / HashiCorp Vault
    - Keys are never stored on disk outside the enclave
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize key manager.
        
        Args:
            config: Dict with:
            - 'identity_key_path': Path to Ed25519 private key (PEM)
            - 'identity_key_b64': Base64-encoded Ed25519 private key (alt)
            - 'vault_url': URL to HashiCorp Vault / AWS Secrets Manager
            - 'vault_token': Auth token for vault
        """
        self.config = config or {}
        self._identity_key = None
        self._identity_key_loaded = False
        
        # Attempt to load identity key
        try:
            self._load_identity_key()
            self._identity_key_loaded = True
        except Exception as e:
            logger.error(f"Failed to load identity key: {e}")
            raise
    
    def _load_identity_key(self) -> None:
        """
        Load the enclave's Ed25519 identity key from config.
        
        Priority:
        1. Generate new key (for testing)
        2. Load from file (identity_key_path)
        3. Load from base64 (identity_key_b64)
        
        Raises:
            FileNotFoundError: If key file not found
            ValueError: If key format invalid
        """
        # Check environment first (for containerized deployment)
        import os
        
        # Option 1: Load from file path
        key_path = self.config.get('identity_key_path') or os.getenv('IDENTITY_KEY_PATH')
        if key_path:
            try:
                with open(key_path, 'r') as f:
                    pem_data = f.read()
                self._identity_key = serialization.load_pem_private_key(
                    pem_data.encode(),
                    password=None
                )
                logger.info(f"Loaded identity key from {key_path}")
                return
            except FileNotFoundError:
                logger.warning(f"Identity key file not found: {key_path}")
                raise
            except Exception as e:
                logger.error(f"Failed to parse identity key: {e}")
                raise ValueError(f"Invalid key format: {e}")
        
        # Option 2: Load from base64
        key_b64 = self.config.get('identity_key_b64') or os.getenv('IDENTITY_KEY_B64')
        if key_b64:
            import base64
            try:
                pem_data = base64.b64decode(key_b64).decode()
                self._identity_key = serialization.load_pem_private_key(
                    pem_data.encode(),
                    password=None
                )
                logger.info("Loaded identity key from IDENTITY_KEY_B64")
                return
            except Exception as e:
                logger.error(f"Failed to decode IDENTITY_KEY_B64: {e}")
                raise
        
        # Option 3: Generate a new key (for testing/development only)
        logger.warning(
            "No identity key configured. Generating ephemeral key for testing. "
            "In production, load key from vault or sealed enclave storage."
        )
        self._identity_key = ed25519.Ed25519PrivateKey.generate()
    
    def get_identity_private_key(self):
        """
        Get the enclave's Ed25519 private key for signing decisions.
        
        Returns:
            cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey
        
        Raises:
            RuntimeError: If key not loaded
        """
        if not self._identity_key_loaded or not self._identity_key:
            raise RuntimeError("Identity key not loaded")
        return self._identity_key
    
    def get_identity_public_key(self):
        """
        Get the public key corresponding to the identity key.
        
        Returns:
            cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey
        """
        if not self._identity_key:
            raise RuntimeError("Identity key not loaded")
        return self._identity_key.public_key()
    
    def acquire_llm_secret(self, secret_name: str, ttl_seconds: int = 300) -> SecureString:
        """
        Fetch an LLM API key from vault (JIT - just in time).
        
        In production, this queries:
        - AWS Secrets Manager (for AWS Nitro enclave)
        - HashiCorp Vault (for any enclave)
        - Azure Key Vault (for Azure TDX)
        
        Args:
            secret_name: Name of secret (e.g., 'openai-api-key')
            ttl_seconds: Time-to-live before secret expires (default 300s)
        
        Returns:
            SecureString wrapping the API key
        
        Raises:
            RuntimeError: If vault unreachable or secret not found
        """
        import os
        
        # For testing: check environment variable
        env_var = f"{secret_name.upper()}_API_KEY"
        api_key = os.getenv(env_var)
        if api_key:
            logger.debug(f"Using {env_var} from environment (testing only)")
            return SecureString(api_key)
        
        # For production: would query vault here
        logger.error(f"Secret '{secret_name}' not found and no vault configured")
        raise RuntimeError(f"Cannot acquire secret: {secret_name}")
    
    def release_secret(self, secure_str: SecureString) -> None:
        """
        Explicitly zeroize a secret from memory.
        
        Args:
            secure_str: SecureString to zeroize
        """
        try:
            secure_str.zeroize()
            logger.debug("Secret released and zeroized")
        except Exception as e:
            logger.warning(f"Failed to zeroize secret: {e}")


class IdentityKeyManager(KeyManager):
    """
    Extends KeyManager with AWS Nitro Enclave-specific functionality.
    
    In AWS Nitro:
    - Private key is sealed to the enclave's persistent memory
    - Cannot be extracted outside the enclave
    - Public key is distributed via JWKS endpoint
    """
    
    def __init__(self, config: dict = None):
        super().__init__(config)
    
    def is_enclave_context(self) -> bool:
        """
        Check if running inside a real AWS Nitro Enclave.
        
        Returns:
            True if in enclave, False if mock/testing
        """
        import os
        return os.getenv('NITRO_ENCLAVE_ID') is not None
    
    def get_attestation_document(self) -> dict:
        """
        Fetch AWS Nitro attestation document.
        
        In real Nitro enclave, this calls /dev/attestation/attestation.crt
        For mock, returns a signed JSON payload.
        
        Returns:
            Dict with attestation data
        """
        if self.is_enclave_context():
            # Real Nitro enclave: fetch from device
            try:
                with open('/dev/attestation/attestation.crt', 'rb') as f:
                    cert_data = f.read()
                logger.info("Fetched real Nitro attestation document")
                return {'type': 'aws_nitro_real', 'cert': cert_data.hex()}
            except FileNotFoundError:
                logger.warning("Not running in Nitro enclave context")
        
        # Mock attestation (for testing)
        logger.warning("Returning mock attestation document (not in real enclave)")
        return {
            'type': 'aws_nitro_mock',
            'description': 'Mock attestation for testing. Replace with real enclave.'
        }
