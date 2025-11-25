# Vigil

Vigil is the public console and example pack for AgentShield—the trust, policy,
and identity layer for AI agents. Use it to visualize AgentShield telemetry,
inspect tenant policies, manage agent identities, and preview the trust graph
surface as you move through Phase 1–3.

## Run the Vigil console locally

1. Make sure the AgentShield services are running (details below).
2. From the `vigil/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python web/server.py
```

3. Open http://localhost:3000 to view the console. The UI talks directly to:
   - `audit-reporter` (`/api/overview`) for runtime stats
   - `policy-hub` (`/tenants/{id}/policies`)
   - `identity-service` (`/tenants/{id}/agents`)
   - `protocol-hub` (`/trust-graph`)

## Call the AgentShield gateway from your agent

See `examples/python-openai-gateway/main.py` for a minimal `httpx` script that
posts to the AgentShield-compatible gateway endpoint. Update `GATEWAY_URL` and
`AGENTSHIELD_API_KEY` to match the credentials you mint via identity-service,
then run:

```bash
python examples/python-openai-gateway/main.py
```

The response should be a normal OpenAI-style JSON payload, and the invocation
will appear in the Vigil console’s Overview tab.

## Quick sanity checklist

With AgentShield cloned locally, start the core services (feel free to adjust
ports to match your setup):

```bash
uvicorn agentshield.services.gateway.app:app --reload --port 8000
uvicorn agentshield.services.audit-reporter.app:app --reload --port 8200
uvicorn agentshield.services.policy-hub.app:app --reload --port 8100
uvicorn agentshield.services.identity-service.app:app --reload --port 8300
uvicorn agentshield.services.protocol-hub.app:app --reload --port 8400
```

Then, inside the Vigil repo:

```bash
pip install -r requirements.txt
python web/server.py
```

Now:

1. Use `examples/python-openai-gateway/main.py` with an API key issued by
   identity-service to send a test request through the gateway.
2. Open http://localhost:3000 and verify:
   - Overview tab increments total/blocked/PII stats as traffic flows.
   - Policies tab lists whatever policy-hub returns for your tenant.
   - Agents tab shows the identities from identity-service.
   - Network tab loads data from protocol-hub (or waits for future trust links).

That’s it—you now have the public Vigil console pointed at your AgentShield
stack. Customize the endpoints in `web/index.html` if your services run on
different hosts or ports.
