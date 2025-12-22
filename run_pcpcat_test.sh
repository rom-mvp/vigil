#!/bin/bash
# Quick test runner for Operation PCPCAT

echo "🎯 Operation PCPCAT Test Runner"
echo "================================"

# Check if Vigil is running
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Vigil is running on localhost:8000"
    echo ""
    echo "🚀 Running PCPCAT attack test suite..."
    echo ""
    python test_pcpcat.py
else
    echo "⚠️  Vigil server not detected on localhost:8000"
    echo ""
    echo "Starting Vigil Enhanced Server..."
    echo ""
    
    # Start Vigil in background
    python vigil_enhanced_server.py > vigil_server.log 2>&1 &
    VIGIL_PID=$!
    
    echo "Waiting for server to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo "✅ Vigil server started (PID: $VIGIL_PID)"
            break
        fi
        echo -n "."
        sleep 1
    done
    
    echo ""
    echo "🚀 Running PCPCAT attack test suite..."
    echo ""
    
    # Run the test
    python test_pcpcat.py
    TEST_EXIT=$?
    
    # Optional: Stop Vigil after test
    # kill $VIGIL_PID 2>/dev/null
    
    exit $TEST_EXIT
fi
