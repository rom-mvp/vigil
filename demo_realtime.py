#!/usr/bin/env python3
"""
Real-time Dashboard Demo
Updates the analytics endpoints with changing data so you can see live updates on the dashboard
"""
import time
import random
from datetime import datetime

# This will be imported by dashboard_server.py to provide dynamic data
class DemoDataGenerator:
    def __init__(self):
        self.total_requests = 15234
        self.blocked_attacks = 120
        self.redacted_events = 342
        self.total_classified = 1847
        self.jailbreak_count = 42
        self.exfiltration_count = 18
        self.coercion_count = 8
        self.total_scanned = 2340
        self.blocked_scans = 63
        self.poisoning_detected = 3
        self.sbom_failures = 10
        self.critical_alerts = 8
        self.high_alerts = 12
        
    def tick(self):
        """Simulate activity - increment counters randomly"""
        # Increment total requests
        self.total_requests += random.randint(5, 15)
        
        # Maybe block an attack (10% chance)
        if random.random() < 0.10:
            self.blocked_attacks += 1
            self.blocked_scans += 1
            
        # Maybe redact PII (15% chance)
        if random.random() < 0.15:
            self.redacted_events += 1
            
        # Classify prompts
        if random.random() < 0.8:
            self.total_classified += 1
            # Maybe detect threat
            if random.random() < 0.05:
                self.jailbreak_count += 1
                self.critical_alerts += random.randint(0, 1)
            elif random.random() < 0.03:
                self.exfiltration_count += 1
                self.high_alerts += random.randint(0, 1)
            elif random.random() < 0.02:
                self.coercion_count += 1
                
        # Scanner activity
        self.total_scanned += random.randint(3, 8)
        
        # Rare events
        if random.random() < 0.01:
            self.poisoning_detected += 1
            self.critical_alerts += 1
            
        if random.random() < 0.02:
            self.sbom_failures += 1
            self.high_alerts += 1
    
    def get_stats(self):
        return {
            "total_requests": self.total_requests,
            "blocked_attacks": self.blocked_attacks,
            "redacted_events": self.redacted_events,
            "cost_today": f"${self.total_requests * 0.001:.2f}",
            "budget_remaining": "Unlimited (Local)"
        }
    
    def get_classifier_data(self):
        return {
            "total_classified": self.total_classified,
            "breakdown": {
                "jailbreak": {
                    "count": self.jailbreak_count,
                    "percentage": round((self.jailbreak_count / max(self.total_classified, 1)) * 100, 1),
                    "trend": "+2.1%"
                },
                "exfiltration": {
                    "count": self.exfiltration_count,
                    "percentage": round((self.exfiltration_count / max(self.total_classified, 1)) * 100, 1),
                    "trend": "+0.5%"
                },
                "coercion": {
                    "count": self.coercion_count,
                    "percentage": round((self.coercion_count / max(self.total_classified, 1)) * 100, 1),
                    "trend": "-0.2%"
                }
            },
            "trends": {
                "hourly": [28, 31, 29, 35, 42, 38, 41, self.jailbreak_count % 50],
                "daily": [284, 301, 295, 318, 342, 329, self.jailbreak_count % 400]
            }
        }
    
    def get_scanner_data(self):
        pass_count = self.total_scanned - self.blocked_scans - int(self.total_scanned * 0.056)
        warn_count = int(self.total_scanned * 0.056)
        
        return {
            "total_scanned": self.total_scanned,
            "verdicts": {
                "PASS": {
                    "count": pass_count,
                    "percentage": round((pass_count / max(self.total_scanned, 1)) * 100, 1)
                },
                "WARN": {
                    "count": warn_count,
                    "percentage": round((warn_count / max(self.total_scanned, 1)) * 100, 1)
                },
                "BLOCK": {
                    "count": self.blocked_scans,
                    "percentage": round((self.blocked_scans / max(self.total_scanned, 1)) * 100, 1)
                }
            }
        }
    
    def get_threats_data(self):
        medium_alerts = random.randint(3, 7)
        low_alerts = random.randint(1, 4)
        total = self.critical_alerts + self.high_alerts + medium_alerts + low_alerts
        
        return {
            "total_alerts": total,
            "critical": self.critical_alerts,
            "high": self.high_alerts,
            "medium": medium_alerts,
            "low": low_alerts,
            "recent": [
                {
                    "id": f"ALERT-{random.randint(1000, 9999)}",
                    "severity": "CRITICAL",
                    "type": "High Confidence Jailbreak",
                    "timestamp": datetime.utcnow().isoformat(),
                    "classifier_score": 0.94,
                    "auto_remediation": "traffic_blocked"
                },
                {
                    "id": f"ALERT-{random.randint(1000, 9999)}",
                    "severity": "HIGH",
                    "type": "Data Exfiltration Attempt",
                    "timestamp": datetime.utcnow().isoformat(),
                    "classifier_score": 0.87,
                    "auto_remediation": "session_terminated"
                }
            ]
        }

# Global instance
_demo_data = DemoDataGenerator()

def get_demo_data():
    """Get the global demo data instance"""
    return _demo_data

def run_background_updater():
    """Background thread to update data"""
    print("🎬 Demo data generator started - dashboard will show live updates!")
    while True:
        time.sleep(2)  # Update every 2 seconds
        _demo_data.tick()
        print(f"📊 Requests: {_demo_data.total_requests} | Blocked: {_demo_data.blocked_attacks} | Classified: {_demo_data.total_classified}")

if __name__ == "__main__":
    run_background_updater()
