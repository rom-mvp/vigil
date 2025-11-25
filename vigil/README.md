# Vigil Developer Sandbox

This folder hosts the lightweight assets that let you experiment with the new
AgentShield-powered Vigil flow without the legacy Docker stack.

```
vigil/
├── README.md
├── requirements.txt
├── web/
│   ├── index.html        # Console UI that proxies to AgentShield
│   └── server.py         # Tiny Flask wrapper around the dashboard API
└── examples/
    └── python-openai-gateway/
        └── main.py       # Sample OpenAI client pointed at the Vigil gateway
```

## Web console

Run the console locally to monitor telemetry or to demo the product offline:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r vigil/requirements.txt

export AGENTSHIELD_KEY=sk_admin          # or your tenant key
export AGENTSHIELD_API_BASE=https://command.agentshield.ai
python vigil/web/server.py
```

Open http://localhost:4173 and paste your AgentShield admin key. Toggle **demo
mode** if you want curated sample data without hitting the upstream service.

### Useful environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENTSHIELD_API_BASE` | `https://command.agentshield.ai` | Upstream dashboard endpoint. |
| `AGENTSHIELD_KEY` | *(unset)* | Optional default key for local dev. |
| `AGENTSHIELD_TIMEOUT` | `8` | Seconds before network requests fail over to demo data. |
| `AGENTSHIELD_REGION` | `local` | Label used in the demo payload. |
| `PORT` | `4173` | Port used by `web/server.py`. |

## Gateway example

The script in `examples/python-openai-gateway` shows how to reuse the official
OpenAI SDK with the Vigil gateway. It sends a canary message that should be
blocked/redacted by AgentShield and appear immediately in the console.

```bash
source .venv/bin/activate
export VIGIL_GATEWAY_URL=http://localhost:8000/v1
python vigil/examples/python-openai-gateway/main.py
```

Customize `VIGIL_GATEWAY_KEY`, `VIGIL_TENANT_ID`, and `VIGIL_MODEL` to match
your environment. The dependency list (Flask, requests, openai, etc.) lives in
`vigil/requirements.txt`.
