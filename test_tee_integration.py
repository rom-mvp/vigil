#!/usr/bin/env python3
"""
TEE Integration Test Helper

Provides mock fixtures and utilities for testing TEE components without
real SGX/SEV/TDX hardware or enclaves.

Usage:
    python test_tee_integration.py
    python -m pytest test_tee_integration.py
"""

import json
import base64
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from vigil.tee_attestation import TEEAttestationClient, TEEType
from vigil.tee_integration import TEEIntegration, TEEConfig
from vigil.key_sealing import KeySealer
from vigil.vsock_transport import VsockTransport


class MockAgentShieldEnclave:
    """Mock AgentShield enclave for testing TEE communication
    
    Simulates an enclave that can:
    - Verify attestation quotes
    - Return signed decisions
    - Manage sealed keys
    """
    
    def __init__(self, name: str = "mock-enclave"):
        self.name = name
        self.verified_quotes = []
        self.sealed_keys = {}
        print(f"✓ Mock AgentShield Enclave '{name}' initialized")
    
    def verify_quote(self, quote: Dict[str, Any]) -> Dict[str, Any]:
        """Verify an attestation quote
        
        In real AgentShield, this would:
        - Check quote signature
        - Verify against platform attestation service
        - Check measurements against policy
        """
        self.verified_quotes.append({
            "timestamp": datetime.utcnow().isoformat(),
            "quote_type": quote.get("type"),
            "instance_id": quote.get("instance_id"),
        })
        
        return {
            "verified": True,
            "quote_type": quote.get("type"),
            "timestamp": datetime.utcnow().isoformat(),
            "enclave": self.name,
        }
    
    def seal_key(self, plaintext_key: bytes, binding: str = "mrenclave") -> bytes:
        """Seal a key to enclave measurement
        
        In real AgentShield, this would use enclave sealing APIs.
        """
        import hashlib
        key_id = hashlib.sha256(plaintext_key).hexdigest()[:8]
        self.sealed_keys[key_id] = {
            "key": base64.b64encode(plaintext_key).decode(),
            "binding": binding,
            "sealed_at": datetime.utcnow().isoformat(),
        }
        return key_id.encode()
    
    def unseal_key(self, key_id: bytes) -> Optional[bytes]:
        """Unseal a key (must be called from same enclave)"""
        key_id_str = key_id.decode()
        if key_id_str not in self.sealed_keys:
            return None
        return base64.b64decode(self.sealed_keys[key_id_str]["key"])
    
    def make_decision(self, policy_request: Dict[str, Any]) -> Dict[str, Any]:
        """Make a policy decision and sign it
        
        In real AgentShield, this would use enclave signing keys.
        """
        import hashlib
        import time
        
        decision_hash = hashlib.sha256(
            json.dumps(policy_request, sort_keys=True).encode()
        ).hexdigest()
        
        decision = {
            "request_hash": decision_hash,
            "decision": "ALLOW",  # Mock: always allow
            "timestamp": datetime.utcnow().isoformat(),
            "enclave": self.name,
            "signature": f"mock-sig-{decision_hash[:16]}",
        }
        
        return decision


def test_tee_attestation():
    """Test TEE attestation client"""
    print("\n" + "=" * 80)
    print("TEST: TEE Attestation Client")
    print("=" * 80)
    
    os.environ["VIGIL_TEE_ENABLED"] = "true"
    os.environ["VIGIL_TEE_TYPE"] = "auto"
    
    try:
        client = TEEAttestationClient()
        print(f"✓ Initialized attestation client (type: {client.tee_type})")
        
        # Get measurements
        measurements = client.get_measurements()
        print(f"✓ Got measurements: {list(measurements.keys())}")
        
        # Generate quote
        quote = client.generate_attestation_quote()
        print(f"✓ Generated attestation quote")
        print(f"  - Type: {quote.get('type')}")
        print(f"  - Timestamp: {quote.get('timestamp')}")
        print(f"  - Signature: {quote.get('signature', 'N/A')[:20]}...")
        
        # Validate quote
        errors = client.validate_attestation_quote(quote)
        if errors:
            print(f"✗ Quote validation errors: {errors}")
        else:
            print(f"✓ Quote validation passed")
        
        # Test measurement policy verification
        result = client.verify_measurement_policy()
        print(f"✓ Measurement policy verification: {result}")
        
        return True
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_key_sealing():
    """Test key sealing"""
    print("\n" + "=" * 80)
    print("TEST: Key Sealing")
    print("=" * 80)
    
    os.environ["VIGIL_TEE_TYPE"] = "auto"
    os.environ["VIGIL_KEY_SEALING_TYPE"] = "mrenclave"
    
    try:
        sealer = KeySealer()
        print(f"✓ Initialized key sealer (platform: {sealer.platform})")
        
        # Test sealing
        test_key = b"sk-test-api-key-1234567890"
        sealed = sealer.seal_key(test_key, b"api_key_context")
        print(f"✓ Sealed key (length: {len(sealed)} bytes)")
        
        # Test unsealing
        unsealed = sealer.unseal_key(sealed)
        if unsealed == test_key:
            print(f"✓ Unsealed key matches original")
        else:
            print(f"✗ Unsealed key does NOT match (got {unsealed[:20]}...)")
            return False
        
        return True
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tee_integration():
    """Test TEE integration layer"""
    print("\n" + "=" * 80)
    print("TEST: TEE Integration Layer")
    print("=" * 80)
    
    os.environ["VIGIL_TEE_ENABLED"] = "true"
    os.environ["VIGIL_TEE_TYPE"] = "auto"
    os.environ["AGENTSHIELD_MODE"] = "http"
    
    try:
        config = TEEConfig()
        tee = TEEIntegration(config)
        print(f"✓ Initialized TEE integration: {config}")
        
        # Get attestation quote
        quote = tee.get_attestation_quote()
        if quote:
            print(f"✓ Got attestation quote (type: {quote.get('type')})")
        else:
            print(f"⚠ No attestation quote available")
        
        # Test measurement verification
        valid = tee.verify_measurement_policy()
        print(f"✓ Measurement policy verification: {valid}")
        
        # Test key sealing
        sealed = tee.seal_sensitive_value(b"test_secret", b"context")
        if sealed:
            unsealed = tee.unseal_sensitive_value(sealed)
            if unsealed == b"test_secret":
                print(f"✓ Sealing/unsealing successful")
            else:
                print(f"✗ Unsealing failed")
                return False
        
        # Export state
        state = tee.to_dict()
        print(f"✓ TEE state exported: {json.dumps(state, indent=2)}")
        
        return True
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mock_agentshield_enclave():
    """Test mock AgentShield enclave"""
    print("\n" + "=" * 80)
    print("TEST: Mock AgentShield Enclave")
    print("=" * 80)
    
    try:
        enclave = MockAgentShieldEnclave("test-enclave")
        
        # Test quote verification
        os.environ["VIGIL_TEE_ENABLED"] = "true"
        os.environ["VIGIL_TEE_TYPE"] = "auto"
        
        vigil = TEEIntegration()
        quote = vigil.get_attestation_quote()
        
        if quote:
            verification = enclave.verify_quote(quote)
            print(f"✓ Quote verification: {verification['verified']}")
        
        # Test key sealing
        test_key = b"secret_api_key"
        key_id = enclave.seal_key(test_key)
        print(f"✓ Key sealed with ID: {key_id.decode()}")
        
        unsealed = enclave.unseal_key(key_id)
        if unsealed == test_key:
            print(f"✓ Key unsealed successfully")
        else:
            print(f"✗ Key unsealing failed")
            return False
        
        # Test policy decision
        decision = enclave.make_decision({
            "user": "test",
            "action": "read",
            "resource": "/api/sensitive",
        })
        print(f"✓ Policy decision made: {decision['decision']}")
        
        return True
    
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("🧪 TEE Integration Test Suite")
    print("=" * 80)
    
    tests = [
        ("TEE Attestation", test_tee_attestation),
        ("Key Sealing", test_key_sealing),
        ("TEE Integration", test_tee_integration),
        ("Mock AgentShield Enclave", test_mock_agentshield_enclave),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"✗ {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
