import sys
import os

# Ensure project src is on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from vigil.agentshield_client import AgentShieldClient, VigilErrorCode  # noqa: F401
