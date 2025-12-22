#!/bin/bash
# Complete script to start server and run PCPCAT tests

echo "🎯 Operation PCPCAT - Complete Test Runner"
echo "=========================================="
echo ""

# Kill any existing servers
echo "🧹 Cleaning up any existing servers..."
pkill -f "vigil_test_server" 2>/dev/null
sleep 1

# Start Vigil Test Server
echo "🚀 Starting Vigil Test Server..."
python /workspaces/vigil/vigil_test_server.py > /tmp/vigil_server.log 2>&1 &
SERVER_PID=$!
echo "   Server PID: $SERVER_PID"

# Wait for server to be ready
echo "⏳ Waiting for server to initialize..."
for i in {1..15}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Server is ready!"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Check if server is actually running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "❌ ERROR: Server failed to start"
    echo "Server log:"
    cat /tmp/vigil_server.log
    exit 1
fi

echo ""
echo "🧪 Running PCPCAT attack tests..."
echo "=================================="
echo ""

# Run the test
python /workspaces/vigil/test_pcpcat_quick.py

TEST_EXIT=$?

echo ""
echo "🏁 Test execution complete!"
echo ""

# Optionally kill the server
read -p "Kill the test server? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kill $SERVER_PID 2>/dev/null
    echo "Server stopped."
fi

exit $TEST_EXIT
