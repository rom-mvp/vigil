#!/bin/bash

# PHASE 5: Docker-Compose Integration Verification Script

# Don't exit on error - we want to collect all failures
cd /workspaces/vigil

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         PHASE 5: DOCKER INTEGRATION VERIFICATION              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CHECKS_PASSED=0
CHECKS_FAILED=0

# Helper function
check_pass() {
    echo -e "${GREEN}✅${NC} $1"
    ((CHECKS_PASSED++))
}

check_fail() {
    echo -e "${RED}❌${NC} $1"
    ((CHECKS_FAILED++))
}

check_warn() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

# ===================================================================
# STEP 1: Git Submodule Status
# ===================================================================
echo "STEP 1: Git Submodule Status"
echo "──────────────────────────────────────────────────────────────"

SUBMODULE_OUTPUT=$(git submodule status 2>&1 || echo "")

if [ -z "$SUBMODULE_OUTPUT" ]; then
    check_fail "AgentShield is not configured as a Git submodule"
    check_warn "  Action: Run: git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield"
else
    if echo "$SUBMODULE_OUTPUT" | grep -q "agentshield"; then
        check_pass "AgentShield is configured as a Git submodule"
        echo "  Details: $SUBMODULE_OUTPUT"
    else
        check_fail "AgentShield submodule not found"
    fi
fi
echo ""

# ===================================================================
# STEP 2: Docker Compose Configuration
# ===================================================================
echo "STEP 2: Docker Compose Configuration"
echo "──────────────────────────────────────────────────────────────"

if grep -q "context: ./services/agentshield" docker-compose.prod.yml; then
    check_pass "docker-compose.prod.yml uses correct build context"
else
    check_fail "docker-compose.prod.yml still uses mock context"
    check_warn "  Current context: $(grep -A2 'agentshield:' docker-compose.prod.yml | grep 'context:' | head -1)"
    check_warn "  Action: Update build context to ./services/agentshield"
fi

if grep -q "HARDWARE_BACKEND=aws_nitro" docker-compose.prod.yml; then
    check_pass "HARDWARE_BACKEND is configured for AWS Nitro"
else
    check_fail "HARDWARE_BACKEND not configured"
    check_warn "  Action: Add environment variable HARDWARE_BACKEND=aws_nitro"
fi

if grep -q "FLASK_APP=mock_agentshield" docker-compose.prod.yml; then
    check_fail "Still has mock_agentshield references in docker-compose"
    check_warn "  Action: Remove FLASK_APP=mock_agentshield.py lines"
else
    check_pass "No mock_agentshield references in docker-compose"
fi
echo ""

# ===================================================================
# STEP 3: File System Status
# ===================================================================
echo "STEP 3: File System Status"
echo "──────────────────────────────────────────────────────────────"

if [ -d "services/agentshield" ]; then
    check_pass "services/agentshield directory exists"
    
    # Check for real agentshield files
    if [ -f "services/agentshield/Dockerfile" ] || [ -f "services/agentshield/Dockerfile.prod" ]; then
        check_pass "AgentShield Dockerfile found"
    else
        check_fail "AgentShield Dockerfile not found in services/agentshield/"
    fi
    
    if [ -f "services/agentshield/requirements.txt" ]; then
        check_pass "AgentShield requirements.txt found"
    else
        check_warn "AgentShield requirements.txt not found (may be OK if already installed)"
    fi
else
    check_fail "services/agentshield directory does not exist"
    check_warn "  Action: Clone real AgentShield repo to services/agentshield"
fi

if [ ! -f "mock_agentshield.py" ]; then
    check_pass "mock_agentshield.py successfully deleted"
else
    check_fail "mock_agentshield.py still exists (should be deleted)"
fi
echo ""

# ===================================================================
# STEP 4: Code Integration Check
# ===================================================================
echo "STEP 4: Code Integration Check"
echo "──────────────────────────────────────────────────────────────"

if grep -q "verify_attestation" src/vigil/clients/agentshield_client.py; then
    check_pass "verify_attestation() implemented in AgentShieldClient"
else
    check_fail "verify_attestation() not found"
fi

if grep -q "verify_attestation" vigil_enhanced_server.py; then
    check_pass "verify_attestation() called in gateway"
else
    check_fail "verify_attestation() not integrated in gateway"
fi

if grep -q "_verify_nitro_attestation\|_verify_azure_attestation" src/vigil/clients/agentshield_client.py; then
    check_pass "Both AWS Nitro and Azure TDX handlers implemented"
else
    check_fail "Attestation handlers not implemented"
fi
echo ""

# ===================================================================
# STEP 5: Test Status
# ===================================================================
echo "STEP 5: Test Status"
echo "──────────────────────────────────────────────────────────────"

if python3 -m pytest tests/integration/test_agentshield_real.py -q --tb=no 2>&1 | grep -q "passed"; then
    TEST_COUNT=$(python3 -m pytest tests/integration/test_agentshield_real.py -q --tb=no 2>&1 | grep "passed" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+")
    check_pass "All tests passing (${TEST_COUNT} tests)"
else
    check_fail "Tests not passing"
fi
echo ""

# ===================================================================
# STEP 6: Docker Compose Validation
# ===================================================================
echo "STEP 6: Docker Compose Configuration Validation"
echo "──────────────────────────────────────────────────────────────"

if command -v docker-compose &> /dev/null; then
    if docker-compose -f docker-compose.prod.yml config > /dev/null 2>&1; then
        check_pass "docker-compose.prod.yml syntax is valid"
    else
        check_fail "docker-compose.prod.yml has syntax errors"
    fi
    
    # Check service list
    SERVICES=$(docker-compose -f docker-compose.prod.yml config --services 2>/dev/null || echo "error")
    if echo "$SERVICES" | grep -q "vigil"; then
        check_pass "Vigil gateway service is configured"
    else
        check_fail "Vigil gateway service not found"
    fi
    
    if echo "$SERVICES" | grep -q "agentshield"; then
        check_pass "AgentShield service is configured"
    else
        check_fail "AgentShield service not found"
    fi
else
    check_warn "docker-compose not available (cannot validate)"
fi
echo ""

# ===================================================================
# SUMMARY
# ===================================================================
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                      SUMMARY                                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Checks Passed: ${GREEN}${CHECKS_PASSED}${NC}"
echo "Checks Failed: ${RED}${CHECKS_FAILED}${NC}"
echo ""

if [ $CHECKS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
    echo ""
    echo "System is ready for Docker deployment:"
    echo "  1. docker compose -f docker-compose.prod.yml build"
    echo "  2. docker compose -f docker-compose.prod.yml up -d"
    echo "  3. pytest tests/integration/test_agentshield_real.py -v"
else
    echo -e "${RED}❌ SOME CHECKS FAILED${NC}"
    echo ""
    echo "Required Actions:"
    echo "  1. Clone AgentShield: git submodule add git@github.com:rom-mvp/agentshield.git services/agentshield"
    echo "  2. Update docker-compose.prod.yml build context"
    echo "  3. Remove mock_agentshield references"
    echo ""
    echo "See PHASE5_INTEGRATION.md for detailed instructions"
fi
