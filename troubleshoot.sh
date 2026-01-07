#!/bin/bash
# Quick Setup Guide for Vigil

echo "🔭 Vigil Setup & Troubleshooting"
echo "================================"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Docker
if ! command_exists docker; then
    echo "❌ Docker not found. Please install Docker first."
    exit 1
fi

echo "✅ Docker found: $(docker --version)"

# Check Docker Compose
if ! docker compose version >/dev/null 2>&1; then
    echo "❌ Docker Compose not found. Please install Docker Compose v2+."
    exit 1
fi

echo "✅ Docker Compose found: $(docker compose version)"
echo ""

# Check container status
echo "📊 Checking container status..."
docker compose ps

echo ""
echo "🔧 Common fixes:"
echo ""
echo "1️⃣  View logs:"
echo "   docker compose logs vigil"
echo "   docker compose logs vigil --follow"
echo ""
echo "2️⃣  Restart containers:"
echo "   docker compose restart"
echo ""
echo "3️⃣  Rebuild containers:"
echo "   docker compose down"
echo "   docker compose up --build -d"
echo ""
echo "4️⃣  Generate API key (after containers are running):"
echo "   docker compose exec vigil python3 generate_api_key.py"
echo "   # Or run locally:"
echo "   python3 generate_api_key.py"
echo ""
echo "5️⃣  Test the service:"
echo "   curl http://localhost:8000/health"
echo ""
