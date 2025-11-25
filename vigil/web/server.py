from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import requests
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

APP_DIR = Path(__file__).resolve().parent
INDEX_FILE = APP_DIR / "index.html"

AGENTSHIELD_API_BASE = os.getenv("AGENTSHIELD_API_BASE", "https://command.agentshield.ai")
AGENTSHIELD_KEY = os.getenv("AGENTSHIELD_KEY")
AGENTSHIELD_TIMEOUT = float(os.getenv("AGENTSHIELD_TIMEOUT", "8.0"))
DEFAULT_PORT = int(os.getenv("PORT", "4173"))

DEMO_EVENTS = [
    {"status": "BLOCKED · PROMPT INJECTION", "details": {"reason": "System override attempt"}},
    {"status": "ALLOW · REDACTED", "details": {"reason": "PII removed", "redacted": True}},
    {"status": "ALLOW · CLEAN", "details": {"reason": "Policy compliant"}},
    {"status": "BLOCKED · DATA EXFIL", "details": {"reason": "External URL exfil attempt"}},
]

app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/api/*": {"origins": "*"}})
SESSION = requests.Session()


@app.get("/")
def serve_index():
    """Return the static console UI."""
    return send_file(INDEX_FILE)


@app.get("/api/health")
def health() -> Any:
    """Simple readiness probe for the UI container."""
    return jsonify(
        {
            "service": "vigil-web-console",
            "status": "ok",
            "version": "0.4-preview",
            "endpoint": _resolve_base(request.headers.get("x-agentshield-endpoint")),
            "demo_supported": True,
            "has_upstream_key": bool(AGENTSHIELD_KEY),
        }
    )


@app.get("/api/dashboard")
def dashboard() -> Any:
    """Proxy AgentShield's admin dashboard or fall back to demo data."""
    if request.args.get("demo") == "1":
        payload = _demo_payload(mode="demo")
        payload["endpoint"] = "demo://local"
        return jsonify(payload)

    key = request.headers.get("x-agentshield-key") or AGENTSHIELD_KEY
    if not key:
        return jsonify({"error": "AgentShield key is required"}), 400

    base = _resolve_base(request.headers.get("x-agentshield-endpoint"))
    url = f"{base}/admin/dashboard"

    try:
        upstream = SESSION.get(
            url,
            headers={"x-agentshield-key": key},
            timeout=AGENTSHIELD_TIMEOUT,
        )
        upstream.raise_for_status()
    except requests.RequestException as exc:
        payload = _demo_payload(mode="fallback")
        payload["error"] = "Unable to reach AgentShield"
        payload["details"] = str(exc)
        payload["endpoint"] = base
        return jsonify(payload), 200

    data = upstream.json()
    data.setdefault("stats", {})
    data.setdefault("recent_logs", [])
    data.setdefault("tenant", {})
    data["source"] = "agentshield"
    data["proxied_at"] = datetime.now(timezone.utc).isoformat()
    data["endpoint"] = base
    return jsonify(data)


def _resolve_base(candidate: str | None = None) -> str:
    base = (candidate or AGENTSHIELD_API_BASE).strip()
    if not base:
        return "https://command.agentshield.ai"
    return base.rstrip("/")


def _demo_payload(mode: str = "demo") -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    events = []
    for idx, template in enumerate(random.choices(DEMO_EVENTS, k=10)):
        log = {
            "timestamp": (now - timedelta(seconds=idx * 42)).isoformat(),
            "status": template["status"],
            "agent_id": f"agent-{random.randint(1800, 9999)}",
            "details": dict(template.get("details", {})),
        }
        events.append(log)

    blocked = sum(1 for event in events if event["status"].startswith("BLOCKED"))
    redacted = sum(1 for event in events if event["details"].get("redacted"))
    total = random.randint(max(blocked + redacted, 90), max(blocked + redacted + 250, 180))

    return {
        "source": mode,
        "generated_at": now.isoformat(),
        "tenant": {
            "id": "agentshield-demo",
            "plan": "enterprise_plus",
            "region": os.getenv("AGENTSHIELD_REGION", "local"),
        },
        "stats": {
            "total_requests": total,
            "blocked_attacks": blocked,
            "redacted_events": max(redacted, blocked // 2),
            "unique_tenants": random.randint(1, 4),
        },
        "recent_logs": events,
    }


if __name__ == "__main__":
    print(f"⚡ Vigil console available at http://0.0.0.0:{DEFAULT_PORT}")
    app.run(host="0.0.0.0", port=DEFAULT_PORT, debug=os.getenv("FLASK_DEBUG") == "1")
