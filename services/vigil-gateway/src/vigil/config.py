import os

VIGIL_MODE = os.getenv("VIGIL_MODE", "standalone")

AGENTSHIELD_URL = os.getenv("AGENTSHIELD_URL")
AGENTSHIELD_JWKS_URL = os.getenv("AGENTSHIELD_JWKS_URL")
AGENTSHIELD_TIMEOUT_MS = int(os.getenv("AGENTSHIELD_TIMEOUT_MS", "3000"))
AGENTSHIELD_FAIL_MODE = os.getenv("AGENTSHIELD_FAIL_MODE", "deny").lower()

if VIGIL_MODE == "saas":
    missing = []
    if not AGENTSHIELD_URL:
        missing.append("AGENTSHIELD_URL")
    if not AGENTSHIELD_JWKS_URL:
        missing.append("AGENTSHIELD_JWKS_URL")

    if missing:
        raise RuntimeError(
            f"VIGIL_MODE=saas requires AgentShield config. Missing: {missing}"
        )
