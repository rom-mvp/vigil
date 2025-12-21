"""
Vigil Data Models - Extended for AgentShield v2.0
Supports semantic classification, scanner pipeline, data registry, and supply chain fields
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum


class ScannerVerdict(str, Enum):
    """Scanner pipeline verdict"""
    PASS = "PASS"
    WARN = "WARN"
    BLOCK = "BLOCK"


class ClassifierVerdict(str, Enum):
    """Semantic classifier verdict"""
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    MALICIOUS = "MALICIOUS"


@dataclass
class SemanticClassification:
    """Semantic classifier results from IntentClassifier"""
    classifier_labels: List[str] = field(default_factory=list)  # ['jailbreak', 'exfiltration', 'coercion']
    classifier_scores: Dict[str, float] = field(default_factory=dict)  # {'jailbreak': 0.95, ...}
    classifier_verdict: Optional[ClassifierVerdict] = None


@dataclass
class ScannerPipeline:
    """Scanner pipeline results"""
    scanner_verdict: Optional[ScannerVerdict] = None
    scanner_confidence: float = 0.0  # 0.0 - 1.0
    scanner_modules_failed: List[str] = field(default_factory=list)
    scanner_detections: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataRegistry:
    """Data governance and registry fields"""
    dataset_id: Optional[str] = None
    model_id: Optional[str] = None
    poisoning_detected: bool = False
    dp_enforced: bool = False  # Differential privacy
    watermark_verified: bool = False


@dataclass
class SupplyChain:
    """Supply chain integrity fields"""
    sbom_verified: bool = False
    component_hash: Optional[str] = None  # Git commit hash
    component_version: Optional[str] = None


@dataclass
class AuditEvent:
    """
    Extended audit event schema for AgentShield v2.0
    Captures all security, governance, and supply chain telemetry
    """
    # Core fields
    timestamp: datetime
    agent_id: str
    status: str  # ALLOWED, BLOCKED, MODIFIED
    
    # Original fields
    tenant_id: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    
    # Legacy detection fields
    details: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None
    
    # New AgentShield v2.0 fields
    semantic: Optional[SemanticClassification] = None
    scanner: Optional[ScannerPipeline] = None
    registry: Optional[DataRegistry] = None
    supply_chain: Optional[SupplyChain] = None
    
    # Metadata
    latency_ms: Optional[int] = None
    model_used: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "status": self.status,
            "tenant_id": self.tenant_id,
            "request_id": self.request_id,
            "endpoint": self.endpoint,
            "details": self.details,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "model_used": self.model_used,
            # Semantic classification
            "classifier_labels": self.semantic.classifier_labels if self.semantic else [],
            "classifier_scores": self.semantic.classifier_scores if self.semantic else {},
            "classifier_verdict": self.semantic.classifier_verdict.value if self.semantic and self.semantic.classifier_verdict else None,
            # Scanner pipeline
            "scanner_verdict": self.scanner.scanner_verdict.value if self.scanner and self.scanner.scanner_verdict else None,
            "scanner_confidence": self.scanner.scanner_confidence if self.scanner else 0.0,
            "scanner_modules_failed": self.scanner.scanner_modules_failed if self.scanner else [],
            "scanner_detections": self.scanner.scanner_detections if self.scanner else {},
            # Data registry
            "dataset_id": self.registry.dataset_id if self.registry else None,
            "model_id": self.registry.model_id if self.registry else None,
            "poisoning_detected": self.registry.poisoning_detected if self.registry else False,
            "dp_enforced": self.registry.dp_enforced if self.registry else False,
            "watermark_verified": self.registry.watermark_verified if self.registry else False,
            # Supply chain
            "sbom_verified": self.supply_chain.sbom_verified if self.supply_chain else False,
            "component_hash": self.supply_chain.component_hash if self.supply_chain else None,
            "component_version": self.supply_chain.component_version if self.supply_chain else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AuditEvent':
        """Create AuditEvent from dictionary"""
        semantic = None
        if data.get('classifier_labels') or data.get('classifier_scores'):
            semantic = SemanticClassification(
                classifier_labels=data.get('classifier_labels', []),
                classifier_scores=data.get('classifier_scores', {}),
                classifier_verdict=ClassifierVerdict(data['classifier_verdict']) if data.get('classifier_verdict') else None
            )
        
        scanner = None
        if data.get('scanner_verdict'):
            scanner = ScannerPipeline(
                scanner_verdict=ScannerVerdict(data['scanner_verdict']),
                scanner_confidence=data.get('scanner_confidence', 0.0),
                scanner_modules_failed=data.get('scanner_modules_failed', []),
                scanner_detections=data.get('scanner_detections', {})
            )
        
        registry = None
        if any(k in data for k in ['dataset_id', 'model_id', 'poisoning_detected', 'dp_enforced', 'watermark_verified']):
            registry = DataRegistry(
                dataset_id=data.get('dataset_id'),
                model_id=data.get('model_id'),
                poisoning_detected=data.get('poisoning_detected', False),
                dp_enforced=data.get('dp_enforced', False),
                watermark_verified=data.get('watermark_verified', False)
            )
        
        supply_chain = None
        if any(k in data for k in ['sbom_verified', 'component_hash', 'component_version']):
            supply_chain = SupplyChain(
                sbom_verified=data.get('sbom_verified', False),
                component_hash=data.get('component_hash'),
                component_version=data.get('component_version')
            )
        
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']) if isinstance(data['timestamp'], str) else data['timestamp'],
            agent_id=data['agent_id'],
            status=data['status'],
            tenant_id=data.get('tenant_id'),
            request_id=data.get('request_id'),
            endpoint=data.get('endpoint'),
            details=data.get('details', {}),
            reason=data.get('reason'),
            latency_ms=data.get('latency_ms'),
            model_used=data.get('model_used'),
            semantic=semantic,
            scanner=scanner,
            registry=registry,
            supply_chain=supply_chain
        )


@dataclass
class ThreatAlert:
    """High-priority security alert"""
    alert_id: str
    alert_type: str  # jailbreak, exfiltration, poisoning, sbom_failure
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    timestamp: datetime
    event: AuditEvent
    confidence: float
    description: str
    
    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "event": self.event.to_dict(),
            "confidence": self.confidence,
            "description": self.description
        }
