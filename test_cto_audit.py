#!/usr/bin/env python3
"""
CTO Security Audit: Comprehensive White-Hat Attack Simulation
Tests policy enforcement, fail-closed behavior, tamper resistance, and audit integrity.
"""
import base64
import hashlib
import json
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Optional, Dict, List
import requests

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class AuditVerifier:
    """Verify Merkle chain integrity and detect tampering."""
    
    @staticmethod
    def verify_chain(logs: List[Dict]) -> Dict:
        """Verify Merkle chain continuity."""
        results = {
            "total": len(logs),
            "valid_links": 0,
            "broken_links": [],
            "missing_hashes": [],
            "valid": True
        }
        
        prev_hash = None
        for i, log in enumerate(logs):
            current_hash = log.get("hash")
            claimed_prev = log.get("prev_hash")
            
            if not current_hash:
                results["missing_hashes"].append(i)
                results["valid"] = False
                continue
            
            if i > 0 and claimed_prev != prev_hash:
                results["broken_links"].append({
                    "index": i,
                    "expected": prev_hash,
                    "actual": claimed_prev
                })
                results["valid"] = False
            else:
                results["valid_links"] += 1
            
            prev_hash = current_hash
        
        return results


class InstrumentedStub(BaseHTTPRequestHandler):
    """AgentShield stub with full instrumentation and attack scenario support."""
    
    ed25519_private_key: Optional[ed25519.Ed25519PrivateKey] = None
    call_log: List[Dict] = []
    
    def log_message(self, format, *args):
        pass
    
    def do_POST(self):
        # Only handle /v1/enforce
        if self.path != '/v1/enforce':
            self.send_response(404)
            self.end_headers()
            return
        
        start = time.time()
        
        length = int(self.headers.get('content-length', '0'))
        req_body = json.loads(self.rfile.read(length)) if length else {}
        
        # Extract test scenario and request ID
        scenario = self.headers.get('X-Test-Scenario', req_body.get('metadata', {}).get('scenario', 'normal'))
        request_id = req_body.get('request_id', str(uuid.uuid4()))
        
        # Log AgentShield call
        self.call_log.append({
            "request_id": request_id,
            "scenario": scenario,
            "timestamp": time.time(),
            "tenant_id": req_body.get("tenant_id"),
            "agent_id": req_body.get("agent_id")
        })
        
        # Route to scenario handler
        handler = getattr(self, f'_scenario_{scenario}', self._scenario_normal)
        handler(req_body, request_id, start)
    
    def _send_decision(self, decision: Dict, status=200):
        body = json.dumps(decision).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def _sign_decision(self, req: dict, decision: dict) -> dict:
        """Add signature, hash, and context_echo to decision."""
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
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        canonical_hash = hashlib.sha256(canonical).digest()
        
        if self.ed25519_private_key:
            signature = self.ed25519_private_key.sign(canonical_hash)
            decision["signature"] = base64.urlsafe_b64encode(signature).decode().rstrip("=")
            decision["signature_key_id"] = "test-ed25519"
            decision["canonical_payload_hash"] = base64.urlsafe_b64encode(canonical_hash).decode().rstrip("=")
        
        decision["context_echo"] = {
            "request_id": req.get("request_id"),
            "tenant_id": req.get("tenant_id"),
            "user_id": req.get("agent_id"),
            "policy_version": req.get("policy_version")
        }
        
        return decision
    
    # === A) Policy Enforcement Scenarios ===
    
    def _scenario_high_risk_override(self, req, request_id, start):
        """ALLOW but risk_score above policy max (0.80 > 0.30)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.85,  # Above threshold!
            "reasons": ["legitimate-pattern"],
            "signature_hash": f"hash_{request_id[:8]}",
            "audit_event_id": f"evt_{request_id[:8]}",
            "sanitized": []
        }
        self._send_decision(self._sign_decision(req, decision))
    
    def _scenario_disallowed_reason(self, req, request_id, start):
        """Low risk but contains disallowed reason."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.15,
            "reasons": ["credential-exfil", "normal-use"],  # Disallowed reason!
            "signature_hash": f"hash_{request_id[:8]}",
            "audit_event_id": f"evt_{request_id[:8]}",
            "sanitized": []
        }
        self._send_decision(self._sign_decision(req, decision))
    
    # === B) Fail-Closed Scenarios ===
    
    def _scenario_timeout(self, req, request_id, start):
        """Simulate timeout (delay > gateway timeout)."""
        time.sleep(10)
        decision = {"action": "ALLOW"}
        self._send_decision(decision)
    
    def _scenario_malformed_schema(self, req, request_id, start):
        """Missing required fields (audit_event_id, signature_hash)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["test"]
            # Missing audit_event_id and signature_hash!
        }
        self._send_decision(self._sign_decision(req, decision))
    
    # === C) Integrity & Tamper Resistance ===
    
    def _scenario_replay_attack(self, req, request_id, start):
        """Decision with mismatched request context (simulates replay)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["replay-attempt"],
            "signature_hash": f"hash_{request_id[:8]}",
            "audit_event_id": f"evt_{request_id[:8]}",
            "sanitized": []
        }
        # Sign with wrong request_id
        fake_req = req.copy()
        fake_req["request_id"] = "old_request_12345"
        self._send_decision(self._sign_decision(fake_req, decision))
    
    def _scenario_tenant_mismatch(self, req, request_id, start):
        """Decision for different tenant (cross-tenant attack)."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1,
            "reasons": ["tenant-confusion"],
            "signature_hash": f"hash_{request_id[:8]}",
            "audit_event_id": f"evt_{request_id[:8]}",
            "sanitized": []
        }
        signed = self._sign_decision(req, decision)
        # Override tenant in context_echo
        signed["context_echo"]["tenant_id"] = "attacker-tenant"
        self._send_decision(signed)
    
    # === D) Data Protection ===
    
    def _scenario_deny_no_leak(self, req, request_id, start):
        """DENY decision - verify no sensitive data in response."""
        decision = {
            "action": "BLOCK",
            "risk_score": 0.95,
            "reasons": ["malicious-pattern", "policy-violation"],
            "signature_hash": f"hash_{request_id[:8]}",
            "audit_event_id": f"evt_{request_id[:8]}",
            "sanitized": [],
            "sensitive_data_should_not_appear": "SECRET_MODEL_OUTPUT"
        }
        self._send_decision(self._sign_decision(req, decision))
    
    # === Normal ===
    
    def _scenario_normal(self, req, request_id, start):
        """Normal ALLOW with valid signature."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.12,
            "reasons": ["normal-traffic"],
            "signature_hash": f"hash_{request_id[:8]}",
            "audit_event_id": f"evt_{request_id[:8]}",
            "sanitized": []
        }
        self._send_decision(self._sign_decision(req, decision))


def run_scenario(scenario: str, description: str, tenant: str, agent: str, policy_ver: int, 
                 expect_status: int, expect_decision: str, expect_audit: bool) -> Dict:
    """Run a test scenario with full instrumentation."""
    request_id = str(uuid.uuid4())
    
    print(f"\n{'='*70}")
    print(f"SCENARIO: {scenario}")
    print(f"DESC: {description}")
    print(f"EXPECT: HTTP {expect_status}, decision={expect_decision}, audit={expect_audit}")
    
    start = time.time()
    timings = {}
    
    try:
        resp = requests.post(
            "http://127.0.0.1:8000/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"bearer-test-{scenario}",
                "X-Agent-ID": agent,
                "X-Tenant-ID": tenant,
                "X-Policy-Version": str(policy_ver),
                "X-Request-ID": request_id,
                "X-Test-Scenario": scenario
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": f"Test scenario: {scenario}"}],
                "metadata": {"scenario": scenario, "request_id": request_id, "test": True}
            },
            timeout=5
        )
        timings['total_ms'] = round((time.time() - start) * 1000, 2)
        
        # Check for sensitive data leakage
        body_text = resp.text
        has_leak = "SECRET_MODEL_OUTPUT" in body_text or "sensitive_data" in body_text.lower()
        
        result = {
            "scenario": scenario,
            "description": description,
            "request_id": request_id,
            "tenant_id": tenant,
            "agent_id": agent,
            "policy_version": policy_ver,
            "status": resp.status_code,
            "expected_status": expect_status,
            "expected_decision": expect_decision,
            "expected_audit": expect_audit,
            "timings": timings,
            "status_pass": resp.status_code == expect_status,
            "data_leak": has_leak,
            "body_sample": body_text[:200]
        }
        
        print(f"ACTUAL: HTTP {resp.status_code}")
        print(f"TIMING: {timings['total_ms']}ms total")
        print(f"DATA LEAK: {'❌ YES' if has_leak else '✅ NO'}")
        
        return result
    
    except requests.exceptions.Timeout:
        timings['total_ms'] = round((time.time() - start) * 1000, 2)
        result = {
            "scenario": scenario,
            "description": description,
            "request_id": request_id,
            "tenant_id": tenant,
            "agent_id": agent,
            "policy_version": policy_ver,
            "status": "TIMEOUT",
            "expected_status": expect_status,
            "expected_decision": expect_decision,
            "expected_audit": expect_audit,
            "timings": timings,
            "status_pass": expect_status == "TIMEOUT",
            "data_leak": False,
            "body_sample": "Request timed out"
        }
        print(f"ACTUAL: TIMEOUT after {timings['total_ms']}ms")
        return result
    
    except Exception as e:
        timings['total_ms'] = round((time.time() - start) * 1000, 2)
        result = {
            "scenario": scenario,
            "description": description,
            "request_id": request_id,
            "tenant_id": tenant,
            "agent_id": agent,
            "policy_version": policy_ver,
            "status": "ERROR",
            "expected_status": expect_status,
            "expected_decision": expect_decision,
            "expected_audit": expect_audit,
            "timings": timings,
            "status_pass": False,
            "data_leak": False,
            "body_sample": str(e)[:200]
        }
        print(f"ACTUAL: ERROR - {e}")
        return result


def verify_audit_presence(results: List[Dict], audit_logs: List[Dict]) -> List[Dict]:
    """Verify each scenario created exactly one audit entry."""
    for result in results:
        request_id = result['request_id']
        matching = [log for log in audit_logs if log.get('entry', {}).get('request_id') == request_id]
        result['audit_present'] = len(matching) > 0
        result['audit_count'] = len(matching)
        result['audit_pass'] = (len(matching) == 1) if result['expected_audit'] else (len(matching) == 0)
        
        if matching:
            entry = matching[0].get('entry', {})
            result['audit_decision'] = entry.get('status')
            result['audit_risk_score'] = entry.get('risk_score')
            result['audit_sig_verified'] = entry.get('sig_verified', False)
    
    return results


def generate_cto_report(results: List[Dict], audit_logs: List[Dict], merkle_check: Dict) -> Dict:
    """Generate comprehensive CTO security audit report."""
    
    total = len(results)
    status_passed = sum(1 for r in results if r['status_pass'])
    audit_passed = sum(1 for r in results if r.get('audit_pass', False))
    no_leaks = sum(1 for r in results if not r.get('data_leak', False))
    
    # Latency stats
    latencies = [r['timings']['total_ms'] for r in results if 'total_ms' in r['timings']]
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted)//2] if latencies else 0
    p95 = latencies_sorted[int(len(latencies_sorted)*0.95)] if latencies else 0
    p99 = latencies_sorted[int(len(latencies_sorted)*0.99)] if latencies else 0
    
    # Categorize results
    categories = {
        "policy_enforcement": [],
        "fail_closed": [],
        "integrity": [],
        "data_protection": [],
        "normal": []
    }
    
    for r in results:
        scenario = r['scenario']
        if 'high_risk' in scenario or 'disallowed' in scenario:
            categories['policy_enforcement'].append(r)
        elif 'timeout' in scenario or 'malformed' in scenario:
            categories['fail_closed'].append(r)
        elif 'replay' in scenario or 'mismatch' in scenario:
            categories['integrity'].append(r)
        elif 'deny_no_leak' in scenario:
            categories['data_protection'].append(r)
        else:
            categories['normal'].append(r)
    
    # Calculate pass rates per category
    category_scores = {}
    for cat, tests in categories.items():
        if tests:
            passed = sum(1 for t in tests if t['status_pass'] and t.get('audit_pass', True) and not t.get('data_leak', False))
            category_scores[cat] = {
                "total": len(tests),
                "passed": passed,
                "pass_rate": round(passed / len(tests) * 100, 1)
            }
    
    # Gap analysis
    gaps = []
    for r in results:
        if not r['status_pass']:
            gaps.append(f"{r['scenario']}: Expected {r['expected_status']}, got {r['status']}")
        if not r.get('audit_pass', True):
            gaps.append(f"{r['scenario']}: Audit entry issue (expected={r['expected_audit']}, count={r.get('audit_count', 0)})")
        if r.get('data_leak', False):
            gaps.append(f"{r['scenario']}: DATA LEAK DETECTED in response")
    
    return {
        "summary": {
            "total_scenarios": total,
            "status_passed": status_passed,
            "audit_passed": audit_passed,
            "no_data_leaks": no_leaks,
            "overall_pass_rate": round((status_passed + audit_passed + no_leaks) / (total * 3) * 100, 1)
        },
        "latency_slo": {
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0
        },
        "category_scores": category_scores,
        "merkle_integrity": merkle_check,
        "audit_log_count": len(audit_logs),
        "gaps_found": gaps,
        "critical_security_pass": all([
            no_leaks == total,  # No data leaks
            merkle_check.get('valid', False),  # Merkle chain valid
            category_scores.get('fail_closed', {}).get('pass_rate', 0) == 100  # Fail-closed works
        ])
    }


def main():
    print("🔒 CTO SECURITY AUDIT: Comprehensive White-Hat Testing")
    print("="*70)
    
    # Load keys
    print("\n1. Loading Ed25519 keypair...")
    with open('/tmp/test_ed25519_private.pem', 'rb') as f:
        ed25519_private = serialization.load_pem_private_key(f.read(), password=None)
    InstrumentedStub.ed25519_private_key = ed25519_private
    
    # Start instrumented stub
    print("2. Starting instrumented AgentShield stub...")
    server = HTTPServer(('127.0.0.1', 9000), InstrumentedStub)
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(1)
    
    print("3. Vigil gateway should be running with strict mode...")
    time.sleep(2)
    
    # Define comprehensive test scenarios
    print("\n4. Running comprehensive security scenarios...")
    scenarios = [
        # A) Policy Enforcement
        ("high_risk_override", "Risk score above policy max (0.85 > 0.30)", "tenant-a", "agent-1", 5, 403, "DENY", True),
        ("disallowed_reason", "Contains disallowed reason (credential-exfil)", "tenant-a", "agent-2", 5, 403, "DENY", True),
        
        # B) Fail-Closed
        ("timeout", "AgentShield timeout", "tenant-b", "agent-3", 5, 503, "ERROR", True),
        ("malformed_schema", "Missing required fields", "tenant-b", "agent-4", 5, 503, "ERROR", True),
        
        # C) Integrity & Tamper Resistance
        ("replay_attack", "Reused decision with wrong request_id", "tenant-c", "agent-5", 5, 503, "DENY", True),
        ("tenant_mismatch", "Cross-tenant decision replay", "tenant-c", "agent-6", 5, 503, "DENY", True),
        
        # D) Data Protection
        ("deny_no_leak", "DENY decision - check for leaks", "tenant-d", "agent-7", 5, 403, "DENY", True),
        
        # Normal
        ("normal", "Normal ALLOW flow", "tenant-e", "agent-8", 5, 200, "ALLOW", True),
    ]
    
    results = []
    for scenario, desc, tenant, agent, policy, exp_status, exp_decision, exp_audit in scenarios:
        result = run_scenario(scenario, desc, tenant, agent, policy, exp_status, exp_decision, exp_audit)
        results.append(result)
        time.sleep(0.5)
    
    # Fetch audit logs
    print("\n5. Fetching and verifying audit logs...")
    try:
        audit_resp = requests.get("http://127.0.0.1:8000/api/v1/audit/logs?limit=100", timeout=5)
        audit_logs = audit_resp.json().get('logs', [])
        print(f"   Retrieved {len(audit_logs)} audit entries")
    except Exception as e:
        print(f"   Failed to fetch audit logs: {e}")
        audit_logs = []
    
    # Verify audit presence
    print("6. Verifying audit trail...")
    results = verify_audit_presence(results, audit_logs)
    
    # Verify Merkle chain
    print("7. Verifying Merkle chain integrity...")
    merkle_check = AuditVerifier.verify_chain(audit_logs)
    print(f"   Chain valid: {merkle_check['valid']}")
    print(f"   Valid links: {merkle_check['valid_links']}/{merkle_check['total']}")
    
    # Generate CTO report
    print("\n8. Generating CTO security report...")
    report = generate_cto_report(results, audit_logs, merkle_check)
    
    # Save detailed report
    full_report = {
        "timestamp": time.time(),
        "test_results": results,
        "cto_report": report,
        "audit_logs": audit_logs,
        "merkle_verification": merkle_check,
        "agentshield_calls": InstrumentedStub.call_log
    }
    
    with open('/tmp/cto_security_audit_report.json', 'w') as f:
        json.dump(full_report, f, indent=2)
    
    print(f"\n✅ Full report saved to /tmp/cto_security_audit_report.json")
    
    # Print summary
    print("\n" + "="*70)
    print("CTO SECURITY AUDIT SUMMARY")
    print("="*70)
    print(f"\nOverall: {report['summary']['overall_pass_rate']}% pass rate")
    print(f"Status checks: {report['summary']['status_passed']}/{report['summary']['total_scenarios']}")
    print(f"Audit checks: {report['summary']['audit_passed']}/{report['summary']['total_scenarios']}")
    print(f"No data leaks: {report['summary']['no_data_leaks']}/{report['summary']['total_scenarios']}")
    
    print(f"\nLatency SLO:")
    print(f"  p50: {report['latency_slo']['p50_ms']}ms")
    print(f"  p95: {report['latency_slo']['p95_ms']}ms")
    print(f"  p99: {report['latency_slo']['p99_ms']}ms")
    
    print(f"\nMerkle Chain: {'✅ VALID' if merkle_check['valid'] else '❌ BROKEN'}")
    
    print(f"\nCritical Security: {'✅ PASS' if report['critical_security_pass'] else '❌ FAIL'}")
    
    if report['gaps_found']:
        print(f"\n⚠️  GAPS FOUND ({len(report['gaps_found'])}):")
        for gap in report['gaps_found'][:5]:
            print(f"  - {gap}")
    
    # Cleanup
    server.shutdown()
    print("\n9. Cleanup complete")
    
    return report['critical_security_pass']


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
