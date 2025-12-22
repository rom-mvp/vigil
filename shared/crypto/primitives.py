"""
Shared Cryptography - HPKE & Ed25519
Write once, use everywhere. Prevents implementation drift.
"""

import base64
import json
import hashlib
from typing import Dict, Tuple
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization


class HPKECrypto:
    """
    Hybrid Public Key Encryption
    Mock implementation - replace with real HPKE library in production
    """
    
    def __init__(self, enclave_public_key: str = "public_key_loaded_from_attestation"):
        self.enclave_pub_key = enclave_public_key
    
    def encrypt(self, plaintext: str | dict) -> bytes:
        """
        Encrypt data that only the enclave can decrypt
        In production, use: hpke-py or cryptography HPKE
        """
        if isinstance(plaintext, dict):
            plaintext = json.dumps(plaintext)
        
        # MOCK: Base64 encode (NOT REAL ENCRYPTION)
        # TODO: Replace with real HPKE
        encrypted = base64.b64encode(plaintext.encode())
        return encrypted
    
    def decrypt(self, ciphertext: bytes) -> dict:
        """
        Decrypt HPKE payload (only works inside enclave with private key)
        """
        # MOCK: Base64 decode
        plaintext = base64.b64decode(ciphertext).decode()
        return json.loads(plaintext)
    
    @staticmethod
    def generate_keypair() -> Tuple[bytes, bytes]:
        """
        Generate HPKE keypair for enclave
        Returns: (private_key_bytes, public_key_bytes)
        """
        # TODO: Use real HPKE key generation
        # For now, mock with random bytes
        import os
        private_key = os.urandom(32)
        public_key = os.urandom(32)
        return private_key, public_key


class Ed25519Signer:
    """
    Ed25519 Signature for cryptographic audit trail
    All decisions are signed by the enclave
    """
    
    def __init__(self, private_key: Ed25519PrivateKey = None):
        self.private_key = private_key or self._generate_key()
        self.public_key = self.private_key.public_key()
    
    def _generate_key(self) -> Ed25519PrivateKey:
        """Generate new Ed25519 keypair"""
        return Ed25519PrivateKey.generate()
    
    def sign(self, data: dict | str) -> str:
        """
        Sign data with Ed25519
        Returns: Base64-encoded signature
        """
        if isinstance(data, dict):
            # Canonical JSON for consistent signatures
            data = json.dumps(data, sort_keys=True, separators=(",", ":"))
        
        data_bytes = data.encode()
        signature = self.private_key.sign(data_bytes)
        return base64.b64encode(signature).decode()
    
    def verify(self, data: dict | str, signature: str) -> bool:
        """
        Verify Ed25519 signature
        Returns: True if valid, False otherwise
        """
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True, separators=(",", ":"))
        
        try:
            data_bytes = data.encode()
            signature_bytes = base64.b64decode(signature)
            self.public_key.verify(signature_bytes, data_bytes)
            return True
        except Exception:
            return False
    
    def export_public_key(self) -> str:
        """Export public key as base64 PEM"""
        pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return base64.b64encode(pem).decode()
    
    @staticmethod
    def load_public_key(pem_b64: str) -> Ed25519PublicKey:
        """Load public key from base64 PEM"""
        pem = base64.b64decode(pem_b64)
        return serialization.load_pem_public_key(pem)


def compute_hash(data: dict | str) -> str:
    """
    SHA-256 hash for content verification
    Used for input_hash in protocol
    """
    if isinstance(data, dict):
        data = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()
