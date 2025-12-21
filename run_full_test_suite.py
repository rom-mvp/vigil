#!/usr/bin/env python3
"""
🔬 FULL COMPREHENSIVE TEST SUITE
Includes server startup, AgentShield integration, and all security tiers
"""

import sys
import subprocess
import time
import json
import os
import signal
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, 'src')

class FullTestRunner:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
        self.server_process = None
        self.api_key = None
    
    def start_server(self) -> bool:
        """Start Vigil server in background"""
        print("\n🚀 Starting Vigil server...")
        
        try:
            # Kill any existing server
            subprocess.run(['pkill', '-f', 'vigil_enhanced_server.py'], 
                         capture_output=True)
            time.sleep(2)
            
            # Start new server
            self.server_process = subprocess.Popen(
                ['python', 'vigil_enhanced_server.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for server to be ready
            print("   Waiting for server to be ready...", end='', flush=True)
            for i in range(30):
                time.sleep(1)
                try:
                    result = subprocess.run(
                        ['curl', '-s', 'http://localhost:8000/health'],
                        capture_output=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        print(" ✅ Ready!")
                        return True
                except:
                    pass
                print(".", end='', flush=True)
            
            print(" ❌ Timeout")
            return False
            
        except Exception as e:
            print(f" ❌ Failed: {e}")
            return False
    
    def stop_server(self):
        """Stop Vigil server"""
        if self.server_process:
            print("\n🛑 Stopping Vigil server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except:
                self.server_process.kill()
        
        subprocess.run(['pkill', '-f', 'vigil_enhanced_server.py'], 
                      capture_output=True)
    
    def get_api_key(self) -> Optional[str]:
        """Get or generate API key"""
        
        # Check if api_keys.json exists
        if os.path.exists('api_keys.json'):
            try:
                with open('api_keys.json') as f:
                    data = json.load(f)
                    if data.get('keys'):
                        key = list(data['keys'].keys())[0]
                        print(f"   Using existing API key: {key[:20]}...")
                        return key
            except:
                pass
        
        # Generate new key
        print("   Generating new API key...")
        result = subprocess.run(
            ['python', '-c', '''
import secrets
import hashlib
import json

api_key = "sk-vigil-" + secrets.token_hex(32)
key_hash = hashlib.sha256(api_key.encode()).hexdigest()

data = {
    "keys": {
        api_key: {
            "hash": key_hash,
            "username": "test",
            "description": "auto-generated",
            "created_at": "2025-12-21"
        }
    }
}

with open("api_keys.json", "w") as f:
    json.dump(data, f, indent=2)

print(api_key)
'''],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            key = result.stdout.strip()
            print(f"   Generated: {key[:20]}...")
            return key
        
        return None
    
    def run_test(self, name: str, command: list, env: Dict[str, str] = None, 
                 timeout: int = 60) -> Dict[str, Any]:
        """Run a single test and capture results"""
        print(f"\n{'='*80}")
        print(f"🧪 {name}")
        print(f"{'='*80}")
        
        start = time.time()
        try:
            test_env = os.environ.copy()
            if env:
                test_env.update(env)
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=test_env
            )
            elapsed = (time.time() - start) * 1000
            
            output = result.stdout + result.stderr
            passed = result.returncode == 0
            
            # Extract metrics
            pass_rate = self._extract_pass_rate(output)
            latency = self._extract_latency(output)
            test_count = self._extract_test_count(output)
            
            # Print summary
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"\n   Status: {status}")
            if test_count:
                print(f"   Tests: {test_count}")
            print(f"   Pass Rate: {pass_rate:.1f}%")
            if latency > 0:
                print(f"   Avg Latency: {latency:.2f}ms")
            print(f"   Runtime: {elapsed:.0f}ms")
            
            return {
                'name': name,
                'passed': passed,
                'pass_rate': pass_rate,
                'avg_latency_ms': latency,
                'total_time_ms': elapsed,
                'test_count': test_count,
                'output_sample': output[-500:],
                'exit_code': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            elapsed = timeout * 1000
            print(f"\n   Status: ⏱️  TIMEOUT ({timeout}s)")
            return {
                'name': name,
                'passed': False,
                'pass_rate': 0.0,
                'avg_latency_ms': 0.0,
                'total_time_ms': elapsed,
                'test_count': None,
                'output_sample': 'TEST TIMEOUT',
                'exit_code': -1
            }
        except Exception as e:
            print(f"\n   Status: ❌ ERROR - {e}")
            return {
                'name': name,
                'passed': False,
                'pass_rate': 0.0,
                'avg_latency_ms': 0.0,
                'total_time_ms': 0.0,
                'test_count': None,
                'output_sample': str(e),
                'exit_code': -2
            }
    
    def _extract_test_count(self, output: str) -> Optional[str]:
        """Extract test count from output"""
        import re
        patterns = [
            r'(\d+)/(\d+)\s*tests',
            r'Tests Passed:\s*(\d+)/(\d+)',
            r'(\d+)/(\d+)\s*\(',
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return f"{match.group(1)}/{match.group(2)}"
        return None
    
    def _extract_pass_rate(self, output: str) -> float:
        """Extract pass rate percentage"""
        import re
        patterns = [
            r'(\d+)/(\d+)\s*\((\d+)%\)',
            r'Tests Passed:\s*(\d+)/(\d+)',
            r'(\d+)/(\d+)\s*tests passed',
            r'passed.*?(\d+)%',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 3:
                    return float(groups[2])
                elif len(groups) >= 2:
                    try:
                        passed = int(groups[0])
                        total = int(groups[1])
                        return (passed / total * 100) if total > 0 else 0.0
                    except:
                        pass
        
        # Check for explicit pass/fail indicators
        if 'All tests passed' in output or 'PASSED' in output:
            return 100.0
        if 'FAILED' in output or 'ERROR' in output:
            return 0.0
        
        return 50.0  # Unknown
    
    def _extract_latency(self, output: str) -> float:
        """Extract average latency"""
        import re
        patterns = [
            r'Avg[^:]*:\s*([\d.]+)\s*ms',
            r'Average[^:]*:\s*([\d.]+)\s*ms',
            r'Latency[^:]*:\s*([\d.]+)ms',
            r'([\d.]+)ms',
        ]
        
        latencies = []
        for pattern in patterns:
            matches = re.findall(pattern, output)
            if matches:
                for m in matches:
                    try:
                        val = float(m)
                        if 0.01 <= val <= 10000:  # Reasonable range
                            latencies.append(val)
                    except:
                        pass
        
        return sum(latencies) / len(latencies) if latencies else 0.0
    
    def run_all_tests(self):
        """Run complete test suite"""
        
        print("""
╔════════════════════════════════════════════════════════════╗
║       🔬 VIGIL FULL COMPREHENSIVE TEST SUITE              ║
║       All Tiers + AgentShield + Server Integration        ║
╚════════════════════════════════════════════════════════════╝
        """)
        
        # Phase 1: Standalone Tests (No Server Required)
        print("\n" + "="*80)
        print("📦 PHASE 1: STANDALONE TESTS (No Server Required)")
        print("="*80)
        
        self.results['tier5_blindspots'] = self.run_test(
            "Tier 5: Blind Spot Detection (Visual, Semantic, ReDoS, Indirect)",
            ['python', 'red_team_tier5.py']
        )
        
        self.results['unit_guardrails'] = self.run_test(
            "Unit Tests: Guardrails Module",
            ['bash', '-c', 'PYTHONPATH=src python -m pytest tests/test_guardrails.py -v --tb=short']
        )
        
        self.results['unit_normalization'] = self.run_test(
            "Unit Tests: Text Normalization",
            ['bash', '-c', 'PYTHONPATH=src python -m pytest tests/test_normalization.py -v --tb=short']
        )
        
        # Phase 2: Server-Based Tests
        print("\n" + "="*80)
        print("📦 PHASE 2: SERVER-BASED INTEGRATION TESTS")
        print("="*80)
        
        # Start server
        server_started = self.start_server()
        
        if server_started:
            # Get API key
            self.api_key = self.get_api_key()
            
            if self.api_key:
                env = {'VIGIL_API_KEY': self.api_key}
                
                self.results['red_team_attack'] = self.run_test(
                    "Red Team: Basic Attack Vectors (Tier 1-3)",
                    ['python', 'red_team_attack.py'],
                    env=env,
                    timeout=120
                )
                
                self.results['red_team_tier4'] = self.run_test(
                    "Red Team: Advanced Fragmentation (Tier 4)",
                    ['python', 'red_team_tier4.py'],
                    env=env,
                    timeout=120
                )
                
                self.results['vector_scan'] = self.run_test(
                    "Vector Threat Scanning",
                    ['python', 'test_vector_scan.py'],
                    timeout=60
                )
            else:
                print("⚠️  Skipping API key tests - failed to generate key")
                self.results['red_team_attack'] = self._skipped_result("Red Team Attack")
                self.results['red_team_tier4'] = self._skipped_result("Red Team Tier 4")
                self.results['vector_scan'] = self._skipped_result("Vector Scan")
        else:
            print("⚠️  Skipping server tests - failed to start server")
            self.results['red_team_attack'] = self._skipped_result("Red Team Attack")
            self.results['red_team_tier4'] = self._skipped_result("Red Team Tier 4")
            self.results['vector_scan'] = self._skipped_result("Vector Scan")
        
        # Stop server
        if server_started:
            self.stop_server()
        
        # Generate final report
        self.generate_report()
    
    def _skipped_result(self, name: str) -> Dict[str, Any]:
        """Create skipped result"""
        return {
            'name': name,
            'passed': None,
            'pass_rate': 0.0,
            'avg_latency_ms': 0.0,
            'total_time_ms': 0.0,
            'test_count': None,
            'output_sample': 'SKIPPED',
            'exit_code': -999
        }
    
    def generate_report(self):
        """Generate comprehensive test report"""
        
        total_time = time.time() - self.start_time
        
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("="*80)
        
        categories = {
            'Core Threat Detection (Standalone)': ['tier5_blindspots'],
            'Unit Tests': ['unit_guardrails', 'unit_normalization'],
            'Red Team Attacks (Server)': ['red_team_attack', 'red_team_tier4'],
            'Vector Scanning (Server)': ['vector_scan'],
        }
        
        overall_stats = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'total_pass_rate': 0.0,
            'total_latency': 0.0,
            'count_for_avg': 0
        }
        
        for category, test_keys in categories.items():
            print(f"\n{'─'*80}")
            print(f"📂 {category}")
            print(f"{'─'*80}")
            
            for key in test_keys:
                if key not in self.results:
                    continue
                
                result = self.results[key]
                overall_stats['total_tests'] += 1
                
                if result['passed'] is None:
                    status = "⏭️  SKIPPED"
                    overall_stats['skipped'] += 1
                elif result['passed']:
                    status = "✅ PASSED"
                    overall_stats['passed'] += 1
                    overall_stats['total_pass_rate'] += result['pass_rate']
                    overall_stats['total_latency'] += result['avg_latency_ms']
                    overall_stats['count_for_avg'] += 1
                else:
                    status = "❌ FAILED"
                    overall_stats['failed'] += 1
                    overall_stats['count_for_avg'] += 1
                
                print(f"\n  {result['name']}")
                print(f"    Status:       {status}")
                if result['test_count']:
                    print(f"    Tests:        {result['test_count']}")
                print(f"    Pass Rate:    {result['pass_rate']:.1f}%")
                if result['avg_latency_ms'] > 0:
                    print(f"    Avg Latency:  {result['avg_latency_ms']:.2f}ms")
                print(f"    Runtime:      {result['total_time_ms']:.0f}ms")
        
        # Calculate averages
        if overall_stats['count_for_avg'] > 0:
            avg_pass_rate = overall_stats['total_pass_rate'] / overall_stats['count_for_avg']
            avg_latency = overall_stats['total_latency'] / overall_stats['count_for_avg']
        else:
            avg_pass_rate = 0.0
            avg_latency = 0.0
        
        # Final summary
        print(f"\n{'='*80}")
        print("🎯 OVERALL SUMMARY")
        print(f"{'='*80}")
        print(f"Total Test Categories:  {overall_stats['total_tests']}")
        print(f"✅ Passed:               {overall_stats['passed']}")
        print(f"❌ Failed:               {overall_stats['failed']}")
        print(f"⏭️  Skipped:              {overall_stats['skipped']}")
        print(f"\n📈 METRICS:")
        print(f"Average Pass Rate:      {avg_pass_rate:.1f}%")
        print(f"Average Latency:        {avg_latency:.2f}ms")
        print(f"Total Runtime:          {total_time:.2f}s")
        print(f"{'='*80}\n")
        
        # Save JSON report
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_runtime_seconds': total_time,
            'overall_stats': {
                'total_tests': overall_stats['total_tests'],
                'passed': overall_stats['passed'],
                'failed': overall_stats['failed'],
                'skipped': overall_stats['skipped'],
                'avg_pass_rate': avg_pass_rate,
                'avg_latency_ms': avg_latency
            },
            'detailed_results': self.results
        }
        
        report_file = f'comprehensive_test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Detailed JSON report: {report_file}\n")
        
        return avg_pass_rate


if __name__ == '__main__':
    runner = FullTestRunner()
    try:
        runner.run_all_tests()
    finally:
        runner.stop_server()
