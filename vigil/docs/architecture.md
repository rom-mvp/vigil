## Vigil Architecture

Vigil is a single-page console that talks directly to AgentShield services. There is no custom backend; the browser loads `web/index.html`, renders Tailwind UI components, and issues cross-origin requests to the Gateway surface APIs you configure.

### High-Level Components

1. **Header controls**
   - Environment dropdown (`env-select`) chooses one of the presets declared in `ENV_CONFIG`.
   - Tenant input (`tenant-input`) scopes every API call by embedding the chosen tenant id in each route (e.g., `/tenants/<tenantId>/policies`).
   - Role dropdown (`role-select`) is a purely client-side RBAC simulator that toggles what tabs and actions the operator can access. It helps customer teams rehearse Viewer/Developer/Admin personas without reloading the app.

2. **Analytics panels**
   - **Overview tab** shows runtime telemetry: total gateway requests, blocked attacks, PII interventions, and the live event grid. It calls `AUDIT_API/api/overview` and expects a shape `{ stats, recent_events }`.
   - **Policies tab** lists governance entries for the active tenant, sourced from `POLICY_API/tenants/<tenantId>/policies`.
   - **Agents tab** surfaces identity service data from `IDENTITY_API/tenants/<tenantId>/agents`, and allows creation when RBAC permits.
   - **Billing tab** (Phase E) consolidates spend KPIs: monthly usage, invoice forecast, quota burn-down, and breakdowns by model and agent. It calls `BILLING_API/tenants/<tenantId>/billing`.
   - **Network tab** visualizes the protocol/trust graph fetched from `PROTOCOL_API/trust-graph`.

3. **RBAC overlay**
   - `RBAC_MATRIX` inside `index.html` defines what each role can view or mutate (`canManagePolicies`, `canManageAgents`, `canViewBilling`).
   - `applyRbacState()` hides tabs or disables buttons as needed, ensuring low-privilege users see read-only analytics while admins gain full control.

### Data Flow

1. On load, `DOMContentLoaded` hydrates the UI from `localStorage` via `loadConsoleConfig()`. This provides persisted `env`, `tenantId`, and `role`.
2. `ENV_CONFIG` pairs each environment alias (`local`, `staging`, `prod`) with concrete API base URLs:

```js
const ENV_CONFIG = {
  local: {
    AUDIT_API: "http://localhost:8200",
    POLICY_API: "http://localhost:8100",
    IDENTITY_API: "http://localhost:8300",
    PROTOCOL_API: "http://localhost:8400",
    BILLING_API: "http://localhost:8500",
  },
  // staging, prod ...
};
```

3. Whenever the environment or tenant changes, `saveConsoleConfig()` persists the selection and `reloadActiveTab()` refreshes the currently visible panel so analytics always reflect the latest scope.
4. Each loader (`loadOverview`, `loadPolicies`, `loadAgents`, `loadBilling`, `loadNetwork`) pulls data from the corresponding service, sanitizes it with `escapeHtml`, and renders declarative templates.
5. Billing-specific helpers (`updateQuotaWidget`, `renderBreakdownTable`) convert raw usage into UX affordances like progress bars and tables.

### Deployment Considerations

- Because Vigil is static, it can be hosted via any CDN or object store (S3, GCS, Azure Blob) or served locally via `python web/server.py`.
- CORS: make sure each backend service allows requests from the Vigil origin (e.g., `http://localhost:3000` during development).
- Secrets: Vigil never stores API keys beyond the operator’s browser session. Service-to-service authentication is handled on the backend; Vigil only consumes tenant-scoped APIs.
- Testing: `tests/test_guardrails.py` exercises rate-limit detection, quota math, billing rollups, RBAC, and tenant isolation logic to support Phase E readiness.
