#!/bin/bash
set -e

echo "🔭 Starting Vigil Security Gateway..."

# Check Python environment
if [ ! -f "requirements.txt" ]; then
    echo "❌ Error: requirements.txt not found!"
    exit 1
fi

echo "📦 Verifying dependencies..."
pip install -r requirements.txt > /dev/null 2>&1 || {
    echo "⚠️  Pip install failed. Attempting fallback install..."
    pip install flask requests numpy sentence-transformers python-dotenv presidio-analyzer presidio-anonymizer cryptography
}

# Kill existing processes
pkill -f "python.*local_server.py" 2>/dev/null || true
pkill -f "python.*mock_agentshield.py" 2>/dev/null || true
pkill -f "python.*test_server" 2>/dev/null || true
sleep 1

echo "🛡️  Bootstrapping AgentShield backend..."
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python3 test_server_quick.py > /tmp/vigil.log 2>&1 &
PID=$!

echo "✅ Vigil is running on http://localhost:8000"
echo "📊 Health check: http://localhost:8000/health"
echo "Press Ctrl+C to stop."
wait $PID
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
