# Vigil Integration with AgentShield v2.0

## Overview

This document details the Vigil updates to support AgentShield v2.0's enhanced security telemetry, including semantic classification, scanner pipeline analytics, data governance tracking, and supply chain integrity monitoring.

## New Capabilities

### 1. Semantic Threat Detection
- **Intent Classification**: Tracks jailbreak, exfiltration, and coercion attempts
- **Confidence Scoring**: Monitors classifier confidence levels (0.0-1.0)
- **Verdict Tracking**: Records SAFE/SUSPICIOUS/MALICIOUS verdicts
- **Real-time Alerts**: Triggers on high-confidence threats (> 0.9)

### 2. Scanner Pipeline Analytics
- **Verdict Distribution**: PASS/WARN/BLOCK statistics
- **Module Performance**: Tracks which scanner modules are triggering
- **Confidence Analysis**: Monitors scanner confidence levels
- **Detection Details**: Captures full scanner output for forensics

### 3. Data Governance
- **Poisoning Detection**: Flags compromised datasets
- **Differential Privacy**: Tracks DP enforcement (epsilon monitoring)
- **Watermarking**: Verifies model watermarks
- **Dataset Registry**: Links events to specific datasets and models

### 4. Supply Chain Integrity
- **SBOM Verification**: Validates component signatures
- **Version Tracking**: Monitors component versions and git hashes
- **Vulnerability Detection**: Flags outdated or vulnerable components
- **Component Health**: Tracks overall supply chain status

## Files Added/Modified

### New Files

#### `models.py`
Extended data models for AgentShield v2.0:
```python
- AuditEvent: Extended with semantic, scanner, registry, supply_chain fields
- SemanticClassification: Classifier results structure
- ScannerPipeline: Scanner verdict and detection details
- DataRegistry: Data governance fields
- SupplyChain: SBOM and component tracking
- ThreatAlert: High-priority alert structure
```

#### `schema.sql`
PostgreSQL database schema with:
- Extended `events` table with all new fields
- Indexed columns for performance (GIN, partial indexes)
- `alerts` table for threat tracking
- Materialized views for analytics
- Helper views (high_confidence_jailbreaks, poisoning_events, etc.)

#### `vigil-alerts.yaml`
Alert configuration covering:
- Semantic threats (jailbreak, exfiltration, coercion)
- Scanner anomalies
- Data governance violations
- Supply chain failures
- Auto-remediation rules
- Alert routing (email, Slack, PagerDuty)

#### `dashboard_v2.html`
Enhanced dashboard featuring:
- Six-tab interface (Overview, Semantic, Scanner, Governance, Supply Chain, Alerts)
- Real-time charts (Chart.js integration)
- Threat severity visualization
- Component health monitoring
- Alert management interface

### Modified Files

#### `dashboard_server.py`
Added API endpoints:
```
GET /api/analytics/classifier
  → Semantic classification breakdown

GET /api/analytics/scanner-pipeline
  → Scanner verdict distribution

GET /api/analytics/registry-hooks
  → Data governance events

GET /api/analytics/supply-chain
  → SBOM and component status

GET /api/alerts/semantic-threats
  → High-priority threat alerts
```

## Database Schema Changes

### New Columns in `events` Table

```sql
-- Semantic Classification
classifier_labels TEXT[]
classifier_scores JSONB
classifier_verdict VARCHAR(50)

-- Scanner Pipeline
scanner_verdict VARCHAR(50)
scanner_confidence DECIMAL(3,2)
scanner_modules_failed TEXT[]
scanner_detections JSONB

-- Data Registry
dataset_id VARCHAR(255)
model_id VARCHAR(255)
poisoning_detected BOOLEAN
dp_enforced BOOLEAN
watermark_verified BOOLEAN

-- Supply Chain
sbom_verified BOOLEAN
component_hash VARCHAR(64)
component_version VARCHAR(50)
```

### Indexes Added

```sql
CREATE INDEX idx_classifier_labels ON events USING GIN (classifier_labels);
CREATE INDEX idx_scanner_verdict ON events(scanner_verdict);
CREATE INDEX idx_poisoning_detected ON events(poisoning_detected) WHERE poisoning_detected = TRUE;
CREATE INDEX idx_sbom_verified ON events(sbom_verified);
```

## API Endpoints

### Analytics Endpoints

#### Classifier Analytics
```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/analytics/classifier
```

**Response**:
```json
{
  "total_classified": 1847,
  "breakdown": {
    "jailbreak": {
      "count": 42,
      "high_confidence": 15,
      "avg_score": 0.73
    },
    "exfiltration": {...},
    "coercion": {...}
  },
  "trends": {
    "last_hour": {...},
    "last_24h": {...}
  },
  "top_agents": [...]
}
```

#### Scanner Pipeline Analytics
```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/analytics/scanner-pipeline
```

**Response**:
```json
{
  "total_scanned": 2340,
  "verdicts": {
    "PASS": {"count": 2145, "percentage": 91.7},
    "WARN": {"count": 132, "percentage": 5.6},
    "BLOCK": {"count": 63, "percentage": 2.7}
  },
  "failed_modules": {...}
}
```

#### Registry Hooks (Data Governance)
```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/analytics/registry-hooks
```

**Response**:
```json
{
  "governance": {
    "poisoning_detected": {
      "count": 3,
      "severity": "CRITICAL",
      "datasets_affected": [...]
    },
    "dp_enforced": {...},
    "watermark_verified": {...}
  },
  "recent_alerts": [...]
}
```

#### Supply Chain Analytics
```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/analytics/supply-chain
```

**Response**:
```json
{
  "sbom": {
    "total_verifications": 1456,
    "verified": 1442,
    "failed": 14,
    "success_rate": 99.0
  },
  "components": {...},
  "vulnerabilities": [...]
}
```

#### Semantic Threat Alerts
```bash
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:5000/api/alerts/semantic-threats
```

**Response**:
```json
{
  "total_alerts": 25,
  "critical": 8,
  "high": 12,
  "alerts": [
    {
      "alert_id": "alert_1a2b3c",
      "type": "jailbreak",
      "severity": "CRITICAL",
      "confidence": 0.97,
      "description": "High-confidence jailbreak attempt",
      "classifier_scores": {...},
      "action_taken": "BLOCKED"
    }
  ]
}
```

## Alert Rules

### Semantic Threat Alerts

1. **High Confidence Jailbreak**
   - Trigger: `classifier_scores.jailbreak > 0.9`
   - Severity: CRITICAL
   - Actions: Email, Slack, PagerDuty

2. **Exfiltration Attempt**
   - Trigger: `'exfiltration' IN classifier_labels`
   - Severity: HIGH
   - Actions: Email, Slack

3. **Repeated Attacks**
   - Trigger: `> 3 jailbreaks from same agent in 1h`
   - Severity: CRITICAL
   - Auto-remediation: Quarantine agent

### Data Governance Alerts

1. **Data Poisoning Detected**
   - Trigger: `poisoning_detected = true`
   - Severity: CRITICAL
   - Auto-remediation: Quarantine dataset, halt training

2. **Watermark Verification Failed**
   - Trigger: `watermark_verified = false`
   - Severity: HIGH
   - Auto-remediation: Flag model, require reverification

### Supply Chain Alerts

1. **SBOM Verification Failed**
   - Trigger: `sbom_verified = false`
   - Severity: HIGH
   - Auto-remediation: Disable component, revert

2. **Multiple SBOM Failures**
   - Trigger: `> 5 SBOM failures in 1h`
   - Severity: CRITICAL
   - Auto-remediation: Freeze deployments, incident response

## Dashboard Features

### Overview Tab
- Key metrics (requests, blocks, alerts, cost)
- Classifier verdict chart (doughnut)
- Scanner pipeline chart (bar)
- Recent events stream

### Semantic Threats Tab
- Jailbreak/exfiltration/coercion counts
- High-confidence attempt tracking
- Top offending agents
- Confidence score breakdown

### Scanner Pipeline Tab
- PASS/WARN/BLOCK distribution
- Failed module statistics
- Confidence distribution
- Module performance metrics

### Data Governance Tab
- Poisoning detection status
- Differential privacy metrics
- Watermark verification stats
- Recent governance alerts

### Supply Chain Tab
- SBOM verification rate
- Component health status
- Active component versions
- Vulnerability tracking

### Alerts Tab
- Severity-based filtering (Critical/High/Medium/Low)
- Detailed alert cards
- Classifier scores visualization
- Action taken status

## Deployment

### 1. Database Setup

```bash
# Create database
createdb vigil_v2

# Apply schema
psql vigil_v2 < schema.sql
```

### 2. Start Dashboard

```bash
# Install dependencies
pip install -r requirements.txt

# Generate API key
python3 generate_api_key.py

# Start dashboard server
docker-compose up -d --build vigil-dashboard
```

### 3. Access Dashboard

```
http://localhost:5000
```

Login with your generated API key (format: `sk-vigil-...`)

### 4. Test Endpoints

```bash
export VIGIL_API_KEY="sk-vigil-your-key-here"

# Test status
curl -H "Authorization: Bearer $VIGIL_API_KEY" \
  http://localhost:5000/api/status

# Test classifier analytics
curl -H "Authorization: Bearer $VIGIL_API_KEY" \
  http://localhost:5000/api/analytics/classifier

# Test threat alerts
curl -H "Authorization: Bearer $VIGIL_API_KEY" \
  http://localhost:5000/api/alerts/semantic-threats
```

## Integration with AgentShield

### Audit Logger Integration

AgentShield's audit logger should POST events to Vigil:

```python
# In AgentShield audit logger
import requests

def send_to_vigil(event: AuditEvent):
    response = requests.post(
        "http://vigil:5000/api/ingest",
        json=event.to_dict(),
        headers={"Authorization": f"Bearer {VIGIL_API_KEY}"}
    )
    return response.ok
```

### Event Format

```json
{
  "timestamp": "2025-12-07T15:42:18Z",
  "agent_id": "agent_7f3a",
  "status": "BLOCKED",
  "classifier_labels": ["jailbreak"],
  "classifier_scores": {
    "jailbreak": 0.97,
    "exfiltration": 0.12
  },
  "classifier_verdict": "MALICIOUS",
  "scanner_verdict": "BLOCK",
  "scanner_confidence": 0.89,
  "poisoning_detected": false,
  "sbom_verified": true,
  "component_hash": "a3f7c2d8e1b4f9a6"
}
```

## Performance Considerations

### Indexing Strategy
- GIN indexes on array fields (classifier_labels)
- Partial indexes on boolean flags (poisoning_detected WHERE true)
- Composite indexes for common query patterns

### Query Optimization
- Materialized views for expensive aggregations
- Time-based partitioning for events table (recommended for > 10M events)
- Caching layer for dashboard metrics (Redis)

### Retention Policy
```sql
-- Archive events older than 90 days
DELETE FROM events WHERE timestamp < NOW() - INTERVAL '90 days';

-- Keep alerts for 365 days
DELETE FROM alerts WHERE created_at < NOW() - INTERVAL '365 days' AND resolved = true;
```

## Monitoring & Observability

### Metrics to Track
1. Alert response times
2. False positive rates
3. Classifier confidence distributions
4. Scanner performance (latency, accuracy)
5. SBOM verification success rates

### Dashboards
- Executive: High-level security posture
- SOC: Real-time threat monitoring
- ML Ops: Data governance and model health
- DevSecOps: Supply chain integrity

## Compliance & Reporting

### SOC2 Requirements
- Audit trail: All events logged with timestamps
- Access control: API key authentication
- Data integrity: SBOM verification
- Incident response: Auto-remediation rules

### Reports
- Daily security summary
- Weekly threat intelligence
- Monthly governance report
- Quarterly supply chain audit

## Troubleshooting

### Common Issues

1. **High false positive rate**
   - Adjust classifier thresholds in alerts.yaml
   - Review scanner module configurations

2. **SBOM verification failures**
   - Check component registry is up to date
   - Verify git commit hashes

3. **Slow dashboard loading**
   - Check database index usage
   - Enable query caching
   - Consider materialized views

## Next Steps

- [ ] Implement real event ingestion (vs mock data)
- [ ] Add PostgreSQL/DynamoDB storage layer
- [ ] Configure alert routing (email, Slack, PagerDuty)
- [ ] Set up automated response playbooks
- [ ] Enable SOC2 compliance reporting
- [ ] Deploy to production with AgentShield v2.0

## Support

For issues or questions:
- Documentation: https://docs.vigil.ai
- GitHub: https://github.com/company/vigil
- Email: support@vigil.ai
