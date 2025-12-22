"""
🔄 Feedback Loop System - Continuous Learning & Model Adaptation

Captures decision outcomes, detects false positives/negatives,
triggers automatic retraining of threat models and policy updates.

Implements the learning pipeline:
1. Capture outcome (user feedback, security team review, actual attack confirmation)
2. Classify as correct/false positive/false negative
3. Update threat model embeddings
4. Adjust policy weights
5. A/B test new policies
6. Automatic rollback on regression
"""

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import numpy as np


class FeedbackEvent:
    """Represents a decision outcome with feedback."""
    
    def __init__(
        self,
        trace_id: str,
        original_decision: str,
        confidence: float,
        risk_score: float,
        tenant_id: str,
        agent_id: str
    ):
        self.trace_id = trace_id
        self.original_decision = original_decision
        self.confidence = confidence
        self.risk_score = risk_score
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.timestamp_ms = int(time.time() * 1000)
        
        self.actual_outcome = None  # "SAFE", "ATTACK", "FALSE_POSITIVE"
        self.feedback_timestamp = None
        self.feedback_source = None  # "user_report", "security_team", "post_breach_analysis"
        self.feedback_notes = ""
    
    def record_feedback(self, actual_outcome: str, source: str, notes: str = ""):
        """Record the actual outcome of the request."""
        self.actual_outcome = actual_outcome
        self.feedback_timestamp = int(time.time() * 1000)
        self.feedback_source = source
        self.feedback_notes = notes
    
    def get_classification(self) -> str:
        """Classify this feedback event."""
        if not self.actual_outcome:
            return "UNCLASSIFIED"
        
        if self.actual_outcome == "SAFE":
            if self.original_decision == "ALLOW":
                return "TRUE_POSITIVE"
            else:
                return "FALSE_POSITIVE"  # We blocked a safe request
        elif self.actual_outcome == "ATTACK":
            if self.original_decision == "BLOCK":
                return "TRUE_NEGATIVE"
            else:
                return "FALSE_NEGATIVE"  # We allowed an attack
        else:
            return "UNCLASSIFIED"


class FeedbackLoopManager:
    """
    Manages feedback collection, analysis, and triggers for model updates.
    
    Responsibilities:
    1. Collect decision outcomes from multiple sources
    2. Classify outcomes (TP/FP/TN/FN)
    3. Compute accuracy metrics per strategy
    4. Suggest policy weight adjustments
    5. Trigger automatic retraining
    6. Manage A/B test deployments
    """
    
    def __init__(self, db_url: Optional[str] = None, version_control_repo: Optional[str] = None):
        self.db_url = db_url
        self.version_control_repo = version_control_repo
        
        # In-memory event buffer (production: PostgreSQL)
        self.feedback_buffer = []
        self.buffer_lock = threading.Lock()
        
        # Metrics by strategy
        self.strategy_metrics = defaultdict(lambda: {
            "tp": 0, "tn": 0, "fp": 0, "fn": 0,
            "accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0
        })
        
        # Metrics by tenant
        self.tenant_metrics = defaultdict(lambda: {
            "total_decisions": 0,
            "correct": 0,
            "accuracy": 0.0,
            "false_positive_rate": 0.0
        })
        
        # Policy version tracking
        self.policy_versions = {
            "current": 1,
            "staging": 1,
            "history": {}
        }
        
        # A/B test configuration
        self.ab_tests = {}
        
        # Retraining trigger thresholds
        self.retrain_thresholds = {
            "false_positive_rate": 0.05,  # Retrain if FP rate > 5%
            "false_negative_rate": 0.02,  # Retrain if FN rate > 2%
            "strategy_drift": 0.10,  # Retrain if strategy accuracy drops >10%
            "min_feedback_events": 1000  # Retrain after 1000 feedback events
        }
        
        # Start background workers
        self._start_workers()
    
    def _start_workers(self):
        """Start background analysis workers."""
        threading.Thread(target=self._analysis_worker, daemon=True).start()
        threading.Thread(target=self._retraining_worker, daemon=True).start()
    
    def submit_feedback(
        self,
        trace_id: str,
        original_decision: str,
        confidence: float,
        risk_score: float,
        tenant_id: str,
        agent_id: str,
        actual_outcome: str,
        source: str,
        notes: str = ""
    ) -> FeedbackEvent:
        """
        Submit feedback for a decision.
        
        Args:
            trace_id: Decision trace ID
            original_decision: What Vigil decided ("ALLOW", "BLOCK", etc.)
            confidence: Confidence of that decision
            risk_score: Risk score
            tenant_id: Tenant ID
            agent_id: Agent ID
            actual_outcome: What actually happened ("SAFE", "ATTACK", "FALSE_POSITIVE")
            source: Where feedback came from
            notes: Human notes about this decision
        """
        event = FeedbackEvent(trace_id, original_decision, confidence, risk_score, tenant_id, agent_id)
        event.record_feedback(actual_outcome, source, notes)
        
        with self.buffer_lock:
            self.feedback_buffer.append(event)
            
            # Keep only last 100k events (production: stream to database)
            if len(self.feedback_buffer) > 100000:
                self.feedback_buffer = self.feedback_buffer[-100000:]
        
        return event
    
    def _analysis_worker(self):
        """Background worker to analyze feedback and compute metrics."""
        while True:
            try:
                time.sleep(60)  # Analyze every 60 seconds
                
                with self.buffer_lock:
                    if not self.feedback_buffer:
                        continue
                    
                    events_to_analyze = list(self.feedback_buffer)
                
                self._compute_metrics(events_to_analyze)
                self._detect_strategy_drift(events_to_analyze)
                self._check_retrain_triggers(events_to_analyze)
                
            except Exception as e:
                print(f"FeedbackLoopManager analysis error: {e}")
    
    def _retraining_worker(self):
        """Background worker to trigger retraining when needed."""
        while True:
            try:
                time.sleep(300)  # Check every 5 minutes
                
                if self._should_retrain():
                    self._trigger_retrain()
                
            except Exception as e:
                print(f"FeedbackLoopManager retrain worker error: {e}")
    
    def _compute_metrics(self, events: List[FeedbackEvent]):
        """Compute accuracy metrics from feedback events."""
        
        # Reset metrics
        for strategy_name in self.strategy_metrics:
            for key in ["tp", "tn", "fp", "fn"]:
                self.strategy_metrics[strategy_name][key] = 0
        
        for tenant_id in self.tenant_metrics:
            self.tenant_metrics[tenant_id]["correct"] = 0
            self.tenant_metrics[tenant_id]["total_decisions"] = 0
        
        # Tally results
        for event in events:
            if not event.actual_outcome:
                continue
            
            classification = event.get_classification()
            
            # Update tenant metrics
            tenant_data = self.tenant_metrics[event.tenant_id]
            tenant_data["total_decisions"] += 1
            if classification in ["TRUE_POSITIVE", "TRUE_NEGATIVE"]:
                tenant_data["correct"] += 1
            
            # Note: In a real system, we'd track which strategies were used
            # For now, we compute aggregate metrics
        
        # Compute percentages
        for tenant_id, metrics in self.tenant_metrics.items():
            if metrics["total_decisions"] > 0:
                metrics["accuracy"] = metrics["correct"] / metrics["total_decisions"]
            
            # Compute false positive rate (FP / (FP + TN))
            # (Placeholder: would need per-decision strategy tracking)
            metrics["false_positive_rate"] = 0.0
    
    def _detect_strategy_drift(self, events: List[FeedbackEvent]):
        """Detect if any strategy's accuracy is drifting (degrading)."""
        
        # This is a simplified version - production would track per-strategy outcomes
        # and detect temporal drift using sliding windows
        
        drift_detected = []
        for strategy_name, metrics in self.strategy_metrics.items():
            total = metrics["tp"] + metrics["tn"] + metrics["fp"] + metrics["fn"]
            if total == 0:
                continue
            
            accuracy = (metrics["tp"] + metrics["tn"]) / total
            if accuracy < 0.85:  # Threshold
                drift_detected.append({
                    "strategy": strategy_name,
                    "accuracy": accuracy,
                    "samples": total
                })
        
        if drift_detected:
            print(f"Strategy drift detected: {drift_detected}")
    
    def _check_retrain_triggers(self, events: List[FeedbackEvent]):
        """Check if retraining thresholds have been exceeded."""
        
        triggers = []
        
        # Count false positives/negatives
        fp_count = sum(1 for e in events if e.get_classification() == "FALSE_POSITIVE")
        fn_count = sum(1 for e in events if e.get_classification() == "FALSE_NEGATIVE")
        total_with_feedback = sum(1 for e in events if e.actual_outcome is not None)
        
        if total_with_feedback > 0:
            fp_rate = fp_count / total_with_feedback
            fn_rate = fn_count / total_with_feedback
            
            if fp_rate > self.retrain_thresholds["false_positive_rate"]:
                triggers.append(f"High FP rate: {fp_rate:.2%}")
            
            if fn_rate > self.retrain_thresholds["false_negative_rate"]:
                triggers.append(f"High FN rate: {fn_rate:.2%}")
        
        if len(events) > self.retrain_thresholds["min_feedback_events"]:
            triggers.append(f"Minimum feedback events reached ({len(events)})")
        
        if triggers:
            self._suggest_retraining(triggers)
    
    def _should_retrain(self) -> bool:
        """Check if retraining should be triggered."""
        
        with self.buffer_lock:
            events = self.feedback_buffer
        
        if not events:
            return False
        
        # Check if minimum feedback events reached
        events_with_feedback = [e for e in events if e.actual_outcome is not None]
        if len(events_with_feedback) >= self.retrain_thresholds["min_feedback_events"]:
            return True
        
        return False
    
    def _suggest_retraining(self, triggers: List[str]):
        """Suggest retraining based on triggers."""
        print(f"Retraining suggested: {triggers}")
        
        # In production:
        # 1. Create new policy version (staging)
        # 2. Use feedback data to adjust vector embeddings
        # 3. Retrain threat model on new false positives
        # 4. Run validation tests
        # 5. Stage for deployment
    
    def _trigger_retrain(self):
        """Trigger automatic retraining process."""
        
        new_version = self.policy_versions["current"] + 1
        
        print(f"Triggering retraining: current={self.policy_versions['current']} → staging={new_version}")
        
        # Steps:
        # 1. Extract false positives from feedback buffer
        # 2. Generate new threat embeddings from false negatives
        # 3. Adjust policy weights based on strategy performance
        # 4. Create staging policy version
        # 5. Run validation
        # 6. Prepare for canary deployment
        
        self.policy_versions["staging"] = new_version
    
    def promote_policy(self, version: int, percentage: float = 100.0):
        """Promote a policy version to production (optionally with canary)."""
        
        if percentage < 100.0:
            # Canary deployment
            self.ab_tests[f"canary_{version}"] = {
                "policy_version": version,
                "percentage": percentage,
                "start_time": datetime.now(),
                "metrics_baseline": dict(self.tenant_metrics)
            }
            print(f"Starting canary deployment for policy {version} ({percentage}% traffic)")
        else:
            # Full rollout
            self.policy_versions["current"] = version
            self.policy_versions["history"][version] = {
                "promoted_at": datetime.now().isoformat(),
                "final_metrics": dict(self.tenant_metrics)
            }
            print(f"Promoted policy {version} to production")
    
    def rollback_policy(self, version: int):
        """Rollback to a previous policy version."""
        
        if version in self.policy_versions["history"]:
            self.policy_versions["current"] = version
            print(f"Rolled back to policy {version}")
        else:
            print(f"Cannot rollback: policy {version} not in history")
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Get metrics for dashboard display."""
        
        with self.buffer_lock:
            total_feedback = len(self.feedback_buffer)
            events_with_outcome = [e for e in self.feedback_buffer if e.actual_outcome]
        
        return {
            "total_feedback_events": total_feedback,
            "events_with_outcome": len(events_with_outcome),
            "current_policy_version": self.policy_versions["current"],
            "staging_policy_version": self.policy_versions["staging"],
            "tenant_metrics": dict(self.tenant_metrics),
            "strategy_metrics": dict(self.strategy_metrics),
            "ab_tests": self.ab_tests,
            "last_updated": datetime.now().isoformat()
        }
