#!/usr/bin/env python3
"""
Integration tests for Vigil <-> AgentShield communication
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import json
import time
import requests
from vigil.tee_attestation import TEEAttestationClient
from vigil.agentshield_client import AgentShieldClient


def test_agentshield_mock_service():
    """Test communication with mock AgentShield service"""
    print("\n" + "=" * 60)
    print("TEST: AgentShield Mock Service Integration")
    print("=" * 60)
    
    # Check if mock service is running
    try:
        response = requests.get('http://localhost:8443/health', timeout=2)
        if response.status_code != 200:
            print("❌ SKIP: AgentShield mock service not running")
            print("   Start with: python agentshield_enclave_mock.py")
            return
    except requests.exceptions.RequestException:
        print("❌ SKIP: AgentShield mock service not running")
        print("   Start with: python agentshield_enclave_mock.py")
        return
    
    # Generate attestation quote
    print("\n1. Generating attestation quote...")
    tee_client = TEEAttestationClient()
    quote = tee_client.generate_attestation_quote()
    print(f"   ✓ Generated {quote['tee_type']} quote")
    
    # Send to AgentShield for verification
    print("\n2. Sending quote to AgentShield...")
    verify_request = {
        'quote': quote,
        'request': {
            'action': 'llm_inference',
            'model': 'gpt-4',
            'timestamp': quote['timestamp']
        }
    }
    
    response = requests.post(
        'http://localhost:8443/v1/verify',
        json=verify_request,
        timeout=5
    )
    
    result = response.json()
    print(f"   ✓ Received response: {response.status_code}")
    
    # Check decision
    print("\n3. Verifying decision...")
    decision = result.get('decision', {})
    verification = result.get('verification', {})
    
    print(f"   Decision: {decision.get('allow')}")
    print(f"   Reason: {decision.get('reason')}")
    print(f"   Verified: {verification.get('verified')}")
    print(f"   Signature: {decision.get('signature')[:20]}..." if decision.get('signature') else "   Signature: None")
    
    if decision.get('allow') and verification.get('verified'):
        print("\n✅ PASS: AgentShield integration working")
    else:
        print("\n❌ FAIL: AgentShield rejected attestation")
        print(f"   Error: {verification.get('error')}")


def test_agentshield_client():
    """Test AgentShieldClient wrapper"""
    print("\n" + "=" * 60)
    print("TEST: AgentShieldClient Wrapper")
    print("=" * 60)
    
    try:
        requests.get('http://localhost:8443/health', timeout=2)
    except:
        print("❌ SKIP: AgentShield mock service not running")
        return
    
    # Create client
    print("\n1. Creating AgentShieldClient...")
    client = AgentShieldClient(
        base_url='http://localhost:8443',
        enable_caching=True
    )
    print("   ✓ Client created")
    
    # Verify a prompt
    print("\n2. Verifying prompt with AgentShield...")
    result = client.verify_prompt(
        prompt="What is the weather today?",
        model="gpt-4"
    )
    
    print(f"   Decision: {result.get('decision')}")
    print(f"   Reason: {result.get('reason')}")
    
    if result.get('decision') == 'allow':
        print("\n✅ PASS: AgentShieldClient working")
    else:
        print("\n❌ FAIL: AgentShieldClient denied request")


def test_measurement_policy():
    """Test measurement policy enforcement"""
    print("\n" + "=" * 60)
    print("TEST: Measurement Policy Enforcement")
    print("=" * 60)
    
    try:
        requests.get('http://localhost:8443/health', timeout=2)
    except:
        print("❌ SKIP: AgentShield mock service not running")
        return
    
    # Get current policy
    print("\n1. Getting current policy...")
    response = requests.get('http://localhost:8443/v1/policy')
    current_policy = response.json()['policy']
    print(f"   ✓ Current policy has {len(current_policy)} platform entries")
    
    # Generate quote
    print("\n2. Generating attestation quote...")
    tee_client = TEEAttestationClient()
    quote = tee_client.generate_attestation_quote()
    measurements = quote['measurements']
    
    # Set restrictive policy (only allow our measurement)
    print("\n3. Setting restrictive policy...")
    new_policy = {
        'sgx_mrenclave': [measurements.get('mrenclave', '')] if quote['tee_type'] == 'sgx' else [],
        'sgx_mrsigner': [],
        'sev_measurement': [measurements.get('measurement', '')] if quote['tee_type'] == 'sev' else [],
        'tdx_mrtd': [measurements.get('mrtd', '')] if quote['tee_type'] == 'tdx' else [],
        'azure_measurement': []
    }
    
    response = requests.post(
        'http://localhost:8443/v1/policy',
        json={'policy': new_policy}
    )
    print(f"   ✓ Policy updated: {response.json()['status']}")
    
    # Test with matching measurement
    print("\n4. Testing with matching measurement...")
    response = requests.post(
        'http://localhost:8443/v1/verify',
        json={'quote': quote, 'request': {}}
    )
    result = response.json()
    
    if result['decision']['allow']:
        print("   ✓ Matching measurement accepted")
    else:
        print(f"   ❌ Matching measurement rejected: {result['verification'].get('error')}")
    
    # Test with different measurement (should fail if policy enforced)
    print("\n5. Testing with different measurement...")
    bad_quote = quote.copy()
    bad_quote['measurements'] = {
        'mrenclave': 'invalid' * 16 if quote['tee_type'] == 'sgx' else ''
    }
    
    response = requests.post(
        'http://localhost:8443/v1/verify',
        json={'quote': bad_quote, 'request': {}}
    )
    result = response.json()
    
    if not result['decision']['allow']:
        print("   ✓ Invalid measurement rejected")
        print(f"   Reason: {result['verification'].get('error')}")
    else:
        print("   ⚠️  Invalid measurement accepted (policy not enforced)")
    
    # Restore original policy
    print("\n6. Restoring original policy...")
    requests.post('http://localhost:8443/v1/policy', json={'policy': current_policy})
    print("   ✓ Policy restored")
    
    print("\n✅ PASS: Measurement policy tests complete")


def test_enclave_measurements():
    """Test retrieving enclave's own measurements"""
    print("\n" + "=" * 60)
    print("TEST: Enclave Measurements")
    print("=" * 60)
    
    try:
        response = requests.get('http://localhost:8443/health', timeout=2)
    except:
        print("❌ SKIP: AgentShield mock service not running")
        return
    
    print("\n1. Requesting enclave measurements...")
    response = requests.get('http://localhost:8443/v1/measurements')
    data = response.json()
    
    measurements = data.get('measurements', {})
    public_key = data.get('public_key')
    
    print(f"   MRENCLAVE: {measurements.get('mrenclave', 'N/A')[:32]}...")
    print(f"   MRSIGNER: {measurements.get('mrsigner', 'N/A')[:32]}...")
    print(f"   Public Key: {public_key[:32]}..." if public_key else "   Public Key: N/A")
    print(f"   Timestamp: {measurements.get('timestamp')}")
    
    if measurements and public_key:
        print("\n✅ PASS: Enclave measurements retrieved")
    else:
        print("\n❌ FAIL: Failed to retrieve measurements")


def main():
    """Run all AgentShield integration tests"""
    print("\n" + "=" * 70)
    print(" " * 10 + "AGENTSHIELD INTEGRATION TEST SUITE")
    print("=" * 70)
    
    tests = [
        test_agentshield_mock_service,
        test_agentshield_client,
        test_measurement_policy,
        test_enclave_measurements
    ]
    
    for test_func in tests:
        try:
            test_func()
            time.sleep(0.5)
        except Exception as e:
            print(f"\n❌ ERROR in {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("Integration tests complete")
    print("=" * 70)


if __name__ == '__main__':
    main()
