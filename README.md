# Vigil

Vigil is the **public console and example client** for [AgentShield](https://your-site-here).

It gives security and platform teams a single pane of glass to:

- See **all agent traffic** (requests, responses, blocks, PII redactions)
- Manage **policies** across tenants and environments
- Manage **non-human identities** (agents & their API keys)
- Preview the **Agent Identity Network** (Phase 3 vision)

Under the hood, Vigil is a thin UI that talks to your **AgentShield** services over HTTP.

---

## Prerequisites

You need an AgentShield environment running somewhere (local, staging, or prod):

- `gateway` (port `8000` by default)
- `audit-reporter` (port `8200`)
- `policy-hub` (port `8100`)
- `identity-service` (port `8300`)
- `protocol-hub` (port `8400`, optional)

> See the AgentShield repo README for how to start these.

For Vigil itself:

- Python 3.11+
- `pip` / `venv`

---

## Install & Run (Local Dev)

From the Vigil repo root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python web/server.py
