#!/usr/bin/env python3
"""
Integration Test: Vigil + AgentShield
Verifies end-to-end flow with actual services.
"""

import requests
import json
import time
import sys
from datetime import datetime

class IntegrationTester:
    def __init__(self, vigil_url="http://localhost:8000", agentshield_url="http://localhost:9000"):
        self.vigil_url = vigil_url
        self.agentshield_url = agentshield_url
        self.results = []
    
    def test_agentshield_endpoint(self):
        """Test AgentShield /v1/enforce is reachable and returns signed decision"""
        print("\n" + "="*60)
        print("TEST 1: AgentShield /v1/enforce endpoint")
        print("="*60)
        
        try:
            payload = {
                "request_id": "integration-test-001",
                "tenant_id": "test-tenant",
                "agent_id": "test-agent",
                "policy_version": "1.0.0",
                "environment": "test",
                "messages": [],
                "metadata": {}
            }
            
            resp = requests.post(
                f"{self.agentshield_url}/v1/enforce",
                json=payload,
                timeout=5
            )
            
            if resp.status_code != 200:
                print(f"❌ FAIL: Expected 200, got {resp.status_code}")
                print(f"Response: {resp.text}")
                self.results.append(("agentshield_endpoint", False, f"Status {resp.status_code}"))
                return False
            
            decision = resp.json()
            
            # Verify required fields
            required_fields = ["action", "risk_score", "signature", "signature_key_id", 
                             "canonical_payload_hash", "issued_at", "context_echo"]
            missing = [f for f in required_fields if f not in decision]
            
            if missing:
                print(f"❌ FAIL: Missing required fields: {missing}")
                print(f"Response: {json.dumps(decision, indent=2)}")
                self.results.append(("agentshield_endpoint", False, f"Missing fields: {missing}"))
                return False
            
            # Verify context_echo structure
            echo = decision.get("context_echo", {})
            echo_required = ["request_id", "tenant_id", "user_id", "policy_version"]
            echo_missing = [f for f in echo_required if f not in echo]
            
            if echo_missing:
                print(f"❌ FAIL: Missing context_echo fields: {echo_missing}")
                self.results.append(("agentshield_endpoint", False, f"Missing context_echo: {echo_missing}"))
                return False
            
            # Verify timestamp is recent
            issued_at = decision.get("issued_at", 0)
            age = time.time() - issued_at
            if age > 10:  # More than 10 seconds old
                print(f"❌ FAIL: Decision timestamp too old ({age:.1f}s)")
                self.results.append(("agentshield_endpoint", False, f"Timestamp age: {age}s"))
                return False
            
            print(f"✅ PASS")
            print(f"  Action: {decision['action']}")
            print(f"  Risk Score: {decision['risk_score']}")
            print(f"  Signature Key ID: {decision['signature_key_id']}")
            print(f"  Timestamp Age: {age:.2f}s")
            self.results.append(("agentshield_endpoint", True, "All fields present"))
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            self.results.append(("agentshield_endpoint", False, str(e)))
            return False
    
    def test_agentshield_jwks(self):
        """Test AgentShield /v1/keys/jwks returns valid key set"""
        print("\n" + "="*60)
        print("TEST 2: AgentShield /v1/keys/jwks endpoint")
        print("="*60)
        
        try:
            resp = requests.get(
                f"{self.agentshield_url}/v1/keys/jwks",
                timeout=5
            )
            
            if resp.status_code != 200:
                print(f"❌ FAIL: Expected 200, got {resp.status_code}")
                self.results.append(("agentshield_jwks", False, f"Status {resp.status_code}"))
                return False
            
            jwks = resp.json()
            keys = jwks.get("keys", [])
            
            if not keys:
                print(f"❌ FAIL: JWKS returned empty keys array")
                self.results.append(("agentshield_jwks", False, "No keys"))
                return False
            
            # Verify first key has required fields
            key = keys[0]
            key_required = ["kid", "kty", "x", "alg"]
            key_missing = [f for f in key_required if f not in key]
            
            if key_missing:
                print(f"❌ FAIL: Key missing fields: {key_missing}")
                self.results.append(("agentshield_jwks", False, f"Missing: {key_missing}"))
                return False
            
            if key["kty"] not in ["OKP", "RSA"]:
                print(f"❌ FAIL: Unsupported key type: {key['kty']}")
                self.results.append(("agentshield_jwks", False, f"Unsupported kty: {key['kty']}"))
                return False
            
            print(f"✅ PASS")
            print(f"  Keys Count: {len(keys)}")
            print(f"  First Key ID: {key['kid']}")
            print(f"  First Key Type: {key['kty']}")
            print(f"  Algorithm: {key['alg']}")
            self.results.append(("agentshield_jwks", True, f"{len(keys)} keys available"))
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            self.results.append(("agentshield_jwks", False, str(e)))
            return False
    
    def test_vigil_signature_verification(self):
        """Test Vigil calls AgentShield and verifies signature"""
        print("\n" + "="*60)
        print("TEST 3: Vigil signature verification")
        print("="*60)
        
        try:
            payload = {
                "request_id": "integration-test-002",
                "tenant_id": "test-tenant",
                "agent_id": "test-agent",
                "policy_version": "1.0.0",
                "environment": "test",
                "messages": [],
                "metadata": {}
            }
            
            resp = requests.post(
                f"{self.vigil_url}/api/v1/enforce",
                json=payload,
                timeout=5
            )
            
            if resp.status_code == 503:
                print(f"❌ FAIL: Vigil returned 503 (signature verification failed)")
                print(f"Response: {resp.text[:200]}")
                self.results.append(("vigil_signature_verification", False, "503 Service Unavailable"))
                return False
            
            if resp.status_code not in [200, 403]:
                print(f"❌ FAIL: Unexpected status {resp.status_code}")
                self.results.append(("vigil_signature_verification", False, f"Status {resp.status_code}"))
                return False
            
            result = resp.json()
            
            # Check if sig_verified is present
            if "sig_verified" not in result:
                print(f"❌ FAIL: Missing sig_verified field")
                self.results.append(("vigil_signature_verification", False, "Missing sig_verified"))
                return False
            
            sig_verified = result.get("sig_verified")
            if not sig_verified:
                print(f"❌ FAIL: Signature verification failed (sig_verified=false)")
                self.results.append(("vigil_signature_verification", False, "sig_verified=false"))
                return False
            
            print(f"✅ PASS")
            print(f"  Status: {resp.status_code}")
            print(f"  sig_verified: {sig_verified}")
            print(f"  Decision: {result.get('status', 'N/A')}")
            self.results.append(("vigil_signature_verification", True, "Signature verified"))
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            self.results.append(("vigil_signature_verification", False, str(e)))
            return False
    
    def test_vigil_audit_logging(self):
        """Test Vigil creates audit logs"""
        print("\n" + "="*60)
        print("TEST 4: Vigil audit logging")
        print("="*60)
        
        try:
            resp = requests.get(
                f"{self.vigil_url}/api/v1/audit/logs?limit=1",
                timeout=5
            )
            
            if resp.status_code != 200:
                print(f"❌ FAIL: Expected 200, got {resp.status_code}")
                self.results.append(("vigil_audit_logging", False, f"Status {resp.status_code}"))
                return False
            
            data = resp.json()
            logs = data.get("logs", [])
            
            if not logs:
                print(f"⚠️  WARNING: No audit logs found (may be expected if fresh start)")
                self.results.append(("vigil_audit_logging", True, "Audit log endpoint working"))
                return True
            
            log = logs[0]
            
            # Verify audit log has required fields
            audit_required = ["request_id", "status", "tenant_id", "risk_score", 
                            "sig_verified", "timings"]
            audit_missing = [f for f in audit_required if f not in log.get("entry", {})]
            
            if audit_missing:
                print(f"❌ FAIL: Audit log missing fields: {audit_missing}")
                self.results.append(("vigil_audit_logging", False, f"Missing: {audit_missing}"))
                return False
            
            entry = log["entry"]
            print(f"✅ PASS")
            print(f"  Last Log Status: {entry['status']}")
            print(f"  sig_verified: {entry['sig_verified']}")
            print(f"  risk_score: {entry['risk_score']}")
            print(f"  Latency: {entry['timings'].get('t_agentshield_ms', 'N/A')}ms")
            self.results.append(("vigil_audit_logging", True, "Audit logs working"))
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            self.results.append(("vigil_audit_logging", False, str(e)))
            return False
    
    def test_vigil_heartbeat(self):
        """Test Vigil heartbeat"""
        print("\n" + "="*60)
        print("TEST 5: Vigil heartbeat")
        print("="*60)
        
        try:
            resp = requests.get(
                f"{self.vigil_url}/api/heartbeat",
                timeout=5
            )
            
            if resp.status_code != 200:
                print(f"❌ FAIL: Expected 200, got {resp.status_code}")
                self.results.append(("vigil_heartbeat", False, f"Status {resp.status_code}"))
                return False
            
            data = resp.json()
            if data.get("status") != "ok":
                print(f"❌ FAIL: Status not 'ok'")
                self.results.append(("vigil_heartbeat", False, "Status not ok"))
                return False
            
            print(f"✅ PASS")
            print(f"  Status: {data['status']}")
            print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
            self.results.append(("vigil_heartbeat", True, "Heartbeat ok"))
            return True
            
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            self.results.append(("vigil_heartbeat", False, str(e)))
            return False
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, result, _ in self.results if result)
        total = len(self.results)
        
        for test_name, result, message in self.results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")
            print(f"     {message}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            print("\n🎉 All tests passed! System ready for integration.")
            return True
        else:
            print(f"\n⚠️  {total - passed} test(s) failed. Review above for details.")
            return False

if __name__ == "__main__":
    tester = IntegrationTester()
    
    print("Integration Testing: Vigil + AgentShield")
    print(f"Vigil URL: {tester.vigil_url}")
    print(f"AgentShield URL: {tester.agentshield_url}")
    print(f"Time: {datetime.now().isoformat()}")
    
    # Run all tests
    tester.test_agentshield_endpoint()
    tester.test_agentshield_jwks()
    tester.test_vigil_heartbeat()
    tester.test_vigil_signature_verification()
    tester.test_vigil_audit_logging()
    
    # Print summary
    success = tester.print_summary()
    sys.exit(0 if success else 1)
