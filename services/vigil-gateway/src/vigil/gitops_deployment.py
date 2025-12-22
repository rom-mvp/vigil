"""
🚀 GitOps & Canary Deployment System - Policy Gradual Rollout with Auto-Rollback

Implements:
- Policy versioning & git-based tracking
- Canary deployments (traffic splitting)
- A/B testing framework
- Automatic regression detection & rollback
- Metrics-driven deployment gates

Integrates with ArgoCD/Flux for policy delivery.
"""

import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class DeploymentStrategy(Enum):
    """Policy deployment strategies."""
    IMMEDIATE = "immediate"  # 100% rollout immediately
    CANARY = "canary"  # Start with small percentage, ramp up
    BLUE_GREEN = "blue_green"  # Parallel deployments, switch at once
    SHADOW = "shadow"  # Run in shadow mode without blocking


class DeploymentState(Enum):
    """Deployment lifecycle states."""
    PENDING = "pending"
    VALIDATING = "validating"
    STAGED = "staged"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class CanaryDeployment:
    """Manages a single canary deployment."""
    
    def __init__(
        self,
        deployment_id: str,
        policy_version: int,
        target_percentage: float,
        ramp_duration_minutes: int = 30
    ):
        self.deployment_id = deployment_id
        self.policy_version = policy_version
        self.target_percentage = target_percentage
        self.ramp_duration_minutes = ramp_duration_minutes
        
        self.state = DeploymentState.PENDING
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        
        # Metrics
        self.metrics = {
            "traffic_served": 0,
            "block_rate": 0.0,
            "avg_latency_ms": 0.0,
            "error_rate": 0.0,
            "false_positive_increase": 0.0,
            "false_negative_increase": 0.0
        }
        
        # Baseline (metrics from previous stable version)
        self.baseline_metrics = {}
        
        # Regression detection
        self.regression_detected = False
        self.regression_reason = None
    
    def start(self):
        """Start the canary deployment."""
        self.state = DeploymentState.DEPLOYING
        self.started_at = datetime.now()
        logger.info(f"Started canary {self.deployment_id} for v{self.policy_version} at {self.target_percentage}%")
    
    def check_regression(self, current_metrics: Dict[str, float]) -> bool:
        """Check if metrics have regressed beyond acceptable limits."""
        
        regression_thresholds = {
            "block_rate_increase": 0.10,  # 10% relative increase
            "error_rate_increase": 0.05,  # 5% relative increase
            "fp_increase": 0.20,  # 20% relative increase
            "fn_increase": 0.10  # 10% relative increase
        }
        
        regressions = []
        
        # Check block rate
        if "block_rate" in current_metrics and self.baseline_metrics.get("block_rate"):
            increase = (current_metrics["block_rate"] - self.baseline_metrics["block_rate"]) / self.baseline_metrics["block_rate"]
            if increase > regression_thresholds["block_rate_increase"]:
                regressions.append(f"Block rate up {increase:.1%}")
        
        # Check false positive rate
        if "false_positive_increase" in current_metrics:
            if current_metrics["false_positive_increase"] > regression_thresholds["fp_increase"]:
                regressions.append(f"FP rate up {current_metrics['false_positive_increase']:.1%}")
        
        # Check false negative rate
        if "false_negative_increase" in current_metrics:
            if current_metrics["false_negative_increase"] > regression_thresholds["fn_increase"]:
                regressions.append(f"FN rate up {current_metrics['false_negative_increase']:.1%}")
        
        if regressions:
            self.regression_detected = True
            self.regression_reason = "; ".join(regressions)
            logger.warning(f"Regression detected in {self.deployment_id}: {self.regression_reason}")
            return True
        
        return False
    
    def mark_complete(self):
        """Mark deployment as complete."""
        self.state = DeploymentState.ACTIVE
        self.completed_at = datetime.now()


class GitOpsDeploymentManager:
    """
    Manages policy deployments with GitOps workflows.
    
    Responsibilities:
    - Validate policy changes before deployment
    - Orchestrate canary deployments
    - Monitor metrics and detect regressions
    - Automatic rollback on failure
    - Maintain deployment history
    """
    
    def __init__(self, git_repo_url: Optional[str] = None, argocd_server: Optional[str] = None):
        self.git_repo_url = git_repo_url or os.environ.get("VIGIL_POLICY_REPO")
        self.argocd_server = argocd_server or os.environ.get("ARGOCD_SERVER", "argocd.default.svc")
        
        # Deployment tracking
        self.deployments = {}  # {deployment_id: CanaryDeployment}
        self.deployment_history = []
        self.deployments_lock = threading.Lock()
        
        # Current active version
        self.active_version = 1
        self.previous_version = None  # For quick rollback
        
        # Rollback configuration
        self.auto_rollback_enabled = True
        self.rollback_thresholds = {
            "critical_error_rate": 0.10,
            "critical_fn_rate": 0.05
        }
        
        # Start background workers
        self._start_workers()
    
    def _start_workers(self):
        """Start background monitoring workers."""
        threading.Thread(target=self._deployment_monitor, daemon=True).start()
    
    def propose_deployment(
        self,
        policy_version: int,
        strategy: DeploymentStrategy,
        description: str = ""
    ) -> str:
        """
        Propose a new policy deployment.
        
        Args:
            policy_version: Policy version to deploy
            strategy: Deployment strategy (canary, blue-green, etc.)
            description: Deployment notes
            
        Returns:
            Deployment ID
        """
        
        deployment_id = f"deploy_{policy_version}_{int(time.time())}"
        
        with self.deployments_lock:
            if strategy == DeploymentStrategy.CANARY:
                deployment = CanaryDeployment(
                    deployment_id=deployment_id,
                    policy_version=policy_version,
                    target_percentage=100.0,  # Will ramp up
                    ramp_duration_minutes=30
                )
            elif strategy == DeploymentStrategy.IMMEDIATE:
                deployment = CanaryDeployment(
                    deployment_id=deployment_id,
                    policy_version=policy_version,
                    target_percentage=100.0,
                    ramp_duration_minutes=0
                )
            else:
                raise ValueError(f"Unknown strategy: {strategy}")
            
            deployment.state = DeploymentState.PENDING
            self.deployments[deployment_id] = deployment
        
        logger.info(f"Proposed deployment {deployment_id}: v{policy_version} via {strategy.value}")
        return deployment_id
    
    def start_deployment(self, deployment_id: str, baseline_metrics: Dict[str, float]) -> bool:
        """
        Start a proposed deployment.
        
        Args:
            deployment_id: ID of deployment to start
            baseline_metrics: Baseline metrics from current stable version
            
        Returns:
            True if started successfully
        """
        
        with self.deployments_lock:
            if deployment_id not in self.deployments:
                logger.error(f"Deployment {deployment_id} not found")
                return False
            
            deployment = self.deployments[deployment_id]
            deployment.baseline_metrics = baseline_metrics
            deployment.start()
        
        # Trigger ArgoCD sync if configured
        if self.git_repo_url:
            self._sync_argocd(deployment.policy_version)
        
        return True
    
    def _sync_argocd(self, policy_version: int):
        """Sync policy version via ArgoCD."""
        # In production: would call ArgoCD API
        logger.info(f"Syncing policy v{policy_version} via ArgoCD")
        
        # Example ArgoCD call:
        # argocd app sync vigil-policies --server=$ARGOCD_SERVER --auth-token=$TOKEN
    
    def _deployment_monitor(self):
        """Background worker to monitor active deployments."""
        while True:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                with self.deployments_lock:
                    for deployment_id, deployment in list(self.deployments.items()):
                        if deployment.state in [DeploymentState.DEPLOYING]:
                            # Check for regression
                            current_metrics = self._collect_metrics(deployment)
                            
                            if deployment.check_regression(current_metrics):
                                if self.auto_rollback_enabled:
                                    self._trigger_rollback(deployment_id)
                            
                            # Update deployment metrics
                            deployment.metrics = current_metrics
            
            except Exception as e:
                logger.error(f"Deployment monitor error: {e}")
    
    def _collect_metrics(self, deployment: CanaryDeployment) -> Dict[str, float]:
        """Collect current metrics from telemetry system."""
        # In production: would fetch from analytics dashboard
        return {
            "traffic_served": 100,
            "block_rate": 0.05,
            "avg_latency_ms": 45.2,
            "error_rate": 0.001,
            "false_positive_increase": 0.0,
            "false_negative_increase": 0.0
        }
    
    def _trigger_rollback(self, deployment_id: str):
        """Automatically rollback a failed deployment."""
        
        with self.deployments_lock:
            if deployment_id not in self.deployments:
                return
            
            deployment = self.deployments[deployment_id]
            
            logger.error(f"ROLLBACK TRIGGERED for {deployment_id}: {deployment.regression_reason}")
            
            deployment.state = DeploymentState.ROLLING_BACK
            
            # Rollback to previous version
            if self.previous_version:
                self.active_version = self.previous_version
                deployment.state = DeploymentState.ROLLED_BACK
                logger.info(f"Rolled back to policy v{self.previous_version}")
            else:
                deployment.state = DeploymentState.FAILED
                logger.error(f"Cannot rollback: no previous version available")
    
    def promote_deployment(self, deployment_id: str) -> bool:
        """Promote a deployment to production."""
        
        with self.deployments_lock:
            if deployment_id not in self.deployments:
                return False
            
            deployment = self.deployments[deployment_id]
            
            if deployment.regression_detected:
                logger.error(f"Cannot promote {deployment_id}: regression detected")
                return False
            
            # Update versions
            self.previous_version = self.active_version
            self.active_version = deployment.policy_version
            
            deployment.mark_complete()
            self.deployment_history.append({
                "deployment_id": deployment_id,
                "policy_version": deployment.policy_version,
                "promoted_at": datetime.now().isoformat(),
                "metrics": deployment.metrics
            })
            
            logger.info(f"Promoted {deployment_id} to production (v{self.active_version})")
            return True
    
    def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a deployment."""
        
        with self.deployments_lock:
            if deployment_id not in self.deployments:
                return None
            
            deployment = self.deployments[deployment_id]
            
            return {
                "deployment_id": deployment_id,
                "state": deployment.state.value,
                "policy_version": deployment.policy_version,
                "created_at": deployment.created_at.isoformat(),
                "started_at": deployment.started_at.isoformat() if deployment.started_at else None,
                "completed_at": deployment.completed_at.isoformat() if deployment.completed_at else None,
                "metrics": deployment.metrics,
                "regression_detected": deployment.regression_detected,
                "regression_reason": deployment.regression_reason
            }
    
    def get_deployment_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent deployment history."""
        return self.deployment_history[-limit:]
    
    def run_a_b_test(
        self,
        policy_version_a: int,
        policy_version_b: int,
        traffic_split: float = 0.5,
        duration_minutes: int = 60
    ) -> str:
        """
        Run an A/B test between two policy versions.
        
        Args:
            policy_version_a: Control version
            policy_version_b: Treatment version
            traffic_split: % of traffic to version B (0.0-1.0)
            duration_minutes: How long to run test
            
        Returns:
            Test ID
        """
        
        test_id = f"abtest_{policy_version_a}_vs_{policy_version_b}_{int(time.time())}"
        
        logger.info(f"Starting A/B test {test_id}: v{policy_version_a} vs v{policy_version_b} ({traffic_split:.0%})")
        
        # In production: would set up traffic splitting via service mesh (Istio)
        # For now, just log
        
        return test_id


# Need to add import for os
import os
