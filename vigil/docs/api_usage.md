## Vigil API Usage Guide

This guide walks through the endpoints Vigil calls so you can stub or secure them in lower environments. All requests originate from the browser and therefore must be CORS-enabled.

### Base URLs via `ENV_CONFIG`

`web/index.html` defines an `ENV_CONFIG` object that maps short environment names (`local`, `staging`, `prod`) to concrete service URLs. When the operator changes the environment selector, Vigil stores the choice in `localStorage` and reuses the matching base URLs for every fetch.

```js
const ENV_CONFIG = {
  staging: {
    AUDIT_API: "https://staging-audit.agentshield.yourdomain.com",
    POLICY_API: "https://staging-policy.agentshield.yourdomain.com",
    IDENTITY_API: "https://staging-identity.agentshield.yourdomain.com",
    PROTOCOL_API: "https://staging-protocol.agentshield.yourdomain.com",
    BILLING_API: "https://staging-billing.agentshield.yourdomain.com",
  },
  // prod, local...
};
```

Each loader function simply calls `getBaseUrl(serviceName)` to build its absolute URL, ensuring all tabs honor the same environment switch.

### Analytics Panels & Endpoints

| Panel     | Function        | Endpoint Pattern                                             | Notes |
|-----------|-----------------|--------------------------------------------------------------|-------|
| Overview  | `loadOverview()`| `${AUDIT_API}/api/overview`                                  | Returns gateway stats and the event feed (`recent_events`). |
| Policies  | `loadPolicies()`| `${POLICY_API}/tenants/${tenantId}/policies`                 | Tenant-scoped; POST in `openCreatePolicyModal()` uses the same route. |
| Agents    | `loadAgents()`  | `${IDENTITY_API}/tenants/${tenantId}/agents`                 | Supports creation via POST in `openCreateAgentModal()`. |
| Billing   | `loadBilling()` | `${BILLING_API}/tenants/${tenantId}/billing`                 | Supplies usage totals, invoice forecast, quota objects, and breakdown arrays. |
| Network   | `loadNetwork()` | `${PROTOCOL_API}/trust-graph`                               | No tenant id required; returns cross-tenant trust edges. |

All responses are rendered directly after escaping HTML. Errors are logged to the console; Billing additionally shows a friendly placeholder that reminds operators to configure the Billing API host.

### Audit / Analytics Data Fetching

- `loadOverview()` issues a GET to `AUDIT_API/api/overview`.
  - Expected response shape:
    ```json
    {
      "stats": {
        "total_requests": 12034,
        "blocked_attacks": 37,
        "redacted_events": 92
      },
      "recent_events": [
        {
          "timestamp": "2025-11-20T18:22:03Z",
          "tenant_id": "acme-prod",
          "agent_id": "support-bot",
          "phase": "response",
          "blocked": false,
          "pii_event_count": 0
        }
      ]
    }
    ```
  - Vigil maps the stats into the hero cards and the array into the table. Missing values are displayed as `—`.

- `loadBilling()` extends analytics into commercial data by calling the `BILLING_API`. The JSON payload should include:
  - `monthly_usage` object (`requests`, `tokens`, `runtime_hours`)
  - `estimated_invoice` object (`amount`, `currency`, `due_date`, `notes`)
  - `quota_remaining` with nested `requests` and `spend` objects (`used`, `limit`)
  - `model_breakdown` and `agent_breakdown` arrays with `{ model|agent_id, requests, spend }`
  - optional `plan_features` list and `audit_trail` text

### Environment Playbook

1. **Add your API domains** to `ENV_CONFIG` before shipping to staging or production.
2. **Enable CORS** for the Vigil origin; otherwise the browser will block requests even if the URLs are correct.
3. **Secure Billing** by only exposing tenant-scoped data. Vigil already respects RBAC (Viewer and Tenant Admin can see billing; Developer cannot), but the backend should also enforce scopes.
4. **Instrument the analytics APIs** with pagination or filtering if needed; Vigil currently displays the latest page of data, so high-volume tenants may require server-side limits.
