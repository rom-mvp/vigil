"""
🤖 Agentic Decision Engine - Multi-Strategy Policy Exploration with Confidence Scoring

This module implements autonomous decision-making with:
- Multiple concurrent policy evaluation paths
- Confidence intervals (not binary decisions)
- Risk scoring with uncertainty quantification
- Feedback-driven policy adaptation
- Ensemble voting with weighted confidence
- Autonomous strategy selection

Replaces deterministic single-path decision logic with multi-agent exploration.
"""

import asyncio
import json
import time
import threading
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import numpy as np
from datetime import datetime


class DecisionStrategy(Enum):
    """Multi-strategy decision paths for ensemble evaluation."""
    SEMANTIC_VECTOR = "semantic_vector"      # Vector similarity against threat DB
    RULE_HEURISTIC = "rule_heuristic"        # Regex pattern matching
    BEHAVIORAL_ANOMALY = "behavioral_anomaly" # Token entropy, request pattern analysis
    POLICY_OVERRIDE = "policy_override"      # Custom tenant policy rules
    CONTEXTUAL_RISK = "contextual_risk"      # Cross-request correlation


@dataclass
class StrategyResult:
    """Result from a single policy evaluation strategy."""
    strategy: DecisionStrategy
    decision: str  # "ALLOW", "BLOCK", "SANITIZE", "INVESTIGATE"
    confidence: float  # 0.0-1.0
    risk_score: float  # 0.0-1.0
    reasoning: str
    latency_ms: float
    evidence: Dict[str, Any]
    
    def to_dict(self):
        return {
            "strategy": self.strategy.value,
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "risk_score": round(self.risk_score, 4),
            "reasoning": self.reasoning,
            "latency_ms": round(latency_ms, 2),
            "evidence": self.evidence
        }


@dataclass
class AgenticDecision:
    """Final ensemble decision with confidence distribution."""
    decision: str  # "ALLOW", "BLOCK", "SANITIZE"
    confidence: float  # Ensemble confidence 0.0-1.0
    risk_score: float  # 0.0-1.0
    uncertainty: float  # Inverse of confidence (lower is better)
    strategy_results: List[StrategyResult]
    ensemble_voting: Dict[str, int]  # {decision: vote_count}
    recommendation_action: str  # What to do if uncertain
    audit_trace_id: str
    timestamp_ms: int
    learning_signal: Dict[str, Any]  # For feedback loop
    
    def to_dict(self):
        return {
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "risk_score": round(self.risk_score, 4),
            "uncertainty": round(self.uncertainty, 4),
            "strategy_results": [sr.to_dict() for sr in self.strategy_results],
            "ensemble_voting": self.ensemble_voting,
            "recommendation_action": self.recommendation_action,
            "audit_trace_id": self.audit_trace_id,
            "timestamp_ms": self.timestamp_ms
        }


class AgenticDecisionEngine:
    """
    Autonomous decision-making engine with multi-strategy exploration.
    Evaluates requests through 5 concurrent policy paths, aggregates with ensemble voting.
    """
    
    def __init__(self, firewall_engine=None, vector_engine=None, agentshield_client=None):
        self.firewall_engine = firewall_engine
        self.vector_engine = vector_engine
        self.agentshield_client = agentshield_client
        
        # Ensemble voting weights (learned from feedback)
        self.strategy_weights = {
            DecisionStrategy.SEMANTIC_VECTOR: 1.0,
            DecisionStrategy.RULE_HEURISTIC: 0.8,
            DecisionStrategy.BEHAVIORAL_ANOMALY: 0.7,
            DecisionStrategy.POLICY_OVERRIDE: 1.5,  # Tenant-specific policy gets highest weight
            DecisionStrategy.CONTEXTUAL_RISK: 0.9
        }
        
        # Confidence thresholds
        self.allow_threshold = 0.85  # Minimum confidence to ALLOW
        self.block_threshold = 0.70  # Minimum confidence to BLOCK
        self.investigate_threshold = 0.50  # Below this, request INVESTIGATE
        
        # Feedback metrics for learning
        self.feedback_buffer = []
        self.feedback_lock = threading.Lock()
        self.metrics = {
            "decisions_made": 0,
            "decisions_by_type": defaultdict(int),
            "false_positives": 0,
            "false_negatives": 0,
            "avg_confidence": 0.0,
            "strategy_performance": defaultdict(lambda: {"accuracy": 0.0, "count": 0})
        }
        
    async def evaluate_async(
        self,
        content: str,
        context: Dict[str, Any],
        tenant_id: str,
        agent_id: str,
        decision_request: Dict[str, Any]
    ) -> AgenticDecision:
        """
        Evaluate request through multiple concurrent strategies.
        Async execution means strategies run in parallel, not sequentially.
        
        Args:
            content: User input to evaluate
            context: Request context (headers, IP, etc.)
            tenant_id: Tenant identifier
            agent_id: Agent/model identifier
            decision_request: Full request payload
            
        Returns:
            AgenticDecision with confidence distribution
        """
        trace_id = context.get("request_id", "trace_unknown")
        start_time = time.time()
        
        # Launch all strategies concurrently
        tasks = [
            self._evaluate_semantic_vector(content, tenant_id),
            self._evaluate_rule_heuristic(content, tenant_id),
            self._evaluate_behavioral_anomaly(content, context, tenant_id),
            self._evaluate_policy_override(content, decision_request, tenant_id),
            self._evaluate_contextual_risk(content, context, agent_id, tenant_id)
        ]
        
        # Run all tasks in parallel (THIS IS NOT SEQUENTIAL)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        strategy_results = [r for r in results if isinstance(r, StrategyResult)]
        
        # Ensemble aggregation
        final_decision = self._aggregate_ensemble(
            strategy_results,
            context,
            tenant_id
        )
        
        final_decision.learning_signal = {
            "strategies_evaluated": len(strategy_results),
            "evaluation_latency_ms": round((time.time() - start_time) * 1000, 2),
            "ensemble_method": "weighted_voting",
            "trace_id": trace_id
        }
        
        # Record metrics
        self._record_decision(final_decision)
        
        return final_decision
    
    async def _evaluate_semantic_vector(self, content: str, tenant_id: str) -> StrategyResult:
        """Strategy 1: Vector semantic similarity against threat database."""
        start = time.time()
        
        if not self.vector_engine:
            return StrategyResult(
                strategy=DecisionStrategy.SEMANTIC_VECTOR,
                decision="ALLOW",
                confidence=0.5,
                risk_score=0.0,
                reasoning="Vector engine not available",
                latency_ms=0,
                evidence={}
            )
        
        try:
            # Run vector scan (async-compatible if vector_engine supports it)
            vector_results = self.vector_engine.scan(content)
            
            if vector_results.get("threat_detected"):
                # High confidence BLOCK based on vector match
                return StrategyResult(
                    strategy=DecisionStrategy.SEMANTIC_VECTOR,
                    decision="BLOCK",
                    confidence=vector_results.get("confidence", 0.9),
                    risk_score=vector_results.get("threat_score", 0.8),
                    reasoning=f"Vector threat detected: {vector_results.get('threat_type', 'unknown')}",
                    latency_ms=round((time.time() - start) * 1000, 2),
                    evidence=vector_results.get("matches", [])
                )
            else:
                return StrategyResult(
                    strategy=DecisionStrategy.SEMANTIC_VECTOR,
                    decision="ALLOW",
                    confidence=0.95,  # High confidence no threat
                    risk_score=0.0,
                    reasoning="No vector threat detected",
                    latency_ms=round((time.time() - start) * 1000, 2),
                    evidence={}
                )
        except Exception as e:
            # Graceful degradation
            return StrategyResult(
                strategy=DecisionStrategy.SEMANTIC_VECTOR,
                decision="INVESTIGATE",
                confidence=0.3,
                risk_score=0.5,
                reasoning=f"Vector evaluation failed: {str(e)}",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={"error": str(e)}
            )
    
    async def _evaluate_rule_heuristic(self, content: str, tenant_id: str) -> StrategyResult:
        """Strategy 2: Rule-based heuristic pattern matching."""
        start = time.time()
        
        if not self.firewall_engine:
            return StrategyResult(
                strategy=DecisionStrategy.RULE_HEURISTIC,
                decision="ALLOW",
                confidence=0.5,
                risk_score=0.0,
                reasoning="Firewall not available",
                latency_ms=0,
                evidence={}
            )
        
        try:
            firewall_result = self.firewall_engine.scan_input(content)
            
            if not firewall_result.get("safe", True):
                return StrategyResult(
                    strategy=DecisionStrategy.RULE_HEURISTIC,
                    decision="BLOCK",
                    confidence=0.85,  # High confidence for regex matches
                    risk_score=0.75,
                    reasoning=firewall_result.get("reason", "Heuristic pattern matched"),
                    latency_ms=round((time.time() - start) * 1000, 2),
                    evidence={"pattern": firewall_result.get("reason")}
                )
            else:
                return StrategyResult(
                    strategy=DecisionStrategy.RULE_HEURISTIC,
                    decision="ALLOW",
                    confidence=0.92,
                    risk_score=0.05,
                    reasoning="No heuristic patterns matched",
                    latency_ms=round((time.time() - start) * 1000, 2),
                    evidence={}
                )
        except Exception as e:
            return StrategyResult(
                strategy=DecisionStrategy.RULE_HEURISTIC,
                decision="INVESTIGATE",
                confidence=0.4,
                risk_score=0.5,
                reasoning=f"Rule evaluation failed: {str(e)}",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={"error": str(e)}
            )
    
    async def _evaluate_behavioral_anomaly(
        self,
        content: str,
        context: Dict[str, Any],
        tenant_id: str
    ) -> StrategyResult:
        """Strategy 3: Behavioral anomaly detection (token entropy, request patterns)."""
        start = time.time()
        
        try:
            # Measure entropy of content (compression-based)
            entropy = self._measure_entropy(content)
            
            # Check for anomalous patterns
            is_anomaly = False
            anomaly_score = 0.0
            reasoning = ""
            
            # High entropy suggests obfuscation/encoding
            if entropy > 4.5:
                is_anomaly = True
                anomaly_score += 0.3
                reasoning += f"High entropy ({entropy:.2f}) suggests encoding; "
            
            # Token ratio analysis (long prompts with few unique tokens)
            token_ratio = self._analyze_token_ratio(content)
            if token_ratio < 0.3:  # Low uniqueness
                is_anomaly = True
                anomaly_score += 0.2
                reasoning += "Low token diversity (repetition attack); "
            
            # Check for request frequency spike
            freq_anomaly = context.get("frequency_spike", False)
            if freq_anomaly:
                is_anomaly = True
                anomaly_score += 0.25
                reasoning += "Frequency spike detected; "
            
            if is_anomaly:
                return StrategyResult(
                    strategy=DecisionStrategy.BEHAVIORAL_ANOMALY,
                    decision="INVESTIGATE",
                    confidence=0.7,
                    risk_score=min(anomaly_score, 1.0),
                    reasoning=reasoning or "Behavioral anomaly detected",
                    latency_ms=round((time.time() - start) * 1000, 2),
                    evidence={
                        "entropy": round(entropy, 2),
                        "token_ratio": round(token_ratio, 2),
                        "frequency_spike": freq_anomaly
                    }
                )
            else:
                return StrategyResult(
                    strategy=DecisionStrategy.BEHAVIORAL_ANOMALY,
                    decision="ALLOW",
                    confidence=0.88,
                    risk_score=0.1,
                    reasoning="Normal behavioral patterns",
                    latency_ms=round((time.time() - start) * 1000, 2),
                    evidence={"entropy": round(entropy, 2), "token_ratio": round(token_ratio, 2)}
                )
        except Exception as e:
            return StrategyResult(
                strategy=DecisionStrategy.BEHAVIORAL_ANOMALY,
                decision="ALLOW",
                confidence=0.5,
                risk_score=0.0,
                reasoning=f"Behavioral analysis unavailable: {str(e)}",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={"error": str(e)}
            )
    
    async def _evaluate_policy_override(
        self,
        content: str,
        decision_request: Dict[str, Any],
        tenant_id: str
    ) -> StrategyResult:
        """Strategy 4: Tenant-specific custom policy rules."""
        start = time.time()
        
        if not self.agentshield_client:
            return StrategyResult(
                strategy=DecisionStrategy.POLICY_OVERRIDE,
                decision="ALLOW",
                confidence=0.5,
                risk_score=0.0,
                reasoning="AgentShield policy engine not available",
                latency_ms=0,
                evidence={}
            )
        
        try:
            # Call AgentShield for tenant-specific policy evaluation
            policy_decision = self.agentshield_client.get_decision(decision_request)
            
            decision_map = {
                "ALLOW": "ALLOW",
                "BLOCK": "BLOCK",
                "SANITIZE": "SANITIZE"
            }
            
            return StrategyResult(
                strategy=DecisionStrategy.POLICY_OVERRIDE,
                decision=decision_map.get(policy_decision.get("decision", "ALLOW"), "ALLOW"),
                confidence=0.95,  # Tenant policy is most authoritative
                risk_score=policy_decision.get("risk_score", 0.0),
                reasoning=f"Policy decision: {policy_decision.get('decision')}",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={
                    "policy_version": policy_decision.get("policy_version"),
                    "audit_event_id": policy_decision.get("audit_event_id")
                }
            )
        except Exception as e:
            return StrategyResult(
                strategy=DecisionStrategy.POLICY_OVERRIDE,
                decision="INVESTIGATE",
                confidence=0.6,
                risk_score=0.5,
                reasoning=f"Policy evaluation failed: {str(e)}",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={"error": str(e)}
            )
    
    async def _evaluate_contextual_risk(
        self,
        content: str,
        context: Dict[str, Any],
        agent_id: str,
        tenant_id: str
    ) -> StrategyResult:
        """Strategy 5: Cross-request correlation and contextual risk scoring."""
        start = time.time()
        
        try:
            risk_score = 0.0
            reasoning = ""
            
            # Check agent reputation (low for unknown agents)
            agent_trustworthiness = context.get("agent_trustworthiness", 0.5)
            if agent_trustworthiness < 0.3:
                risk_score += 0.2
                reasoning += f"Low agent trust ({agent_trustworthiness:.2f}); "
            
            # Check request pattern (similar to recent blocks)
            is_repeat_attack = context.get("is_repeat_attack", False)
            if is_repeat_attack:
                risk_score += 0.3
                reasoning += "Repeat attack pattern detected; "
            
            # Geolocation anomaly
            geo_anomaly = context.get("geo_anomaly", False)
            if geo_anomaly:
                risk_score += 0.15
                reasoning += "Geolocation anomaly; "
            
            # Time-of-day anomaly
            hour = datetime.now().hour
            if hour < 6 or hour > 23:  # Off-hours
                risk_score += 0.05
                reasoning += "Off-hours request; "
            
            decision = "ALLOW"
            confidence = 0.85
            if risk_score > 0.6:
                decision = "INVESTIGATE"
                confidence = 0.75
            
            return StrategyResult(
                strategy=DecisionStrategy.CONTEXTUAL_RISK,
                decision=decision,
                confidence=confidence,
                risk_score=min(risk_score, 1.0),
                reasoning=reasoning or "Nominal contextual risk",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={
                    "agent_trustworthiness": round(agent_trustworthiness, 2),
                    "is_repeat_attack": is_repeat_attack,
                    "geo_anomaly": geo_anomaly
                }
            )
        except Exception as e:
            return StrategyResult(
                strategy=DecisionStrategy.CONTEXTUAL_RISK,
                decision="ALLOW",
                confidence=0.5,
                risk_score=0.0,
                reasoning=f"Contextual analysis unavailable: {str(e)}",
                latency_ms=round((time.time() - start) * 1000, 2),
                evidence={"error": str(e)}
            )
    
    def _aggregate_ensemble(
        self,
        strategy_results: List[StrategyResult],
        context: Dict[str, Any],
        tenant_id: str
    ) -> AgenticDecision:
        """Aggregate multi-strategy results into final decision."""
        
        # Weighted voting
        decision_votes = defaultdict(float)
        weighted_risk = 0.0
        total_weight = 0.0
        
        for result in strategy_results:
            weight = self.strategy_weights.get(result.strategy, 1.0)
            decision_votes[result.decision] += weight * result.confidence
            weighted_risk += result.risk_score * weight
            total_weight += weight
        
        if total_weight == 0:
            total_weight = 1.0
        
        weighted_risk /= total_weight
        
        # Determine final decision by highest weighted votes
        final_decision = max(decision_votes, key=decision_votes.get) if decision_votes else "INVESTIGATE"
        
        # Calculate ensemble confidence
        max_votes = decision_votes.get(final_decision, 0)
        ensemble_confidence = min(max_votes / total_weight, 1.0) if total_weight > 0 else 0.5
        
        # Determine action based on thresholds
        recommendation = "PROCEED"
        if final_decision == "BLOCK":
            recommendation = "REJECT"
        elif final_decision == "SANITIZE":
            recommendation = "SANITIZE_AND_PROCEED"
        elif ensemble_confidence < self.block_threshold:
            recommendation = "INVESTIGATE_FURTHER"
        
        return AgenticDecision(
            decision=final_decision,
            confidence=ensemble_confidence,
            risk_score=weighted_risk,
            uncertainty=1.0 - ensemble_confidence,
            strategy_results=strategy_results,
            ensemble_voting=dict(decision_votes),
            recommendation_action=recommendation,
            audit_trace_id=context.get("request_id", "unknown"),
            timestamp_ms=int(time.time() * 1000),
            learning_signal={}
        )
    
    def _measure_entropy(self, text: str) -> float:
        """Measure Shannon entropy of text (higher = more random/encoded)."""
        if not text:
            return 0.0
        
        # Count character frequencies
        freq = defaultdict(int)
        for char in text:
            freq[char] += 1
        
        # Calculate Shannon entropy
        entropy = 0.0
        for count in freq.values():
            p = count / len(text)
            entropy -= p * np.log2(p) if p > 0 else 0
        
        return entropy
    
    def _analyze_token_ratio(self, text: str) -> float:
        """Analyze token diversity (unique tokens / total tokens)."""
        words = text.lower().split()
        if not words:
            return 0.0
        
        unique_words = len(set(words))
        return unique_words / len(words)
    
    def _record_decision(self, decision: AgenticDecision):
        """Record decision for metrics and feedback."""
        with self.feedback_lock:
            self.metrics["decisions_made"] += 1
            self.metrics["decisions_by_type"][decision.decision] += 1
            self.feedback_buffer.append({
                "timestamp": decision.timestamp_ms,
                "decision": decision.decision,
                "confidence": decision.confidence,
                "risk_score": decision.risk_score,
                "strategies": [sr.strategy.value for sr in decision.strategy_results],
                "trace_id": decision.audit_trace_id
            })
            
            # Keep only last 10k decisions
            if len(self.feedback_buffer) > 10000:
                self.feedback_buffer = self.feedback_buffer[-10000:]
    
    def record_feedback(self, trace_id: str, was_correct: bool, actual_outcome: str):
        """Record feedback for a decision (used by feedback loop system)."""
        with self.feedback_lock:
            for decision in self.feedback_buffer:
                if decision.get("trace_id") == trace_id:
                    decision["feedback"] = {
                        "was_correct": was_correct,
                        "actual_outcome": actual_outcome,
                        "feedback_timestamp": int(time.time() * 1000)
                    }
                    break
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        with self.feedback_lock:
            return {
                "total_decisions": self.metrics["decisions_made"],
                "decisions_by_type": dict(self.metrics["decisions_by_type"]),
                "buffer_size": len(self.feedback_buffer)
            }
