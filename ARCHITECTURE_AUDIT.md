# Vigil Architecture Audit - Security Separation Analysis
**Date**: January 6, 2026  
**Scope**: Verify clean separation between Vigil (control plane) and AgentShield (data plane)

## Executive Summary

### ❌ CRITICAL VIOLATIONS FOUND

The current architecture **FAILS** the fundamental security requirement:

> **"AgentShield is the ONLY place where plaintext data, prompts, or model weights may ever exist. Vigil must be provably incapable of accessing plaintext AI data."**

### Violations Breakdown

| Violation | Severity | Location | Impact |
|-----------|----------|----------|--------|
| **Vigil inspects full plaintext prompts** | 🔴 CRITICAL | `src/vigil/local_server.py:740-767` | Loses TEE trust model |
| **Vigil normalizes user content** | 🔴 CRITICAL | `src/vigil/local_server.py:741-743` | Direct content manipulation |
| **Vigil performs semantic analysis** | 🔴 CRITICAL | `vigil_enhanced_server.py:700+` | Reads sensitive content |
| **Vigil holds LLM API keys** | 🔴 CRITICAL | `src/vigil/local_server.py:1053` | Secrets in control plane |
| **Vigil makes LLM calls directly** | 🔴 CRITICAL | `src/vigil/local_server.py:1069-1077` | Model execution in wrong layer |
| **Vigil logs may contain content** | 🟡 HIGH | Multiple files | Potential PII exposure |

---

## Detailed Findings

## 1. ❌ Vigil Inspects Full Plaintext Prompts

### Current Code (VIOLATION)
**File**: `src/vigil/local_server.py:740-767`

```python
# [STEP 1] Normalize potential obfuscation before scanning
normalized_contents = []
for msg in messages:
    if isinstance(msg, dict) and 'content' in msg and isinstance(msg['content'], str):
        normalized = _normalize_text(msg['content'])  # ❌ READS PLAINTEXT
        msg['content'] = normalized                    # ❌ MODIFIES PLAINTEXT
        normalized_contents.append(normalized)

# [STEP 2] Vector Threat Scan - Embedding + VRAM Search
try:
    combined_input = " ".join([content for content in normalized_contents if content])
    if combined_input:
        vector_scan_results = vector_engine.scan(combined_input)  # ❌ SEMANTIC ANALYSIS
```

**What's Wrong**:
- Vigil directly reads `msg['content']` (user prompts)
- Vigil normalizes/transforms plaintext
- Vigil performs vector embedding analysis on full content
- Vigil joins all messages into `combined_input` string

**Auditor Questions This Fails**:
- ✅ "Can Vigil read prompts if compromised?" → **YES (FAILS)**
- ✅ "Are logs metadata-only?" → **NO (FAILS)** - content flows through code
- ✅ "Is traffic encrypted end-to-end into enclave?" → **NO (FAILS)** - decrypted at Vigil

---

## 2. ❌ Vigil Holds and Uses LLM API Keys

### Current Code (VIOLATION)
**File**: `src/vigil/local_server.py:1053-1077`

```python
# SAAS LLM FORWARDING - Step 4: Acquire secret via AgentShield (mandatory)
try:
    secret = agentshield.acquire_secret(decision_token=decision_token, action="chat.completion")
    llm_api_key = secret.get('api_key')           # ❌ VIGIL RECEIVES PLAINTEXT API KEY
    llm_endpoint = secret.get('endpoint', 'https://api.openai.com/v1/chat/completions')
    llm_model = secret.get('model') or body.get('model', 'gpt-4')
except Exception as e:
    return jsonify({"error": {"message": "AgentShield secret acquisition failed"}}), 503

# SAAS LLM CALL - Step 5: Forward to LLM with Tenant's Key
llm_headers = {
    "Authorization": f"Bearer {llm_api_key}",     # ❌ VIGIL USES API KEY
    "Content-Type": "application/json"
}

llm_response = requests.post(                     # ❌ VIGIL MAKES MODEL CALL
    llm_endpoint,
    json=llm_body,
    headers=llm_headers,
    timeout=60.0
)
```

**What's Wrong**:
- Vigil receives plaintext LLM API keys from AgentShield
- Vigil stores API keys in memory (`llm_api_key` variable)
- Vigil makes direct HTTP calls to LLM providers
- Vigil handles model responses

**What Rule Says**:
> ❌ Hold API keys or long-lived secrets  
> ❌ Execute model calls

---

## 3. ❌ Vigil Performs Semantic Content Analysis

### Current Code (VIOLATION)
**File**: `vigil_enhanced_server.py` (multiple locations)

```python
# Vigil performs deep semantic analysis
def check_capability_violations(text: str) -> Dict[str, List[str]]:
    violations: Dict[str, List[str]] = {}
    # ... analyzes prompt content ...

# Vigil computes embeddings
EMBEDDING_MODEL = SentenceTransformer(...)
embedding = vector_engine.embed(combined_input)  # ❌ SEMANTIC INTERPRETATION

# Vigil does credential extraction detection
def redact_pii(text: str) -> str:              # ❌ INSPECTS SENSITIVE CONTENT
    patterns = [
        (r"\b[\w.-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]"),
        # ... more patterns ...
    ]
```

**What's Wrong**:
- Vigil loads ML models (SentenceTransformer)
- Vigil performs vector embeddings
- Vigil scans for PII patterns
- Vigil interprets semantic meaning

**What Rule Says**:
> ❌ Perform semantic interpretation of sensitive content

---

## 4. 🟡 Vigil Logs May Contain User Content

### Risk Assessment
**File**: Multiple locations

```python
# Potential logging risks (not observed directly, but data flows through)
logger.info(f"Processing request: {request_id}")  # OK
# But data is in scope, risk of accidental logging
```

**What Auditors Will Check**:
- ✅ "Are logs metadata-only?" → **CANNOT PROVE** - content is in memory

---

## Correct Architecture (MUST DO)

### Clean Split: Control Plane vs Data Plane

```
┌─────────────────────────────────────────────────────────────────┐
│                         VIGIL (Control Plane)                    │
│  ✅ CAN DO:                                                      │
│    - IAM (Okta, Azure AD, SAML)                                 │
│    - RBAC/ABAC decisions                                        │
│    - Policy compilation & signing                               │
│    - TLS termination (metadata only)                            │
│    - Rate limiting                                              │
│    - Request routing & tagging                                  │
│    - Budget pre-checks (token COUNT, not content)               │
│                                                                  │
│  ❌ MUST NOT DO:                                                │
│    - Read msg['content']                                        │
│    - Normalize/transform prompts                                │
│    - Perform embeddings/semantic analysis                       │
│    - Hold LLM API keys                                          │
│    - Make model calls                                           │
│    - Log user content                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Encrypted Envelope
                              │ (Vigil cannot decrypt)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTSHIELD (Data Plane / TEE)                │
│  ✅ ONLY PLACE FOR:                                             │
│    - Decrypting request envelopes                               │
│    - Reading plaintext prompts                                  │
│    - Semantic content analysis                                  │
│    - Threat detection (injection, jailbreak)                    │
│    - Holding LLM API keys (in vault)                            │
│    - Making model calls                                         │
│    - Processing model responses                                 │
│    - PII redaction                                              │
│                                                                  │
│  🔒 TEE GUARANTEES:                                             │
│    - Code attestation (PCR validation)                          │
│    - Memory encryption                                          │
│    - No debugging/introspection                                 │
│    - Audit log integrity                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Required Changes

### Priority 1: Remove Plaintext Access from Vigil

#### Change 1: Envelope Encryption
**File**: `src/vigil/local_server.py`

```python
# BEFORE (❌ WRONG)
messages = body.get('messages', [])
normalized = _normalize_text(msg['content'])  # ❌ Vigil reads content

# AFTER (✅ CORRECT)
# Vigil NEVER decrypts the envelope
encrypted_envelope = {
    "ciphertext": encrypt_for_enclave(body),  # Only AgentShield can decrypt
    "metadata": {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "estimated_tokens": estimate_from_size(body),  # Size-based estimate
        "policy_hash": policy_hash
    }
}
# Forward encrypted envelope to AgentShield
decision = agentshield.verify_encrypted_request(encrypted_envelope)
```

#### Change 2: Token Estimation Without Content
**Current**: Vigil calls `token_meter.count_message_tokens(messages, model)` which reads content

**Required**: Size-based estimation only
```python
# ✅ Estimate tokens from payload size, not content
estimated_tokens = len(request.data) // 4  # Rough heuristic: 1 token ≈ 4 bytes
# OR use Content-Length header
estimated_tokens = int(request.headers.get('Content-Length', 0)) // 4
```

#### Change 3: Move Semantic Analysis to AgentShield
**Current**: Vigil does `vector_engine.scan(combined_input)`

**Required**: AgentShield does all content analysis
```python
# In AgentShield (inside TEE):
def verify_request(encrypted_envelope):
    plaintext = decrypt(encrypted_envelope['ciphertext'])
    messages = plaintext['messages']
    
    # ✅ NOW we can read content (inside TEE)
    combined_input = " ".join([msg['content'] for msg in messages])
    
    # Semantic analysis
    vector_scan = vector_engine.scan(combined_input)
    pii_scan = detect_pii(combined_input)
    injection_scan = detect_injection(combined_input)
    
    return {
        "decision": "ALLOW" | "BLOCK",
        "risk_score": 0.0,
        "threats": []
    }
```

#### Change 4: Move LLM Calls to AgentShield
**Current**: Vigil makes `requests.post(llm_endpoint, ...)`

**Required**: AgentShield makes all model calls
```python
# In AgentShield (inside TEE):
def execute_llm_call(decision_token, encrypted_request):
    # Decrypt to get plaintext messages
    plaintext = decrypt(encrypted_request)
    
    # Get API key from secure vault (never leaves TEE)
    api_key = vault.get_secret(f"tenant_{tenant_id}_api_key")
    
    # Make LLM call
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "gpt-4", "messages": plaintext['messages']}
    )
    
    # Scan output before returning
    output_scan = scan_output(response.json())
    
    # Return encrypted response
    return encrypt_for_client(response.json())
```

---

### Priority 2: Policy Distribution Changes

#### Current Problems
- Policies reference prompt content
- Vigil needs to parse policies to route

#### Required Changes
**File**: `src/vigil/local_server.py`

```python
# BEFORE (❌)
def check_policy(prompt_text):
    # Vigil evaluates policy against prompt
    for rule in policy_rules:
        if rule.matches(prompt_text):  # ❌ Reads content
            return "BLOCK"

# AFTER (✅)
# Vigil only compiles and signs policies, never evaluates against content
def distribute_policy():
    policy_bundle = {
        "rules": load_from_git(),
        "version": 123,
        "hash": sha256(rules)
    }
    # Sign with Vigil's key
    signature = sign(policy_bundle)
    
    # Send to AgentShield for evaluation
    agentshield.update_policy(policy_bundle, signature)
```

---

### Priority 3: Logging & Observability

#### Current Risk
Variables like `combined_input`, `msg['content']` exist in Vigil's memory

#### Required Changes
```python
# ❌ NEVER log in Vigil
logger.info(f"Processing: {combined_input}")  # FORBIDDEN

# ✅ Metadata-only logging
logger.info(f"Request: id={request_id}, tenant={tenant_id}, tokens_est={estimated_tokens}")

# ✅ AgentShield logs (inside TEE, with audit integrity)
agentshield_logger.info(f"Threat detected: type=injection, risk=0.9, prompt_hash={sha256(prompt)}")
```

---

## Compliance Checklist

### Auditor Questions - Current State

| Question | Current Answer | Target Answer |
|----------|----------------|---------------|
| Can Vigil read prompts if compromised? | ❌ YES | ✅ NO |
| Are logs metadata-only? | ❌ NO | ✅ YES |
| Are policies signed before enclave delivery? | 🟡 PARTIAL | ✅ YES |
| Is traffic encrypted end-to-end into enclave? | ❌ NO | ✅ YES |
| Can Vigil be bypassed? | ❌ YES | ✅ NO |
| Does Vigil hold secrets? | ❌ YES | ✅ NO |
| Does Vigil execute model calls? | ❌ YES | ✅ NO |

---

## Implementation Roadmap

### Phase 1: Immediate (Week 1)
1. ✅ Remove all `msg['content']` access from Vigil
2. ✅ Remove vector embedding from Vigil
3. ✅ Remove PII detection from Vigil
4. ✅ Switch to size-based token estimation

### Phase 2: Core Changes (Week 2-3)
5. ✅ Implement envelope encryption
6. ✅ Move semantic analysis to AgentShield
7. ✅ Move LLM calls to AgentShield
8. ✅ Implement secure vault in AgentShield

### Phase 3: Verification (Week 4)
9. ✅ Audit all log statements
10. ✅ Code review: search for ANY content access
11. ✅ Penetration test: try to exfiltrate prompts via Vigil
12. ✅ Formal verification: prove Vigil cannot decrypt

---

## Code Locations Requiring Changes

### Files to Modify

| File | Lines | Change Required |
|------|-------|-----------------|
| `src/vigil/local_server.py` | 740-767 | Remove content normalization |
| `src/vigil/local_server.py` | 704 | Remove `count_message_tokens` (reads content) |
| `src/vigil/local_server.py` | 1053-1077 | Remove LLM API key handling |
| `src/vigil/local_server.py` | 1069-1077 | Remove direct LLM calls |
| `vigil_enhanced_server.py` | 700+ | Remove capability check on content |
| `vigil_enhanced_server.py` | ~800 | Remove PII redaction function |
| `src/vigil/agentshield_client.py` | 282 | Change to encrypted envelope |
| `src/vigil/agentshield_client.py` | 710-865 | Move secret acquisition to enclave |

### Files to Create

| File | Purpose |
|------|---------|
| `src/vigil/envelope_crypto.py` | Encrypt requests for AgentShield |
| `services/agentshield/content_analyzer.py` | Move all semantic analysis here |
| `services/agentshield/llm_executor.py` | LLM call handling in TEE |
| `services/agentshield/vault.py` | Secure key storage |

---

## Risk Assessment

### If Not Fixed

| Risk | Probability | Impact | Mitigation Status |
|------|-------------|--------|-------------------|
| Regulator rejection | HIGH | CRITICAL | ❌ Not mitigated |
| Loss of TEE credibility | HIGH | CRITICAL | ❌ Not mitigated |
| Cannot claim "OPAQUE-level" | CERTAIN | CRITICAL | ❌ Not mitigated |
| Data breach via Vigil compromise | MEDIUM | HIGH | ❌ Not mitigated |
| PII exposure in logs | MEDIUM | HIGH | 🟡 Partial (redact_pii) |

### After Fix

| Risk | Probability | Impact | Mitigation Status |
|------|-------------|--------|-------------------|
| All above | LOW | N/A | ✅ Cryptographically mitigated |

---

## Conclusion

**Current Architecture: ❌ FAILS REQUIREMENTS**

The Vigil repository currently violates the core security principle by:
1. Reading plaintext prompts
2. Performing semantic analysis on content
3. Holding LLM API keys
4. Making model calls directly

**Required Action**: Implement envelope encryption and move ALL content processing to AgentShield (TEE).

**Timeline**: 4 weeks to full compliance  
**Effort**: ~3 engineer-weeks of refactoring  
**Risk**: Until fixed, cannot claim TEE security model
