#!/bin/bash
# Vigil AgentShield v2.0 Integration Test Suite

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_KEY=${VIGIL_API_KEY:-"sk-vigil-d39becf0e143aac46e96c5647b6a91cd806c2298cd526eaf5a16a132537d56ed"}
BASE_URL=${VIGIL_URL:-"http://localhost:5000"}

echo "========================================"
echo "  Vigil AgentShield v2.0 Test Suite"
echo "========================================"
echo ""

# Test counter
PASSED=0
FAILED=0

# Test function
test_endpoint() {
    local name=$1
    local endpoint=$2
    local expected_keys=$3
    
    echo -n "Testing $name... "
    
    response=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $API_KEY" "$BASE_URL$endpoint")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -eq 200 ]; then
        # Check for expected keys in JSON
        if echo "$body" | python3 -c "import json, sys; data=json.load(sys.stdin); keys='$expected_keys'.split(','); exit(0 if all(k in data for k in keys) else 1)" 2>/dev/null; then
            echo -e "${GREEN}✓ PASSED${NC}"
            ((PASSED++))
            return 0
        else
            echo -e "${RED}✗ FAILED${NC} (Missing expected keys: $expected_keys)"
            ((FAILED++))
            return 1
        fi
    else
        echo -e "${RED}✗ FAILED${NC} (HTTP $http_code)"
        echo "$body" | head -5
        ((FAILED++))
        return 1
    fi
}

# Run tests
echo "=== Core Endpoints ==="
test_endpoint "System Status" "/api/status" "status,version,mode"
test_endpoint "System Stats" "/api/stats" "total_requests,blocked_attacks"
test_endpoint "Event Logs" "/api/logs" ""

echo ""
echo "=== AgentShield v2.0 Analytics ==="
test_endpoint "Classifier Analytics" "/api/analytics/classifier" "total_classified,breakdown,trends"
test_endpoint "Scanner Pipeline" "/api/analytics/scanner-pipeline" "total_scanned,verdicts"
test_endpoint "Registry Hooks" "/api/analytics/registry-hooks" "governance,datasets,models"
test_endpoint "Supply Chain" "/api/analytics/supply-chain" "sbom,components"
test_endpoint "Semantic Threats" "/api/alerts/semantic-threats" "total_alerts,alerts"

echo ""
echo "=== Detailed Verification ==="

# Verify classifier breakdown
echo -n "Checking classifier labels... "
classifier_data=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/analytics/classifier")
if echo "$classifier_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
breakdown = data.get('breakdown', {})
required = ['jailbreak', 'exfiltration', 'coercion', 'safe']
if all(label in breakdown for label in required):
    print('OK')
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} All labels present"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} Missing required labels"
    ((FAILED++))
fi

# Verify scanner verdicts
echo -n "Checking scanner verdicts... "
scanner_data=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/analytics/scanner-pipeline")
if echo "$scanner_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
verdicts = data.get('verdicts', {})
required = ['PASS', 'WARN', 'BLOCK']
if all(v in verdicts for v in required):
    print('OK')
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} All verdicts present"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} Missing required verdicts"
    ((FAILED++))
fi

# Verify governance metrics
echo -n "Checking governance metrics... "
registry_data=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/analytics/registry-hooks")
if echo "$registry_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
gov = data.get('governance', {})
required = ['poisoning_detected', 'dp_enforced', 'watermark_verified']
if all(m in gov for m in required):
    print('OK')
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} All governance metrics present"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} Missing required metrics"
    ((FAILED++))
fi

# Verify SBOM data
echo -n "Checking SBOM verification... "
sc_data=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/analytics/supply-chain")
if echo "$sc_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
sbom = data.get('sbom', {})
if 'verified' in sbom and 'failed' in sbom and 'success_rate' in sbom:
    success_rate = sbom['success_rate']
    print(f'OK (Success rate: {success_rate}%)')
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} SBOM data complete"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} Incomplete SBOM data"
    ((FAILED++))
fi

# Verify alert severity levels
echo -n "Checking alert severity levels... "
threats_data=$(curl -s -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/alerts/semantic-threats")
if echo "$threats_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if 'critical' in data and 'high' in data and 'medium' in data:
    print(f'OK (Critical: {data[\"critical\"]}, High: {data[\"high\"]})')
    sys.exit(0)
else:
    sys.exit(1)
" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} All severity levels present"
    ((PASSED++))
else
    echo -e "${RED}✗${NC} Missing severity levels"
    ((FAILED++))
fi

echo ""
echo "=== Sample Data Verification ==="

# Show sample classifier data
echo "Classifier Summary:"
echo "$classifier_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
breakdown = data.get('breakdown', {})
print(f\"  • Jailbreak: {breakdown.get('jailbreak', {}).get('count', 0)} ({breakdown.get('jailbreak', {}).get('high_confidence', 0)} high-conf)\")
print(f\"  • Exfiltration: {breakdown.get('exfiltration', {}).get('count', 0)} ({breakdown.get('exfiltration', {}).get('high_confidence', 0)} high-conf)\")
print(f\"  • Coercion: {breakdown.get('coercion', {}).get('count', 0)} ({breakdown.get('coercion', {}).get('high_confidence', 0)} high-conf)\")
print(f\"  • Safe: {breakdown.get('safe', {}).get('count', 0)}\")
"

# Show sample scanner data
echo ""
echo "Scanner Summary:"
echo "$scanner_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
verdicts = data.get('verdicts', {})
print(f\"  • PASS: {verdicts.get('PASS', {}).get('count', 0)} ({verdicts.get('PASS', {}).get('percentage', 0)}%)\")
print(f\"  • WARN: {verdicts.get('WARN', {}).get('count', 0)} ({verdicts.get('WARN', {}).get('percentage', 0)}%)\")
print(f\"  • BLOCK: {verdicts.get('BLOCK', {}).get('count', 0)} ({verdicts.get('BLOCK', {}).get('percentage', 0)}%)\")
"

# Show sample governance data
echo ""
echo "Governance Summary:"
echo "$registry_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
gov = data.get('governance', {})
print(f\"  • Poisoning detected: {gov.get('poisoning_detected', {}).get('count', 0)}\")
print(f\"  • DP enforced: {gov.get('dp_enforced', {}).get('count', 0)} queries\")
print(f\"  • Watermark verified: {gov.get('watermark_verified', {}).get('count', 0)} ({gov.get('watermark_verified', {}).get('success_rate', 0)}%)\")
"

# Show sample supply chain data
echo ""
echo "Supply Chain Summary:"
echo "$sc_data" | python3 -c "
import json, sys
data = json.load(sys.stdin)
sbom = data.get('sbom', {})
components = data.get('components', {})
print(f\"  • SBOM verified: {sbom.get('verified', 0)}/{sbom.get('total_verifications', 0)} ({sbom.get('success_rate', 0)}%)\")
print(f\"  • Components tracked: {components.get('total_tracked', 0)}\")
print(f\"  • Vulnerabilities: {components.get('vulnerable', 0)}\")
"

echo ""
echo "========================================"
echo "  Test Results"
echo "========================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo "Total: $((PASSED + FAILED))"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "Dashboard available at: $BASE_URL"
    echo "Use API key: ${API_KEY:0:20}..."
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
