#!/bin/bash
# Simple API Key Generator - Works without Docker
# Run this if your Docker container won't start

set -e

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         🔑 Vigil API Key Generator                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+."
    exit 1
fi

# Run the generator
python3 generate_api_key.py

echo ""
echo "✨ Next steps:"
echo ""
echo "1. Start Vigil:"
echo "   docker compose up -d"
echo ""
echo "2. Test the API:"
echo "   curl http://localhost:8000/health"
echo ""
echo "3. Use your key with requests"
echo ""
