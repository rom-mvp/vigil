package vigil.policy

import future.keywords.contains
import future.keywords.if
import future.keywords.in

# Default deny - fail secure
default allow := false
default decision := "BLOCK"
default risk_score := 1.0

# Allow decision with low risk
allow if {
    decision == "ALLOW"
    risk_score < 0.5
}

# Block decision with high risk
block if {
    decision == "BLOCK"
    risk_score >= 0.5
}

# Main decision logic
decision := "ALLOW" if {
    not has_prompt_injection
    not has_pii
    not has_code_execution
    not has_sql_injection
    not has_xss_attempt
}

decision := "BLOCK" if {
    has_prompt_injection
}

decision := "BLOCK" if {
    has_pii
}

decision := "BLOCK" if {
    has_code_execution
}

decision := "BLOCK" if {
    has_sql_injection
}

decision := "BLOCK" if {
    has_xss_attempt
}

# Calculate risk score based on detected threats
risk_score := score if {
    threats := [
        {"detected": has_prompt_injection, "score": 0.95},
        {"detected": has_pii, "score": 0.99},
        {"detected": has_code_execution, "score": 0.95},
        {"detected": has_sql_injection, "score": 0.98},
        {"detected": has_xss_attempt, "score": 0.98}
    ]
    
    detected := [t | t := threats[_]; t.detected]
    count(detected) > 0
    
    # Use highest risk score if multiple threats
    scores := [t.score | t := detected[_]]
    score := max(scores)
}

risk_score := 0.05 if {
    decision == "ALLOW"
}

# Threat detection rules
has_prompt_injection if {
    content := extract_content
    regex.match(`(?i)system:`, content)
}

has_prompt_injection if {
    content := extract_content
    regex.match(`(?i)ignore previous`, content)
}

has_prompt_injection if {
    content := extract_content
    regex.match(`(?i)</system>`, content)
}

has_pii if {
    content := extract_content
    # Credit card pattern (13-19 digits)
    regex.match(`\b[0-9]{13,19}\b`, content)
}

has_pii if {
    content := extract_content
    # SSN pattern (XXX-XX-XXXX)
    regex.match(`\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b`, content)
}

has_xss_attempt if {
    content := extract_content
    regex.match(`(?i)<script>`, content)
}

has_sql_injection if {
    content := extract_content
    regex.match(`(?i)DROP\s+TABLE`, content)
}

has_code_execution if {
    content := extract_content
    regex.match(`(?i)exec\s*\(`, content)
}

# Extract content from messages
extract_content := content if {
    messages := input.messages
    is_array(messages)
    contents := [m.content | m := messages[_]; m.content]
    content := concat(" ", contents)
}

extract_content := "" if {
    not input.messages
}

# Reasons for decision
reasons := reasons_list if {
    threats := []
    threats_with_prompt := array.concat(threats, ["prompt-injection-system"] if has_prompt_injection else [])
    threats_with_pii := array.concat(threats_with_prompt, ["pii-detected"] if has_pii else [])
    threats_with_code := array.concat(threats_with_pii, ["code-execution"] if has_code_execution else [])
    threats_with_sql := array.concat(threats_with_code, ["sql-injection"] if has_sql_injection else [])
    threats_with_xss := array.concat(threats_with_sql, ["xss-attempt"] if has_xss_attempt else [])
    
    count(threats_with_xss) > 0
    reasons_list := threats_with_xss
}

reasons := ["clean"] if {
    decision == "ALLOW"
}

# Tenant and environment validation
valid_tenant if {
    input.tenant_id
    input.tenant_id != ""
}

valid_environment if {
    input.environment
    input.environment in ["production", "staging", "development", "test"]
}

# Context validation for request integrity
valid_request if {
    input.request_id
    input.request_id != ""
    valid_tenant
}

# Policy version check
policy_version := "v1.0.0"

# Final enforcement decision
enforcement_decision := {
    "action": decision,
    "risk_score": risk_score,
    "reasons": reasons,
    "policy_version": policy_version,
    "timestamp": time.now_ns()
}
