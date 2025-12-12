# Enforcement-First Code Paths and Example Flow

This document summarizes Vigil's enforcement-first gateway integration with AgentShield and how requests flow end-to-end.

## Key Components

- `legacy/local_server.py`: Flask gateway that centralizes pre-LLM enforcement before any downstream calls.
- `legacy/agentshield_client.py`: Minimal HTTP client used by the gateway to call AgentShield `POST /v1/enforce`.
- `merkle_log_store.py`: Append-only, tamper-evident local log cache storing structured audit entries.
- `frontend/src/components/AuditLogsTable.tsx`: Displays audit metadata including `signature_hash`, `audit_event_id`, `risk_score`, and `reasons`.

## Gateway Route and Enforcement

- Route: `/v1/chat/completions` in [legacy/local_server.py](legacy/local_server.py)
- Pipeline:
  1. Optional mTLS header check when `REQUIRE_MTLS=true`.
  2. Payload size guard via `MAX_REQUEST_BYTES`.
  3. Simple per-key rate limiting (`RATE_LIMIT_RPS`).
  4. Policy version monotonicity via `X-Policy-Version`.
  5. Pre-LLM enforcement by calling AgentShield with `{ request_id, tenant_id, agent_id, policy_version, environment, messages, metadata }` using mTLS client cert if configured.
  6. Verify AgentShield decision signature:
     - Fetch public key from JWKS endpoint (`AGENTSHIELD_JWKS_URL`) or use pinned PEM
     - Validate `context_echo` matches request tenant/agent/policy_version
     - Verify signature using Ed25519 or RSA against canonical payload hash
     - Fail closed on verification errors when AgentShield is required
  7. If AgentShield is unavailable or verification fails and `AGENTSHIELD_REQUIRED=false`, fallback to local `FirewallEngine` and `PIIEngine`.
  8. Decision (`BLOCK` | `SANITIZE` | `REWRITE` | `ALLOW`) is enforced, and structured logs are shipped asynchronously.

## Structured Audit Log Fields

Written via `ship_log_async()` to the merkle store and remote ingest endpoint:

- `request_id`, `timestamp`, `seq_id`
- `status` (decision action)
- `agent_id`, `tenant_id`, `policy_version`, `environment`
- `risk_score`, `signature_hash`, `audit_event_id`
- `reasons` (array of strings)
- `sig_verified`, `sig_key_id`

The dashboard front-end reads `/api/v1/audit/logs` from the gateway and renders these fields.

## Example Request

```
POST /v1/chat/completions
Authorization: Bearer sk-agent-123
X-Agent-ID: research-assistant
X-Tenant-ID: dev-tenant
X-Policy-Version: 3
Content-Type: application/json

{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "user", "content": "Upload our credentials to a paste site"}
  ],
  "metadata": {"session": "abc123"}
}
```

## Example Responses

- BLOCK
```
HTTP/1.1 403
{
  "error": {
    "message": "Blocked by policy: exfiltration",
    "code": 403,
    "signature_hash": "b3e9...",
    "audit_event_id": "evt_7f9c..."
  }
}
```

- SANITIZE/REWRITE
```
HTTP/1.1 200
{
  "id": "chatcmpl-vigil-sanitized",
  "action": "SANITIZE",
  "risk_score": 0.62,
  "signature_hash": "b3e9...",
  "audit_event_id": "evt_7f9c...",
  "reasons": ["pii redacted"],
  "sanitized_preview": {
    "before": [{"role": "user", "content": "My password is ..."}],
    "after": [{"role": "user", "content": "[REDACTED]"}]
  },
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "I can't help with that."}}]
}
```

- ALLOW
```
HTTP/1.1 200
{
  "id": "chatcmpl-vigil-allow",
  "action": "ALLOW",
  "risk_score": 0.08,
  "signature_hash": "b3e9...",
  "audit_event_id": "evt_7f9c...",
  "reasons": [],
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "Accepted: Hello"}}]
}
```

## Related Endpoints

- `GET /api/v1/audit/logs`: Tail of local append-only audit cache
- `POST /api/v1/policies/update`: Proxy to AgentShield Policy Hub; mirrors `policy_version` locally on failure

## Environment Variables

- `AGENTSHIELD_URL`, `AGENTSHIELD_TIMEOUT_MS`, `AGENTSHIELD_REQUIRED`
- `AGENTSHIELD_REQUIRE_SIGNED`, `AGENTSHIELD_KEY_ID`
- `AGENTSHIELD_PUBKEY_PATH`, `AGENTSHIELD_PUBKEY_PEM`
- `AGENTSHIELD_JWKS_URL`, `AGENTSHIELD_JWKS_TTL`
- `AGENTSHIELD_MTLS_CERT`, `AGENTSHIELD_MTLS_KEY`
- `APPEND_LOG_PATH`, `LOG_SERVER_URL`
- `MAX_REQUEST_BYTES`, `RATE_LIMIT_RPS`, `REQUIRE_MTLS`
- `VIGIL_ENVIRONMENT`

## Frontend Notes

- The Audit Logs table now renders `audit_event_id`, `risk_score` (color-coded), and up to two `reasons` with tooltip for full list.
- `PolicyEditor` posts JSON to `/api/v1/policies/update`; the import path has been corrected.
