#!/bin/bash
# One-command startup for Vigil + AgentShield backend
set -e

echo "🔭 Starting Vigil Security Gateway..."
echo ""

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Setting up Python environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -q -r requirements.txt
else
    source venv/bin/activate
fi

# Kill existing processes
pkill -f "python.*local_server.py" 2>/dev/null || true
pkill -f "python.*mock_agentshield.py" 2>/dev/null || true
sleep 1

# Start AgentShield backend (user-facing analytics API)
echo "🛡️  Starting AgentShield backend on port 9000..."
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python3 mock_agentshield.py > /tmp/agentshield.log 2>&1 &
AGENTSHIELD_PID=$!

# Start Vigil Gateway (internal security layer)
echo "🔐 Starting Vigil Gateway on port 8000..."
cd src/vigil && python3 local_server.py > /tmp/gateway.log 2>&1 &
GATEWAY_PID=$!
cd ../..

# Wait for services to be ready
echo "⏳ Waiting for services..."
sleep 3

# Health check
if ! curl -s http://localhost:9000/health > /dev/null; then
    echo "❌ AgentShield backend failed to start"
    cat /tmp/agentshield.log
    exit 1
fi

if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ Vigil Gateway failed to start"
    cat /tmp/gateway.log
    exit 1
fi

echo ""
echo "✅ Vigil is running!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📡 API Endpoints:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  🔐 Protected LLM Requests:"
echo "     POST http://localhost:8000/v1/chat/completions"
echo ""
echo "  📊 Analytics Dashboard:"
echo "     GET  http://localhost:9000/analytics/dashboard"
echo ""
echo "  📈 Metrics (Prometheus):"
echo "     GET  http://localhost:9000/analytics/metrics"
echo ""
echo "  📋 Audit Logs:"
echo "     GET  http://localhost:9000/analytics/logs?tenant_id=X"
echo ""
echo "  ⚠️  Threat Feed:"
echo "     GET  http://localhost:9000/analytics/threats?threshold=0.5"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 Example Usage:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  # Send protected LLM request:"
echo "  curl -X POST http://localhost:8000/v1/chat/completions \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'X-Tenant-ID: my-app' \\"
echo "    -H 'X-Agent-ID: chatbot-1' \\"
echo "    -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'"
echo ""
echo "  # View analytics:"
echo "  curl http://localhost:9000/analytics/dashboard | python -m json.tool"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Logs:"
echo "  AgentShield: tail -f /tmp/agentshield.log"
echo "  Gateway:     tail -f /tmp/gateway.log"
echo ""
echo "🛑 Stop:"
echo "  pkill -f 'python.*local_server.py|python.*mock_agentshield.py'"
echo ""
