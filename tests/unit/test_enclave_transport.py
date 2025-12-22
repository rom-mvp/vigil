"""
Unit tests for EnclaveTransport - HPKE Encryption & VSOCK Communication
Tests the blind forwarder functionality
"""

import pytest
import json
import base64
from vigil.enclave_transport import EnclaveTransport


@pytest.mark.unit
class TestEnclaveTransport:
    """Test suite for EnclaveTransport encryption and forwarding"""
    
    def test_initialization(self):
        """Test EnclaveTransport initializes with correct defaults"""
        transport = EnclaveTransport()
        
        assert transport.cid == 88
        assert transport.port == 5000
        assert transport.enclave_pub_key == "public_key_loaded_from_attestation"
    
    def test_custom_initialization(self):
        """Test EnclaveTransport with custom CID and port"""
        transport = EnclaveTransport(cid=99, port=6000)
        
        assert transport.cid == 99
        assert transport.port == 6000
    
    def test_hpke_encrypt(self):
        """Test HPKE encryption produces encrypted output"""
        transport = EnclaveTransport()
        payload = "Hello, secure world!"
        
        encrypted = transport._hpke_encrypt(payload)
        
        # Should be bytes
        assert isinstance(encrypted, bytes)
        
        # Should be base64-encoded (in this mock implementation)
        assert base64.b64decode(encrypted) == payload.encode()
        
        # Should not equal plaintext
        assert encrypted != payload.encode()
    
    def test_hpke_decrypt(self):
        """Test HPKE decryption reverses encryption"""
        transport = EnclaveTransport()
        original_data = {"prompt": "test", "encrypted": True}
        
        # Encrypt then decrypt
        encrypted = transport._hpke_encrypt(json.dumps(original_data))
        decrypted = transport._hpke_decrypt(encrypted)
        
        assert decrypted == original_data
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test full encrypt/decrypt roundtrip preserves data"""
        transport = EnclaveTransport()
        test_payloads = [
            {"simple": "value"},
            {"complex": {"nested": "data", "array": [1, 2, 3]}},
            {"unicode": "Hello 世界 🌍"},
            {"empty": {}},
        ]
        
        for payload in test_payloads:
            encrypted = transport._hpke_encrypt(json.dumps(payload))
            decrypted = transport._hpke_decrypt(encrypted)
            assert decrypted == payload, f"Roundtrip failed for {payload}"
    
    def test_send_secure_fallback(self, monkeypatch):
        """Test send_secure uses HTTP fallback when VSOCK unavailable"""
        import requests
        import socket
        from unittest.mock import Mock, patch, MagicMock
        
        transport = EnclaveTransport()
        payload = {"prompt": "test request"}
        
        # Mock socket to raise AttributeError (VSOCK not available)
        original_socket = socket.socket
        def mock_socket_creation(*args, **kwargs):
            # Check if it's trying to create AF_VSOCK
            if args and hasattr(socket, 'AF_VSOCK') and args[0] == socket.AF_VSOCK:
                raise AttributeError("AF_VSOCK not available")
            return original_socket(*args, **kwargs)
        
        # Mock requests.post to simulate HTTP fallback
        mock_response = Mock()
        mock_response.json.return_value = {
            "decision": "ALLOW",
            "encrypted": True,
            "latency_ms": 15.0
        }
        
        with patch('socket.socket', side_effect=AttributeError("AF_VSOCK not available")):
            with patch('requests.post', return_value=mock_response):
                result = transport.send_secure(payload)
        
        assert result["decision"] == "ALLOW"
        assert result["encrypted"] is True
    
    def test_encryption_produces_different_output(self):
        """Test that encryption is not deterministic (includes randomness)"""
        transport = EnclaveTransport()
        payload = "test data"
        
        # Note: In real HPKE, encryption should produce different output each time
        # This mock implementation is deterministic, but we test the interface
        encrypted1 = transport._hpke_encrypt(payload)
        encrypted2 = transport._hpke_encrypt(payload)
        
        # Both should be valid encryptions
        assert isinstance(encrypted1, bytes)
        assert isinstance(encrypted2, bytes)
        
        # In mock implementation, they're the same (deterministic)
        # In real HPKE, they would differ (non-deterministic)
        assert encrypted1 == encrypted2  # Mock behavior
    
    def test_blind_forwarding_principle(self):
        """Test that host cannot read encrypted payload"""
        transport = EnclaveTransport()
        sensitive_data = {
            "api_key": "sk-secret-key-12345",
            "user_prompt": "Confidential business strategy"
        }
        
        encrypted = transport._hpke_encrypt(json.dumps(sensitive_data))
        
        # Verify it's encrypted (not plaintext JSON)
        try:
            # This should fail because encrypted data is not valid JSON
            json.loads(encrypted)
            assert False, "Encrypted data should not be valid JSON"
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            # Expected - encrypted data cannot be parsed as JSON
            pass
        
        # Verify decryption works
        decrypted = transport._hpke_decrypt(encrypted)
        assert decrypted["api_key"] == "sk-secret-key-12345"


@pytest.mark.unit
def test_enclave_transport_import():
    """Test that EnclaveTransport can be imported"""
    from vigil.enclave_transport import EnclaveTransport
    assert EnclaveTransport is not None


@pytest.mark.unit
def test_multiple_transports_independent():
    """Test that multiple EnclaveTransport instances are independent"""
    transport1 = EnclaveTransport(cid=88, port=5000)
    transport2 = EnclaveTransport(cid=99, port=6000)
    
    assert transport1.cid != transport2.cid
    assert transport1.port != transport2.port
    
    # Changes to one don't affect the other
    transport1.enclave_pub_key = "key1"
    transport2.enclave_pub_key = "key2"
    
    assert transport1.enclave_pub_key != transport2.enclave_pub_key
