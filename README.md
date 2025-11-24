# 🛡️ Vigil (AgentShield) v0.3 Enterprise

**The Identity-First Security Gateway for AI Agents.**

Vigil is a transparent proxy that sits between your code and the LLM. It blocks attacks and redacts PII *before* data leaves your infrastructure.

**New in v0.3:**
* 🧠 **Context-Aware NLP:** Uses Microsoft Presidio & Spacy to detect PII (Names, Locations) without regex.
* 🔌 **Transparent Gateway:** Drop-in replacement for OpenAI. Just change `base_url`.
* 📊 **Enterprise Dashboard:** Real-time visibility into all attacks and PII redactions via Docker Compose.

---

## ⚡ Quick Start (Enterprise Fleet)

Run the full stack (Gateway + Dashboard) locally.

### 1. Launch the Fleet
```bash
# Starts Gateway (Port 8000) and Dashboard (Port 3000)
docker-compose up --build
```

### 2. Access the Command Center
Open your browser to: **[http://localhost:3000](http://localhost:3000)**
* Login Key: `sk_admin`

### 3. Connect your Agent
Vigil is compatible with the official OpenAI SDK. 

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",  # Point to Vigil Gateway
    api_key="sk-dummy-key"                # No real key needed for local test
)

# This request is automatically scanned, redacted, and logged to your Dashboard
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "My name is Sarah and I live in London."}]
)

print(response.choices[0].message.content)
# Output: "Vigil accepted: 'My name is <REDACTED_PERSON> and I live in <REDACTED_LOCATION>.'"
```

---

## 🛡️ Features

| Feature | Description | Tech Stack |
| :--- | :--- | :--- |
| **Smart PII Redaction** | Detects Names, Locations, Phones, Emails using NLP. | Presidio + Spacy |
| **Heuristic Firewall** | Blocks prompt injections (e.g., "Ignore instructions"). | Regex Engine |
| **Transparent Proxy** | Mimics OpenAI API (`/v1/chat/completions`). | Flask |
| **Enterprise Dashboard** | Aggregates logs from all gateways in real-time. | React + Flask |
| **Privacy First** | Runs 100% offline. No data egress. | Docker |

---

## 🤝 Contributing

1.  Fork the repo.
2.  `docker-compose up --build`
3.  Create a PR with your new detection rules!
