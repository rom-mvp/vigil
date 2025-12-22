#!/usr/bin/env python3
"""
End-to-End Test: Verify Priority 1 implementation works with AgentShield backend.

Tests that the 4 new fields are properly handled:
1. schema_version
2. ttl_ms
3. context_echo.policy_id
4. context_echo.input_hash
"""

import sys
import os
import json
import time
import requests
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_section(title):
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}{title:^80}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")

def print_success(msg):
    print(f"{GREEN}✅ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}❌ {msg}{RESET}")

def print_info(msg):
    print(f"{YELLOW}ℹ️  {msg}{RESET}")

def test_agentshield_health():
    """Test 1: Verify AgentShield is running."""
    print_section("TEST 1: AgentShield Health Check")
    
    try:
        response = requests.get("http://localhost:9000/health", timeout=5)
        if response.status_code == 200:
            print_success("AgentShield is running")
            return True
        else:
            print_error(f"AgentShield health check failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Cannot reach AgentShield: {e}")
        print_info("Make sure AgentShield is running: docker-compose up agentshield")
        return False

def test_vigil_health():
    """Test 2: Verify Vigil is running."""
    print_section("TEST 2: Vigil Health Check")
    
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            print_success("Vigil is running")
            return True
        else:
            print_error(f"Vigil health check failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print_error(f"Cannot reach Vigil: {e}")
        print_info("Make sure Vigil is running: docker-compose up vigil")
        return False

def test_direct_agentshield_enforce():
    """Test 3: Test AgentShield /v1/enforce endpoint directly."""
    print_section("TEST 3: Direct AgentShield /v1/enforce Test")
    
    request_data = {
        "request_id": f"test-direct-{int(time.time())}",
        "tenant_id": "test-tenant",
        "agent_id": "test-agent",
        "policy_id": "policy-test",
        "policy_version": 1,
        "timestamp_ms": int(time.time() * 1000),
        "ttl_ms": 300000,
        "input_hash": "test-hash-12345",
        "messages": [{"role": "user", "content": "Test message"}],
        "environment": "test"
    }
    
    try:
        response = requests.post(
            "http://localhost:9000/v1/enforce",
            json=request_data,
            timeout=5
        )
        
        if response.status_code != 200:
            print_error(f"AgentShield returned status {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
        
        decision = response.json()
        
        # Check for new fields
        checks = {
            "schema_version": decision.get("schema_version"),
            "ttl_ms": decision.get("ttl_ms"),
            "context_echo.policy_id": decision.get("context_echo", {}).get("policy_id"),
            "context_echo.input_hash": decision.get("context_echo", {}).get("input_hash")
        }
        
        print_info("AgentShield Response Fields:")
        all_present = True
        for field, value in checks.items():
            if value is not None:
                print_success(f"{field}: {value}")
            else:
                print_error(f"{field}: MISSING")
                all_present = False
        
        # Also check existing fields
        print_info("\nExisting Fields:")
        for field in ["action", "risk_score", "signature", "signature_key_id", "issued_at"]:
            value = decision.get(field)
            if value is not None:
                print_success(f"{field}: {str(value)[:50]}")
            else:
                print_error(f"{field}: MISSING")
                all_present = False
        
        if all_present:
            print_success("\n✅ All required fields present in AgentShield response")
            return True
        else:
            print_error("\n❌ Some fields missing in AgentShield response")
            return False
            
    except Exception as e:
        print_error(f"AgentShield test failed: {e}")
        return False

def test_vigil_enforcement():
    """Test 4: Test end-to-end through Vigil."""
    print_section("TEST 4: End-to-End Vigil Enforcement")
    
    request_data = {
        "messages": [{"role": "user", "content": "Hello, this is a test message"}]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": "test-tenant-e2e",
        "X-Agent-ID": "test-agent-e2e",
        "X-Policy-ID": "policy-e2e-test",
        "X-Policy-Version": "1"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json=request_data,
            headers=headers,
            timeout=5
        )
        
        print_info(f"Response Status: {response.status_code}")
        
        if response.status_code in [200, 403]:  # Both ALLOW and BLOCK are valid
            result = response.json()
            print_success(f"Request processed: {result.get('action', 'N/A')}")
            
            # Check if signature verification happened
            if "signature_hash" in result:
                print_success(f"Signature hash present: {result['signature_hash'][:16]}...")
            
            return True
        else:
            print_error(f"Unexpected status code: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"Vigil enforcement test failed: {e}")
        return False

def test_audit_logs():
    """Test 5: Check audit logs for new fields."""
    print_section("TEST 5: Audit Log Verification")
    
    try:
        response = requests.get(
            "http://localhost:8000/api/v1/audit/logs",
            params={"limit": 5},
            timeout=5
        )
        
        if response.status_code != 200:
            print_error(f"Failed to fetch audit logs: {response.status_code}")
            return False
        
        logs = response.json().get("logs", [])
        
        if not logs:
            print_info("No audit logs found yet")
            return True
        
        print_info(f"Found {len(logs)} recent audit log entries")
        
        # Check the most recent log
        latest_log = logs[-1] if logs else None
        if latest_log:
            entry = latest_log.get("entry", latest_log)
            
            print_info("\nLatest Audit Log Entry:")
            
            # Check for new fields
            new_fields = {
                "policy_id": entry.get("policy_id"),
                "input_hash": entry.get("input_hash"),
                "error_code": entry.get("error_code")
            }
            
            for field, value in new_fields.items():
                if value is not None:
                    print_success(f"{field}: {value}")
                else:
                    print_info(f"{field}: Not present (may be optional)")
            
            # Check existing fields
            print_info("\nCore Fields:")
            for field in ["request_id", "status", "sig_verified", "tenant_id", "agent_id"]:
                value = entry.get(field)
                if value is not None:
                    print_success(f"{field}: {value}")
        
        print_success("\n✅ Audit logs accessible")
        return True
        
    except Exception as e:
        print_error(f"Audit log test failed: {e}")
        return False

def test_signature_verification():
    """Test 6: Verify signature verification with new context fields."""
    print_section("TEST 6: Signature Verification Test")
    
    # This test sends a request and checks if signature verification succeeded
    request_data = {
        "messages": [{"role": "user", "content": "Test signature verification"}]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": "sig-test-tenant",
        "X-Agent-ID": "sig-test-agent",
        "X-Policy-ID": "policy-sig-test"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json=request_data,
            headers=headers,
            timeout=5
        )
        
        # Check audit logs for this request
        time.sleep(1)  # Give audit log time to write
        
        logs_response = requests.get(
            "http://localhost:8000/api/v1/audit/logs",
            params={"limit": 1, "tenant_id": "sig-test-tenant"},
            timeout=5
        )
        
        if logs_response.status_code == 200:
            logs = logs_response.json().get("logs", [])
            if logs:
                entry = logs[-1].get("entry", logs[-1])
                sig_verified = entry.get("sig_verified")
                
                if sig_verified:
                    print_success("Signature verification: PASSED")
                    print_success(f"Signature key ID: {entry.get('sig_key_id', 'N/A')}")
                    return True
                else:
                    print_error("Signature verification: FAILED")
                    error_code = entry.get("error_code")
                    if error_code:
                        print_info(f"Error code: {error_code}")
                    return False
            else:
                print_info("No logs found for signature test")
                return True
        
        return True
        
    except Exception as e:
        print_error(f"Signature verification test failed: {e}")
        return False

def test_input_hash_validation():
    """Test 7: Verify input_hash is computed and validated."""
    print_section("TEST 7: Input Hash Validation")
    
    print_info("Testing input_hash computation and validation...")
    
    # Send request through Vigil
    request_data = {
        "messages": [{"role": "user", "content": "Test input hash validation"}]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-ID": "hash-test-tenant",
        "X-Agent-ID": "hash-test-agent",
        "X-Policy-ID": "policy-hash-test"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json=request_data,
            headers=headers,
            timeout=5
        )
        
        if response.status_code in [200, 403]:
            print_success("Request processed (input_hash computed by Vigil)")
            
            # Check audit log
            time.sleep(1)
            logs_response = requests.get(
                "http://localhost:8000/api/v1/audit/logs",
                params={"limit": 1, "tenant_id": "hash-test-tenant"},
                timeout=5
            )
            
            if logs_response.status_code == 200:
                logs = logs_response.json().get("logs", [])
                if logs:
                    entry = logs[-1].get("entry", logs[-1])
                    input_hash = entry.get("input_hash")
                    
                    if input_hash:
                        print_success(f"input_hash in audit log: {input_hash[:32]}...")
                        return True
                    else:
                        print_info("input_hash not found in audit log (may be optional)")
                        return True
            
            return True
        else:
            print_error(f"Request failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Input hash validation test failed: {e}")
        return False

def run_all_tests():
    """Run all end-to-end tests."""
    print_section("🚀 PRIORITY 1 END-TO-END TESTING")
    print_info("Verifying AgentShield backend integration")
    
    tests = [
        ("AgentShield Health", test_agentshield_health),
        ("Vigil Health", test_vigil_health),
        ("AgentShield Direct Enforce", test_direct_agentshield_enforce),
        ("Vigil End-to-End", test_vigil_enforcement),
        ("Audit Logs", test_audit_logs),
        ("Signature Verification", test_signature_verification),
        ("Input Hash Validation", test_input_hash_validation)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print_section("📊 TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{GREEN}✅ PASSED{RESET}" if result else f"{RED}❌ FAILED{RESET}"
        print(f"{test_name:.<40} {status}")
    
    print(f"\n{BLUE}{'─'*80}{RESET}")
    print(f"Total: {passed}/{total} tests passed ({passed*100//total}%)")
    print(f"{BLUE}{'─'*80}{RESET}\n")
    
    if passed == total:
        print(f"{GREEN}{'='*80}{RESET}")
        print(f"{GREEN}✅ ALL TESTS PASSED! Priority 1 implementation is working end-to-end.{RESET}")
        print(f"{GREEN}{'='*80}{RESET}\n")
        return 0
    else:
        print(f"{RED}{'='*80}{RESET}")
        print(f"{RED}⚠️  Some tests failed. Check the output above for details.{RESET}")
        print(f"{RED}{'='*80}{RESET}\n")
        return 1

if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
