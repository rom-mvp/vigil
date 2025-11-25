# 🔭 Vigil

### The Public Console & Developer Experience Layer for AgentShield

**Vigil** is the official **console** and **developer toolkit** for **AgentShield** — the trust, identity, and governance layer for AI agents.

While **AgentShield** provides backend services (Gateway, Firewall, PII Redaction, Policy Hub, Identity Service, Protocol Network), **Vigil** provides the user-facing interface:

* 📊 Real-time runtime dashboard for agent activity
* 🛡 Policy management UI
* 🧬 Identity (NHI) management for agents
* 🌐 Cross-tenant trust graph (Phase 3 preview)
* 🧑‍💻 Developer examples for integrating with the AgentShield Gateway

Vigil is lightweight, easy to deploy, and fully environment-aware (Local, Staging, Production).

---

# 🚀 Features

## 🔍 1. Overview Tab

Monitor agent activity flowing through AgentShield’s Gateway:

* Total Requests
* Blocked Attacks (firewall or policy)
* PII Redactions

Includes a **live event table** showing:

* Timestamp
* Tenant ID
* Agent ID
* Phase (`request`, `response`, `blocked`)
* Blocked status
* PII detection count

---

## 🧩 2. Policies Tab

Connects to AgentShield’s **Policy Hub**:

* List all governance policies for the selected tenant
* Create new policies directly from the UI
* View:

  * Name
  * Description
  * Priority
  * Rule count

In **Phase 2+**, changes propagate instantly to all agents.

---

## 🧬 3. Agents Tab

Connects to AgentShield’s **Identity Service** to manage Non-Human Identities (NHIs):

* List all agents for the current tenant
* Create new agents (auto-generates API keys)
* View:

  * Agent ID
  * Roles
  * API Key
  * Active / disabled status

---

## 🌐 4. Network Tab (Phase 3 Preview)

Visualizes the emerging **Agent Identity Network** backed by AgentShield’s Protocol Hub:

* Cross-tenant trust relationships
* Direction of trust (A → B)
* Trust scores
* Last updated timestamps

This previews Phase 3’s “Visa/Mastercard-style network” for agent-to-agent interactions.

---

## ⚙️ 5. Multi-Environment & Multi-Tenant Support

Top-right controls let you instantly switch between:

* **Environment:** Local / Staging / Production
* **Tenant ID:** Free text (e.g., `dev-tenant`, `acme-prod`)

Selections are automatically persisted via `localStorage`.

---

# 🏗 Repository Structure

```
vigil/
  web/
    index.html         # Vigil console (single-page UI)
    server.py          # Lightweight Flask dev server

  examples/
    python-openai-gateway/
      main.py          # Example: calling the AgentShield Gateway

  requirements.txt      # Minimal dependencies
  README.md             # This file
  LICENSE
```

---

# 📦 Requirements

* Python **3.11+**
* Running AgentShield backend (any environment):

| Service          | Port |
| ---------------- | ---- |
| Gateway          | 8000 |
| Policy Hub       | 8100 |
| Audit Reporter   | 8200 |
| Identity Service | 8300 |
| Protocol Hub     | 8400 |

---

# 🧪 Running Vigil Locally

Clone the repo and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Start the Vigil console:

```bash
python web/server.py
```

Open your browser at:

```
http://localhost:3000
```

You now have the full Vigil console running locally.

---

# 🔧 Configure Your Environments

Vigil includes an editable `ENV_CONFIG` block in `web/index.html`:

```js
const ENV_CONFIG = {
  local: {
    label: "Local Dev",
    AUDIT_API: "http://localhost:8200",
    POLICY_API: "http://localhost:8100",
    IDENTITY_API: "http://localhost:8300",
    PROTOCOL_API: "http://localhost:8400",
  },
  staging: {
    label: "Staging",
    AUDIT_API: "https://staging-audit.agentshield.yourcloud.com",
    POLICY_API: "https://staging-policy.agentshield.yourcloud.com",
    IDENTITY_API: "https://staging-identity.agentshield.yourcloud.com",
    PROTOCOL_API: "https://staging-protocol.agentshield.yourcloud.com",
  },
  prod: {
    label: "Production",
    AUDIT_API: "https://audit.agentshield.com",
    POLICY_API: "https://policy.agentshield.com",
    IDENTITY_API: "https://identity.agentshield.com",
    PROTOCOL_API: "https://protocol.agentshield.com",
  },
};
```

Modify these values to match your deployment.

The **Env Dropdown** updates instantly and persists across sessions.

---

# 🔑 Calling the AgentShield Gateway (Developer Example)

Vigil ships with a simple, copy/paste-ready Python example:

**File:** `examples/python-openai-gateway/main.py`

```python
import asyncio
import httpx

GATEWAY_URL = "http://localhost:8000/v1/chat/completions"
AGENTSHIELD_API_KEY = "YOUR_AGENT_API_KEY"  # created via identity-service


async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GATEWAY_URL,
            headers={"Authorization": f"Bearer {AGENTSHIELD_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": "Hello from a secured agent via Vigil example"}
                ],
            },
        )
        print(resp.json())


if __name__ == "__main__":
    asyncio.run(main())
```

This demonstrates exactly how developers should integrate their agents with the secured Gateway.

---

# 🧭 Relationship to AgentShield

```
+-------------------------+
|      Vigil (UI/UX)      |
|   - Dashboard           |
|   - Policies            |
|   - Agents              |
|   - Network             |
|   - SDK Examples        |
+-------------------------+
              |
              v
+--------------------------------------+
|             AgentShield              |
|   Runtime Gateway (Firewall + PII)   |
|   Audit Reporter                     |
|   Policy Hub                         |
|   Identity Service                   |
|   Protocol Hub                       |
|   Core Engines (firewall/pii/policy) |
+--------------------------------------+
```

* **Vigil = Frontend**
* **AgentShield = Backend**

Vigil contains **no security logic** — it simply communicates with the AgentShield APIs.

---

# 📄 License

**Apache 2.0**

---

# 📬 Contributing

Pull Requests are welcome for:

* UI/UX improvements
* Additional examples
* Richer policy/identity editors
* New environment presets

Please open issues for bugs or feature requests.

---

# 🛡️ Final Notes

Vigil is intentionally minimal:

* No backend logic
* No build tooling
* No JS frameworks
* Fully self-contained single-file UI
* Works with any AgentShield backend (local → prod)

This simplicity makes Vigil easy for developers, CISOs, and enterprise teams to deploy and extend.

