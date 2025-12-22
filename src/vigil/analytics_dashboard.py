"""
📊 Real-Time Analytics Dashboard - Streaming Telemetry & Decision Intelligence

Provides:
- Live decision traces (confidence distributions, strategy breakdown)
- False positive detection heatmap
- Policy effectiveness metrics
- Anomaly alerts (sudden spike in blocks)
- Model health dashboard
- Tenant-specific analytics

WebSocket support for real-time streaming.
"""

import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class DecisionTrace:
    """Represents a single decision with full telemetry."""
    
    def __init__(
        self,
        request_id: str,
        tenant_id: str,
        agent_id: str,
        decision: str,
        confidence: float,
        risk_score: float,
        strategies_used: List[Dict[str, Any]]
    ):
        self.request_id = request_id
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.decision = decision
        self.confidence = confidence
        self.risk_score = risk_score
        self.strategies_used = strategies_used
        self.timestamp_ms = int(time.time() * 1000)
        
        # Feedback (populated later)
        self.feedback = None
        self.feedback_timestamp_ms = None
        self.was_correct = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "risk_score": round(self.risk_score, 4),
            "strategies": self.strategies_used,
            "timestamp_ms": self.timestamp_ms,
            "feedback": self.feedback,
            "was_correct": self.was_correct
        }


class AnomalyDetector:
    """Detects anomalies in decision patterns."""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.decision_history = deque(maxlen=window_size)
        self.block_rate_history = deque(maxlen=100)
        self.anomalies = []
        self._lock = threading.Lock()
        
        self.baseline_block_rate = 0.05  # 5% blocks is normal
        self.spike_threshold = 3.0  # 3x normal is anomaly
    
    def record_decision(self, decision: str):
        """Record a decision for anomaly detection."""
        with self._lock:
            self.decision_history.append(decision)
            
            # Compute current block rate
            if len(self.decision_history) >= 100:
                recent = list(self.decision_history)[-100:]
                block_count = sum(1 for d in recent if d == "BLOCK")
                block_rate = block_count / 100
                
                self.block_rate_history.append(block_rate)
                
                # Detect spike
                if block_rate > self.baseline_block_rate * self.spike_threshold:
                    self.anomalies.append({
                        "type": "block_rate_spike",
                        "block_rate": round(block_rate, 4),
                        "baseline": self.baseline_block_rate,
                        "timestamp": datetime.now().isoformat()
                    })
    
    def get_anomalies(self, since_timestamp: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent anomalies."""
        with self._lock:
            if since_timestamp:
                # Filter by timestamp
                return [a for a in self.anomalies if a.get("timestamp") > since_timestamp]
            return list(self.anomalies)[-100:]  # Last 100


class RealTimeAnalyticsDashboard:
    """
    Aggregates decision telemetry and provides dashboard data.
    """
    
    def __init__(self):
        self.decision_traces = deque(maxlen=10000)  # Keep last 10k decisions
        self.traces_lock = threading.Lock()
        
        self.anomaly_detector = AnomalyDetector()
        
        # Metrics aggregated per time window (1 min, 5 min, 1 hour)
        self.metrics_windows = {
            "1m": deque(maxlen=60),
            "5m": deque(maxlen=12),
            "1h": deque(maxlen=24)
        }
        
        # Per-tenant dashboard
        self.tenant_dashboards = defaultdict(lambda: {
            "decisions_made": 0,
            "block_rate": 0.0,
            "avg_confidence": 0.0,
            "avg_risk_score": 0.0,
            "false_positive_rate": 0.0,
            "policy_version": None,
            "last_updated": None
        })
        
        # Per-strategy effectiveness
        self.strategy_effectiveness = defaultdict(lambda: {
            "evaluations": 0,
            "correct_blocks": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "accuracy": 0.0
        })
        
        # Start background workers
        self._start_workers()
    
    def _start_workers(self):
        """Start background aggregation workers."""
        threading.Thread(target=self._aggregation_worker, daemon=True).start()
    
    def record_decision(self, trace: DecisionTrace):
        """Record a decision with full telemetry."""
        with self.traces_lock:
            self.decision_traces.append(trace)
        
        # Record for anomaly detection
        self.anomaly_detector.record_decision(trace.decision)
        
        # Update tenant dashboard
        tenant_data = self.tenant_dashboards[trace.tenant_id]
        tenant_data["decisions_made"] += 1
        tenant_data["last_updated"] = datetime.now().isoformat()
    
    def record_feedback(self, request_id: str, was_correct: bool, actual_outcome: str):
        """Record feedback for a decision."""
        with self.traces_lock:
            for trace in self.decision_traces:
                if trace.request_id == request_id:
                    trace.was_correct = was_correct
                    trace.feedback = actual_outcome
                    trace.feedback_timestamp_ms = int(time.time() * 1000)
                    break
    
    def _aggregation_worker(self):
        """Background worker to aggregate metrics."""
        while True:
            try:
                time.sleep(60)  # Aggregate every 60 seconds
                
                with self.traces_lock:
                    traces = list(self.decision_traces)
                
                if not traces:
                    continue
                
                # Aggregate over windows
                self._aggregate_metrics(traces)
                self._update_tenant_metrics(traces)
                self._update_strategy_metrics(traces)
                
            except Exception as e:
                logger.error(f"Aggregation worker error: {e}")
    
    def _aggregate_metrics(self, traces: List[DecisionTrace]):
        """Aggregate metrics over time windows."""
        
        # Get traces from last minute
        now_ms = int(time.time() * 1000)
        recent = [t for t in traces if now_ms - t.timestamp_ms < 60000]
        
        if not recent:
            return
        
        # Compute 1m metrics
        block_count = sum(1 for t in recent if t.decision == "BLOCK")
        block_rate = block_count / len(recent) if recent else 0.0
        avg_confidence = sum(t.confidence for t in recent) / len(recent) if recent else 0.0
        avg_risk = sum(t.risk_score for t in recent) / len(recent) if recent else 0.0
        
        metrics_snapshot = {
            "timestamp": datetime.now().isoformat(),
            "window": "1m",
            "decisions_count": len(recent),
            "block_rate": round(block_rate, 4),
            "avg_confidence": round(avg_confidence, 4),
            "avg_risk_score": round(avg_risk, 4),
            "distribution": {
                "ALLOW": sum(1 for t in recent if t.decision == "ALLOW"),
                "BLOCK": block_count,
                "SANITIZE": sum(1 for t in recent if t.decision == "SANITIZE"),
                "INVESTIGATE": sum(1 for t in recent if t.decision == "INVESTIGATE")
            }
        }
        
        self.metrics_windows["1m"].append(metrics_snapshot)
    
    def _update_tenant_metrics(self, traces: List[DecisionTrace]):
        """Update per-tenant metrics."""
        
        tenant_data_map = defaultdict(lambda: {
            "total": 0, "blocks": 0, "confidences": [], "risk_scores": [],
            "correct": 0, "feedback_total": 0
        })
        
        for trace in traces:
            data = tenant_data_map[trace.tenant_id]
            data["total"] += 1
            if trace.decision == "BLOCK":
                data["blocks"] += 1
            data["confidences"].append(trace.confidence)
            data["risk_scores"].append(trace.risk_score)
            
            if trace.was_correct is not None:
                data["feedback_total"] += 1
                if trace.was_correct:
                    data["correct"] += 1
        
        # Update dashboards
        for tenant_id, data in tenant_data_map.items():
            dashboard = self.tenant_dashboards[tenant_id]
            dashboard["decisions_made"] = data["total"]
            dashboard["block_rate"] = round(data["blocks"] / data["total"], 4) if data["total"] > 0 else 0.0
            dashboard["avg_confidence"] = round(sum(data["confidences"]) / len(data["confidences"]), 4) if data["confidences"] else 0.0
            dashboard["avg_risk_score"] = round(sum(data["risk_scores"]) / len(data["risk_scores"]), 4) if data["risk_scores"] else 0.0
            dashboard["false_positive_rate"] = round(
                1.0 - (data["correct"] / data["feedback_total"]), 4
            ) if data["feedback_total"] > 0 else 0.0
    
    def _update_strategy_metrics(self, traces: List[DecisionTrace]):
        """Update strategy effectiveness metrics."""
        
        for trace in traces:
            for strategy_result in trace.strategies_used:
                strategy_name = strategy_result.get("strategy", "unknown")
                strat_data = self.strategy_effectiveness[strategy_name]
                
                strat_data["evaluations"] += 1
    
    def get_dashboard_data(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get dashboard data for UI."""
        
        with self.traces_lock:
            traces = list(self.decision_traces)
        
        if tenant_id:
            traces = [t for t in traces if t.tenant_id == tenant_id]
        
        return {
            "summary": {
                "total_decisions": len(traces),
                "timestamp": datetime.now().isoformat(),
                "traces": [t.to_dict() for t in list(traces)[-100:]]  # Last 100 traces
            },
            "metrics_windows": {
                "1m": list(self.metrics_windows["1m"])[-10:],
                "5m": list(self.metrics_windows["5m"])[-10:],
                "1h": list(self.metrics_windows["1h"])[-10:]
            },
            "tenant_dashboards": dict(self.tenant_dashboards) if not tenant_id else {tenant_id: self.tenant_dashboards[tenant_id]},
            "anomalies": self.anomaly_detector.get_anomalies(),
            "strategy_effectiveness": dict(self.strategy_effectiveness)
        }
    
    def get_trace(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed trace for a specific request."""
        with self.traces_lock:
            for trace in self.decision_traces:
                if trace.request_id == request_id:
                    return trace.to_dict()
        return None
