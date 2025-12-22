#!/usr/bin/env python3
"""
Negative path testing for Vigil gateway enforcement.
Tests DENY, CHALLENGE, malformed responses, timeouts, invalid signatures, etc.
"""
import base64
import json
import time
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ed25519
import requests


class TestStub(BaseHTTPRequestHandler):
    """Stub AgentShield that returns different responses based on test_case header."""
    
    # Class variables for keys
    rsa_private_key: Optional[rsa.RSAPrivateKey] = None
    ed25519_private_key: Optional[ed25519.Ed25519PrivateKey] = None
    
    def log_message(self, format, *args):
        pass  # Suppress logs
    
    def do_POST(self):
        test_case = self.headers.get('X-Test-Case', 'normal')
        length = int(self.headers.get('content-length', '0'))
        req_body = json.loads(self.rfile.read(length)) if length else {}
        
        # Route to test case handler
        handler = getattr(self, f'_handle_{test_case}', self._handle_normal)
        handler(req_body)
    
    def _send_json(self, data: dict, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def _sign_ed25519(self, payload: bytes) -> str:
        if not self.ed25519_private_key:
            return ""
        signature = self.ed25519_private_key.sign(payload)
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")
    
    def _canonical_payload(self, req: dict, decision: dict) -> bytes:
        payload = {
            "request_context": {
                "request_id": req.get("request_id"),
                "tenant_id": req.get("tenant_id"),
                "agent_id": req.get("agent_id"),
                "policy_version": req.get("policy_version"),
                "environment": req.get("environment"),
            },
            "decision": {
                "action": decision.get("action"),
                "risk_score": decision.get("risk_score"),
                "reasons": decision.get("reasons"),
                "audit_event_id": decision.get("audit_event_id"),
                "signature_hash": decision.get("signature_hash"),
                "sanitized": decision.get("sanitized"),
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    
    def _handle_normal(self, req):
        """Normal ALLOW with valid signature."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["normal-test"],
            "signature_hash": "hash_normal",
            "audit_event_id": "evt_normal",
            "sanitized": []
        }
        payload = self._canonical_payload(req, decision)
        payload_hash = hashlib.sha256(payload).digest()
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip("=")
        decision["signature"] = self._sign_ed25519(payload_hash)
        decision["signature_key_id"] = "test-ed25519"
        decision["context_echo"] = {
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_deny(self, req):
        """BLOCK/DENY decision with valid signature."""
        decision = {
            "action": "BLOCK",
            "risk_score": 0.95,
            "reasons": ["malicious-pattern-detected", "policy-violation"],
            "signature_hash": "hash_deny",
            "audit_event_id": "evt_deny",
            "sanitized": []
        }
        payload = self._canonical_payload(req, decision)
        payload_hash = hashlib.sha256(payload).digest()
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip("=")
        decision["signature"] = self._sign_ed25519(payload_hash)
        decision["signature_key_id"] = "test-ed25519"
        decision["context_echo"] = {
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_challenge(self, req):
        """CHALLENGE decision with valid signature."""
        decision = {
            "action": "CHALLENGE",
            "risk_score": 0.65,
            "reasons": ["requires-mfa", "anomalous-behavior"],
            "signature_hash": "hash_challenge",
            "audit_event_id": "evt_challenge",
            "sanitized": [],
            "challenge_type": "mfa"
        }
        payload = self._canonical_payload(req, decision)
        payload_hash = hashlib.sha256(payload).digest()
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip("=")
        decision["signature"] = self._sign_ed25519(payload_hash)
        decision["signature_key_id"] = "test-ed25519"
        decision["context_echo"] = {
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_malformed(self, req):
        """Malformed JSON response."""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"action": "ALLOW", invalid json')
    
    def _handle_timeout(self, req):
        """Simulate timeout by delaying response."""
        time.sleep(10)  # Gateway should timeout before this
        self._send_json({"action": "ALLOW"})
    
    def _handle_invalid_sig(self, req):
        """Valid structure but invalid signature."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["invalid-sig-test"],
            "signature_hash": "hash_invalid",
            "audit_event_id": "evt_invalid",
            "sanitized": []
        }
        payload = self._canonical_payload(req, decision)
        payload_hash = hashlib.sha256(payload).digest()
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip("=")
        # Wrong signature
        decision["signature"] = base64.urlsafe_b64encode(b"fake_signature_bytes_here_12345678901234567890123456789012").decode().rstrip("=")
        decision["signature_key_id"] = "test-ed25519"
        decision["context_echo"] = {
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_mismatched_hash(self, req):
        """Signature valid but for different payload (mismatched hash)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["mismatched-hash-test"],
            "signature_hash": "hash_mismatch",
            "audit_event_id": "evt_mismatch",
            "sanitized": []
        }
        # Sign one payload
        payload1 = self._canonical_payload(req, decision)
        payload_hash1 = hashlib.sha256(payload1).digest()
        signature = self._sign_ed25519(payload_hash1)
        
        # But modify decision after signing (risk_score tampering)
        decision["risk_score"] = 0.01  # Changed!
        payload2 = self._canonical_payload(req, decision)
        payload_hash2 = hashlib.sha256(payload2).digest()
        
        # Send mismatched hash and signature
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash2).decode().rstrip("=")
        decision["signature"] = signature  # Signature for payload1, but hash is payload2
        decision["signature_key_id"] = "test-ed25519"
        decision["context_echo"] = {
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_missing_audit_id(self, req):
        """Missing audit_event_id field."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["no-audit-id"],
            "signature_hash": "hash_no_audit",
            # audit_event_id missing!
            "sanitized": []
        }
        payload = self._canonical_payload(req, decision)
        payload_hash = hashlib.sha256(payload).digest()
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip("=")
        decision["signature"] = self._sign_ed25519(payload_hash)
        decision["signature_key_id"] = "test-ed25519"
        decision["context_echo"] = {
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_context_mismatch(self, req):
        """context_echo doesn't match request (cross-tenant attack simulation)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["context-mismatch-test"],
            "signature_hash": "hash_context",
            "audit_event_id": "evt_context",
            "sanitized": []
        }
        payload = self._canonical_payload(req, decision)
        payload_hash = hashlib.sha256(payload).digest()
        decision["canonical_payload_hash"] = base64.urlsafe_b64encode(payload_hash).decode().rstrip("=")
        decision["signature"] = self._sign_ed25519(payload_hash)
        decision["signature_key_id"] = "test-ed25519"
        # Wrong tenant!
        decision["context_echo"] = {
            "tenant_id": "attacker-tenant",  # Mismatch!
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        self._send_json(decision)
    
    def _handle_unsigned(self, req):
        """No signature or key_id (unsigned decision)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["unsigned-test"],
            "signature_hash": "hash_unsigned",
            "audit_event_id": "evt_unsigned",
            "sanitized": []
        }
        # No signature, no key_id, no canonical_payload_hash
        self._send_json(decision)


def run_test_case(case_name: str, description: str, expect_status: int) -> dict:
    """Run a single test case and return results."""
    print(f"\n{'='*60}")
    print(f"TEST: {case_name}")
    print(f"DESC: {description}")
    print(f"EXPECT: HTTP {expect_status}")
    
    start = time.time()
    try:
        resp = requests.post(
            "http://127.0.0.1:8000/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"bearer-test-{case_name}",
                "X-Agent-ID": f"test-agent-{case_name}",
                "X-Tenant-ID": "test-tenant",
                "X-Policy-Version": "5",
                "X-Test-Case": case_name
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": f"Test {case_name}"}],
                "metadata": {"test_case": case_name}
            },
            timeout=5
        )
        elapsed = time.time() - start
        
        result = {
            "case": case_name,
            "description": description,
            "status": resp.status_code,
            "expected": expect_status,
            "latency_ms": round(elapsed * 1000, 2),
            "passed": resp.status_code == expect_status,
            "body": resp.text[:500]
        }
        
        print(f"ACTUAL: HTTP {resp.status_code}")
        print(f"LATENCY: {result['latency_ms']} ms")
        print(f"RESULT: {'✅ PASS' if result['passed'] else '❌ FAIL'}")
        
        return result
    
    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        result = {
            "case": case_name,
            "description": description,
            "status": "TIMEOUT",
            "expected": expect_status,
            "latency_ms": round(elapsed * 1000, 2),
            "passed": expect_status == "TIMEOUT",
            "body": "Request timed out"
        }
        print(f"ACTUAL: TIMEOUT after {result['latency_ms']} ms")
        print(f"RESULT: {'✅ PASS' if result['passed'] else '❌ FAIL'}")
        return result
    
    except Exception as e:
        elapsed = time.time() - start
        result = {
            "case": case_name,
            "description": description,
            "status": "ERROR",
            "expected": expect_status,
            "latency_ms": round(elapsed * 1000, 2),
            "passed": False,
            "body": str(e)[:500]
        }
        print(f"ACTUAL: ERROR - {e}")
        print(f"RESULT: ❌ FAIL")
        return result


def generate_analytics(results: list, audit_logs: list):
    """Generate comprehensive analytics from test results."""
    print("\n" + "="*60)
    print("ANALYTICS SUMMARY")
    print("="*60)
    
    total = len(results)
    passed = sum(1 for r in results if r['passed'])
    failed = total - passed
    
    print(f"\nOverall: {passed}/{total} tests passed ({round(passed/total*100, 1)}%)")
    print(f"Failed: {failed}")
    
    # Latency stats
    latencies = [r['latency_ms'] for r in results if isinstance(r['latency_ms'], (int, float))]
    if latencies:
        print(f"\nLatency:")
        print(f"  Min: {min(latencies)} ms")
        print(f"  Max: {max(latencies)} ms")
        print(f"  Avg: {round(sum(latencies)/len(latencies), 2)} ms")
    
    # Status breakdown
    print(f"\nStatus Codes:")
    status_counts = {}
    for r in results:
        status = r['status']
        status_counts[status] = status_counts.get(status, 0) + 1
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    
    # Audit log summary
    print(f"\nAudit Logs: {len(audit_logs)} entries")
    if audit_logs:
        actions = {}
        verified = 0
        for log in audit_logs:
            entry = log.get('entry', {})
            action = entry.get('status', 'UNKNOWN')
            actions[action] = actions.get(action, 0) + 1
            if entry.get('sig_verified'):
                verified += 1
        
        print(f"  Signature verified: {verified}/{len(audit_logs)}")
        print(f"  Actions:")
        for action, count in sorted(actions.items()):
            print(f"    {action}: {count}")
    
    # Failed tests detail
    if failed > 0:
        print(f"\n❌ Failed Tests:")
        for r in results:
            if not r['passed']:
                print(f"  - {r['case']}: expected {r['expected']}, got {r['status']}")
    
    # Security findings
    print(f"\n🔒 Security Validation:")
    security_cases = ['invalid_sig', 'mismatched_hash', 'context_mismatch', 'unsigned']
    security_passed = sum(1 for r in results if r['case'] in security_cases and r['passed'])
    print(f"  {security_passed}/{len(security_cases)} security checks passed")
    
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed/total*100, 1),
        "latencies": latencies,
        "audit_log_count": len(audit_logs)
    }


def main():
    print("🛡️  Vigil Negative Path Testing Suite")
    print("="*60)
    
    # Load Ed25519 keypair
    print("\n1. Loading Ed25519 test keypair...")
    try:
        with open('/tmp/test_ed25519_private.pem', 'rb') as f:
            ed25519_private = serialization.load_pem_private_key(f.read(), password=None)
        print("   Using existing keypair from /tmp/test_ed25519_*.pem")
    except FileNotFoundError:
        print("   Generating new keypair...")
        ed25519_private = ed25519.Ed25519PrivateKey.generate()
        ed25519_public = ed25519_private.public_key()
        with open('/tmp/test_ed25519_public.pem', 'wb') as f:
            f.write(ed25519_public.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        with open('/tmp/test_ed25519_private.pem', 'wb') as f:
            f.write(ed25519_private.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
    
    TestStub.ed25519_private_key = ed25519_private
    
    # Start stub server
    print("2. Starting AgentShield test stub on port 9000...")
    server = HTTPServer(('127.0.0.1', 9000), TestStub)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(1)
    
    print("3. Starting Vigil gateway...")
    # Gateway should already be running with proper config
    time.sleep(2)
    
    # Define test cases
    test_cases = [
        ("normal", "Normal ALLOW with valid signature", 200),
        ("deny", "BLOCK/DENY decision", 403),
        ("challenge", "CHALLENGE decision", 200),  # Gateway may return 200 with challenge payload
        ("malformed", "Malformed JSON response", 503),
        ("timeout", "AgentShield timeout", "TIMEOUT"),
        ("invalid_sig", "Invalid signature bytes", 503),
        ("mismatched_hash", "Signature for different payload", 503),
        ("missing_audit_id", "Missing audit_event_id", 200),  # May still process but log warning
        ("context_mismatch", "context_echo tenant mismatch", 503),
        ("unsigned", "No signature or key_id", 503),
    ]
    
    print("\n4. Running test cases...")
    results = []
    for case, desc, expect in test_cases:
        result = run_test_case(case, desc, expect)
        results.append(result)
        time.sleep(0.5)
    
    # Fetch audit logs
    print("\n5. Fetching audit logs...")
    try:
        audit_resp = requests.get("http://127.0.0.1:8000/api/v1/audit/logs", timeout=5)
        audit_logs = audit_resp.json().get('logs', [])
        print(f"   Retrieved {len(audit_logs)} audit entries")
    except Exception as e:
        print(f"   Failed to fetch audit logs: {e}")
        audit_logs = []
    
    # Generate analytics
    print("\n6. Generating analytics...")
    analytics = generate_analytics(results, audit_logs)
    
    # Save detailed report
    report = {
        "timestamp": time.time(),
        "results": results,
        "analytics": analytics,
        "audit_logs": audit_logs
    }
    
    with open('/tmp/vigil_negative_test_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n✅ Full report saved to /tmp/vigil_negative_test_report.json")
    
    # Cleanup
    server.shutdown()
    print("\n7. Cleanup complete")
    
    return analytics['pass_rate'] >= 90


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
