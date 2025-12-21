#!/bin/bash
# Quick Demo Script for Vigil Dashboard

echo "🔭 Vigil Dashboard Demo"
echo "======================="
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install Docker Compose."
    exit 1
fi

echo "📦 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

echo ""
echo "✅ Services started!"
echo ""
echo "📊 Access Points:"
echo "  Dashboard:  http://localhost:3000"
echo "  Gateway:    http://localhost:8000"
echo ""
echo "🔐 Demo Accounts:"
echo "  Admin:      admin / admin123"
echo "  Auditor:    auditor / auditor123"
echo ""

# Generate some test traffic
echo "🚀 Generating test audit logs..."
echo ""

for i in {1..5}; do
    echo "  Sending request $i/5..."
    curl -s -X POST http://localhost:8000/v1/chat/completions \
      -H "Content-Type: application/json" \
      -H "X-Tenant-ID: demo-tenant-$((i % 3))" \
      -H "X-Agent-ID: demo-agent-$i" \
      -H "X-Policy-Version: 1" \
      -d "{\"messages\": [{\"role\": \"user\", \"content\": \"Test message $i\"}]}" \
      > /dev/null 2>&1
    sleep 1
done

echo ""
echo "✅ Test traffic generated!"
echo ""
echo "🎉 Demo ready!"
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:3000 in your browser"
echo "  2. Login with admin / admin123"
echo "  3. View audit logs with 5 test entries"
echo "  4. Click any row to see detailed view"
echo "  5. Try filters (tenant, agent, decision)"
echo "  6. Test policy configuration"
echo "  7. Export logs to JSON/CSV"
echo ""
echo "📋 View logs:"
echo "  docker-compose logs -f vigil-dashboard"
echo ""
echo "🛑 Stop demo:"
echo "  docker-compose down"
echo ""
