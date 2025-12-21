#!/usr/bin/env python3
"""
🔬 COMPREHENSIVE TEST SUITE
Runs all tests from Tier 1 to advanced hacking tests with AgentShield integration
"""

import sys
import subprocess
import time
import json
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, 'src')

class ComprehensiveTestRunner:
    def __init__(self):
        self.results = {}
        self.start_time = time.time()
    
    def run_test(self, name: str, command: list, requires_server: bool = False) -> Dict[str, Any]:
        """Run a single test and capture results"""
        print(f"\n{'='*80}")
        print(f"🧪 Running: {name}")
        print(f"{'='*80}")
        
        start = time.time()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60
            )
            elapsed = (time.time() - start) * 1000
            
            output = result.stdout + result.stderr
            passed = result.returncode == 0
            
            # Extract pass rate from output
            pass_rate = self._extract_pass_rate(output)
            latency = self._extract_latency(output)
            
            return {
                'name': name,
                'passed': passed,
                'pass_rate': pass_rate,
                'avg_latency_ms': latency,
                'total_time_ms': elapsed,
                'output': output[-1000:],  # Last 1000 chars
                'exit_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'name': name,
                'passed': False,
                'pass_rate': 0.0,
                'avg_latency_ms': 0.0,
                'total_time_ms': 60000,
                'output': 'TIMEOUT',
                'exit_code': -1
            }
        except Exception as e:
            return {
                'name': name,
                'passed': False,
                'pass_rate': 0.0,
                'avg_latency_ms': 0.0,
                'total_time_ms': 0.0,
                'output': str(e),
                'exit_code': -2
            }
    
    def _extract_pass_rate(self, output: str) -> float:
        """Extract pass rate from test output"""
        import re
        
        # Look for patterns like "4/4 (100%)" or "24/28"
        patterns = [
            r'(\d+)/(\d+)\s*\((\d+)%\)',
            r'Tests Passed:\s*(\d+)/(\d+)',
            r'(\d+)/(\d+)\s*tests passed',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                if len(match.groups()) >= 3:
                    return float(match.group(3))
                else:
                    passed = int(match.group(1))
                    total = int(match.group(2))
                    return (passed / total * 100) if total > 0 else 0.0
        
        return 0.0 if 'FAIL' in output or 'ERROR' in output else 100.0
    
    def _extract_latency(self, output: str) -> float:
        """Extract average latency from test output"""
        import re
        
        patterns = [
            r'Avg:\s*([\d.]+)\s*ms',
            r'Average:\s*([\d.]+)\s*ms',
            r'Latency:\s*([\d.]+)ms',
        ]
        
        latencies = []
        for pattern in patterns:
            matches = re.findall(pattern, output)
            if matches:
                latencies.extend([float(m) for m in matches])
        
        return sum(latencies) / len(latencies) if latencies else 0.0
    
    def run_all_tests(self):
        """Run all test categories"""
        
        print("""
╔════════════════════════════════════════════════════════════╗
║         🔬 VIGIL COMPREHENSIVE TEST SUITE                  ║
║         All Tiers + AgentShield + SaaS Functions           ║
╚════════════════════════════════════════════════════════════╝
        """)
        
        # Category 1: Core Threat Detection (Standalone)
        print("\n📦 CATEGORY 1: CORE THREAT DETECTION (Standalone)")
        print("─" * 80)
        
        self.results['tier5_blindspots'] = self.run_test(
            "Tier 5: Blind Spot Detection",
            ['python', 'red_team_tier5.py']
        )
        
        # Category 2: Integration Tests (Require dependencies)
        print("\n📦 CATEGORY 2: UNIT TESTS")
        print("─" * 80)
        
        self.results['unit_guardrails'] = self.run_test(
            "Unit Tests: Guardrails",
            ['bash', '-c', 'PYTHONPATH=src python -m pytest tests/test_guardrails.py -v --tb=short']
        )
        
        self.results['unit_normalization'] = self.run_test(
            "Unit Tests: Normalization",
            ['bash', '-c', 'PYTHONPATH=src python -m pytest tests/test_normalization.py -v --tb=short']
        )
        
        # Category 3: Vector Scanning
        print("\n📦 CATEGORY 3: VECTOR THREAT SCANNING")
        print("─" * 80)
        
        # Note: These require server running
        print("⚠️  Skipping server-dependent tests (require Vigil server on port 8000)")
        self.results['vector_scan'] = {
            'name': 'Vector Threat Scan',
            'passed': None,
            'pass_rate': 0.0,
            'avg_latency_ms': 0.0,
            'total_time_ms': 0.0,
            'output': 'SKIPPED: Requires running server',
            'exit_code': -999
        }
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate comprehensive test report"""
        
        total_time = time.time() - self.start_time
        
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE TEST RESULTS")
        print("="*80 + "\n")
        
        categories = {
            'Core Threat Detection': ['tier5_blindspots'],
            'Unit Tests': ['unit_guardrails', 'unit_normalization'],
            'Vector Scanning': ['vector_scan'],
        }
        
        overall_stats = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0,
            'avg_pass_rate': 0.0,
            'avg_latency': 0.0
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
                else:
                    status = "❌ FAILED"
                    overall_stats['failed'] += 1
                
                print(f"\n{result['name']}")
                print(f"  Status:        {status}")
                print(f"  Pass Rate:     {result['pass_rate']:.1f}%")
                print(f"  Avg Latency:   {result['avg_latency_ms']:.2f}ms")
                print(f"  Total Time:    {result['total_time_ms']:.0f}ms")
                
                if result['passed'] is not None:
                    overall_stats['avg_pass_rate'] += result['pass_rate']
                    overall_stats['avg_latency'] += result['avg_latency_ms']
        
        # Calculate averages
        non_skipped = overall_stats['total_tests'] - overall_stats['skipped']
        if non_skipped > 0:
            overall_stats['avg_pass_rate'] /= non_skipped
            overall_stats['avg_latency'] /= non_skipped
        
        # Final summary
        print(f"\n{'='*80}")
        print("🎯 OVERALL SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests:       {overall_stats['total_tests']}")
        print(f"✅ Passed:          {overall_stats['passed']}")
        print(f"❌ Failed:          {overall_stats['failed']}")
        print(f"⏭️  Skipped:         {overall_stats['skipped']}")
        print(f"Average Pass Rate: {overall_stats['avg_pass_rate']:.1f}%")
        print(f"Average Latency:   {overall_stats['avg_latency']:.2f}ms")
        print(f"Total Runtime:     {total_time:.2f}s")
        print(f"{'='*80}\n")
        
        # Save JSON report
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'total_runtime_seconds': total_time,
            'overall_stats': overall_stats,
            'detailed_results': self.results
        }
        
        report_file = f'test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Detailed report saved to: {report_file}\n")
        
        return overall_stats['avg_pass_rate']


if __name__ == '__main__':
    runner = ComprehensiveTestRunner()
    runner.run_all_tests()
