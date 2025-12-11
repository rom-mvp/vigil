-- Vigil Database Schema for AgentShield v2.0
-- Enhanced with semantic classification, scanner pipeline, data registry, and supply chain fields

-- Drop existing tables if recreating
-- DROP TABLE IF EXISTS events CASCADE;
-- DROP TABLE IF EXISTS alerts CASCADE;

-- Main events table with extended schema
CREATE TABLE IF NOT EXISTS events (
    -- Core fields
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    agent_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('ALLOWED', 'BLOCKED', 'MODIFIED', 'WARN')),
    
    -- Request metadata
    tenant_id VARCHAR(255),
    request_id VARCHAR(255),
    endpoint VARCHAR(500),
    latency_ms INTEGER,
    model_used VARCHAR(100),
    
    -- Legacy fields
    details JSONB DEFAULT '{}',
    reason TEXT,
    
    -- Semantic Classification (IntentClassifier)
    classifier_labels TEXT[] DEFAULT '{}',
    classifier_scores JSONB DEFAULT '{}',
    classifier_verdict VARCHAR(50) CHECK (classifier_verdict IN ('SAFE', 'SUSPICIOUS', 'MALICIOUS')),
    
    -- Scanner Pipeline
    scanner_verdict VARCHAR(50) CHECK (scanner_verdict IN ('PASS', 'WARN', 'BLOCK')),
    scanner_confidence DECIMAL(3,2) CHECK (scanner_confidence >= 0 AND scanner_confidence <= 1),
    scanner_modules_failed TEXT[] DEFAULT '{}',
    scanner_detections JSONB DEFAULT '{}',
    
    -- Data Registry (DataRegistry hooks)
    dataset_id VARCHAR(255),
    model_id VARCHAR(255),
    poisoning_detected BOOLEAN DEFAULT FALSE,
    dp_enforced BOOLEAN DEFAULT FALSE,
    watermark_verified BOOLEAN DEFAULT FALSE,
    
    -- Supply Chain
    sbom_verified BOOLEAN DEFAULT FALSE,
    component_hash VARCHAR(64),
    component_version VARCHAR(50),
    
    -- Indexes for fast queries
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_agent_id ON events(agent_id);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
CREATE INDEX IF NOT EXISTS idx_events_tenant_id ON events(tenant_id);

-- New AgentShield v2.0 indexes
CREATE INDEX IF NOT EXISTS idx_classifier_labels ON events USING GIN (classifier_labels);
CREATE INDEX IF NOT EXISTS idx_classifier_verdict ON events(classifier_verdict);
CREATE INDEX IF NOT EXISTS idx_scanner_verdict ON events(scanner_verdict);
CREATE INDEX IF NOT EXISTS idx_scanner_confidence ON events(scanner_confidence);
CREATE INDEX IF NOT EXISTS idx_poisoning_detected ON events(poisoning_detected) WHERE poisoning_detected = TRUE;
CREATE INDEX IF NOT EXISTS idx_sbom_verified ON events(sbom_verified);
CREATE INDEX IF NOT EXISTS idx_component_hash ON events(component_hash);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_classifier_high_confidence ON events(classifier_verdict, timestamp DESC) 
    WHERE classifier_verdict IN ('SUSPICIOUS', 'MALICIOUS');
CREATE INDEX IF NOT EXISTS idx_scanner_blocks ON events(scanner_verdict, timestamp DESC) 
    WHERE scanner_verdict = 'BLOCK';

-- Alerts table for high-priority threats
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(255) UNIQUE NOT NULL,
    alert_type VARCHAR(100) NOT NULL CHECK (alert_type IN (
        'jailbreak', 'exfiltration', 'coercion', 'poisoning', 'sbom_failure', 
        'watermark_failure', 'repeated_offense', 'other'
    )),
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    confidence DECIMAL(3,2) CHECK (confidence >= 0 AND confidence <= 1),
    description TEXT,
    
    -- Related event
    event_id INTEGER REFERENCES events(id),
    agent_id VARCHAR(255),
    dataset_id VARCHAR(255),
    model_id VARCHAR(255),
    component VARCHAR(255),
    
    -- Alert metadata
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(255),
    acknowledged_at TIMESTAMP,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Alert indexes
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alerts(resolved) WHERE resolved = FALSE;
CREATE INDEX IF NOT EXISTS idx_alerts_agent ON alerts(agent_id);

-- Analytics summary table (materialized view for performance)
CREATE TABLE IF NOT EXISTS analytics_summary (
    id SERIAL PRIMARY KEY,
    metric_type VARCHAR(100) NOT NULL,
    metric_name VARCHAR(255) NOT NULL,
    metric_value JSONB NOT NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(metric_type, metric_name, period_start)
);

CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_summary(metric_type);
CREATE INDEX IF NOT EXISTS idx_analytics_period ON analytics_summary(period_start DESC);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for automatic timestamp updates
CREATE TRIGGER update_events_updated_at BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_alerts_updated_at BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Sample query views for common analytics

-- High-confidence jailbreak attempts
CREATE OR REPLACE VIEW high_confidence_jailbreaks AS
SELECT 
    id,
    timestamp,
    agent_id,
    classifier_labels,
    classifier_scores,
    scanner_verdict,
    status
FROM events
WHERE 
    'jailbreak' = ANY(classifier_labels)
    AND (classifier_scores->>'jailbreak')::FLOAT > 0.9
ORDER BY timestamp DESC;

-- Data poisoning events
CREATE OR REPLACE VIEW poisoning_events AS
SELECT 
    id,
    timestamp,
    dataset_id,
    model_id,
    agent_id,
    status
FROM events
WHERE poisoning_detected = TRUE
ORDER BY timestamp DESC;

-- SBOM verification failures
CREATE OR REPLACE VIEW sbom_failures AS
SELECT 
    id,
    timestamp,
    component_hash,
    component_version,
    agent_id
FROM events
WHERE sbom_verified = FALSE
ORDER BY timestamp DESC;

-- Scanner verdict summary (last 24h)
CREATE OR REPLACE VIEW scanner_verdict_24h AS
SELECT 
    scanner_verdict,
    COUNT(*) as count,
    AVG(scanner_confidence) as avg_confidence
FROM events
WHERE 
    timestamp > NOW() - INTERVAL '24 hours'
    AND scanner_verdict IS NOT NULL
GROUP BY scanner_verdict;

-- Comments for documentation
COMMENT ON TABLE events IS 'Main audit events table with AgentShield v2.0 semantic, scanner, registry, and supply chain fields';
COMMENT ON TABLE alerts IS 'High-priority security alerts requiring attention';
COMMENT ON COLUMN events.classifier_labels IS 'Array of detected intent labels: jailbreak, exfiltration, coercion';
COMMENT ON COLUMN events.classifier_scores IS 'JSON object with confidence scores for each label';
COMMENT ON COLUMN events.scanner_verdict IS 'Scanner pipeline decision: PASS, WARN, or BLOCK';
COMMENT ON COLUMN events.poisoning_detected IS 'Boolean flag for data poisoning detection';
COMMENT ON COLUMN events.sbom_verified IS 'Boolean flag for SBOM signature verification';
