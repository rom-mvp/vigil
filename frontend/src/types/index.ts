export interface AuditLog {
  id: string;
  timestamp: string;
  agent_id: string;
  tenant_id: string;
  status: string;
  endpoint: string;
  signature_hash: string;
  classifier_labels?: string[];
  classifier_verdict?: string;
  scanner_verdict?: string;
  poisoning_detected?: boolean;
  sbom_verified?: boolean;
  details?: Record<string, unknown>;
}

export interface Activity {
  timestamp: string;
  event_type: string;
  description: string;
  severity: string;
}

export interface Policy {
  version: string;
  rules: unknown;
  effective_date: string;
}
