#!/bin/bash

# Comprehensive test suite runner
# Tests all aspects of the system

set -e

echo "🧪 Telecom AI Copilot - Comprehensive Test Suite"
echo "================================================="
echo ""

BACKEND_URL="http://localhost:8000"
TESTS_PASSED=0
TESTS_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ PASS${NC}: $2"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ FAIL${NC}: $2"
        ((TESTS_FAILED++))
    fi
}

echo "📋 Test 1: Backend Health Check"
echo "------"
HEALTH=$(curl -s http://localhost:8000/health | grep -o '"status": "[^"]*')
[[ $HEALTH == *"healthy"* ]] && test_result 0 "Backend is healthy" || test_result 1 "Backend not healthy"
echo ""

echo "📋 Test 2: Database Initialization"
echo "------"
INIT=$(curl -s -X POST http://localhost:8000/initialize \
    -H "Content-Type: application/json" \
    -d '{
        "incidents_csv_path": "/data/incidents/incidents.csv",
        "logs_dir_path": "/data/logs",
        "manuals_dir_path": "/data/manuals"
    }')

DOC_COUNT=$(echo "$INIT" | grep -o '"document_count": [0-9]*' | grep -o '[0-9]*')
[[ $DOC_COUNT -gt 100 ]] && test_result 0 "Database initialized with $DOC_COUNT documents" || test_result 1 "Database initialization failed"
echo ""

echo "📋 Test 3: Incident Analysis"
echo "------"
ANALYSIS=$(curl -s -X POST http://localhost:8000/analyze-incident \
    -H "Content-Type: application/json" \
    -d '{
        "incident_description": "High packet loss on Node B12",
        "top_k_retrieval": 5,
        "temperature": 0.7
    }')

HAS_ROOT_CAUSE=$(echo "$ANALYSIS" | grep -c '"root_cause"' || true)
HAS_ACTIONS=$(echo "$ANALYSIS" | grep -c '"recommended_actions"' || true)
HAS_SEVERITY=$(echo "$ANALYSIS" | grep -c '"severity"' || true)
HAS_METRICS=$(echo "$ANALYSIS" | grep -c '"metrics"' || true)

[[ $HAS_ROOT_CAUSE -gt 0 && $HAS_ACTIONS -gt 0 && $HAS_SEVERITY -gt 0 && $HAS_METRICS -gt 0 ]] && \
    test_result 0 "Analysis generated with all required fields" || \
    test_result 1 "Analysis missing required fields"
echo ""

echo "📋 Test 4: Retrieval Quality"
echo "------"
DOC_COUNT=$(echo "$ANALYSIS" | grep -o '"retrieved_context"' | wc -l)
[[ $DOC_COUNT -gt 0 ]] && test_result 0 "Retrieved $DOC_COUNT context documents" || test_result 1 "No documents retrieved"
echo ""

echo "📋 Test 5: Metrics Collection"
echo "------"
METRICS=$(curl -s http://localhost:8000/metrics)
HAS_LATENCY=$(echo "$METRICS" | grep -c '"latency' || true)
HAS_QUALITY=$(echo "$METRICS" | grep -c '"quality' || true)

[[ $HAS_LATENCY -gt 0 && $HAS_QUALITY -gt 0 ]] && \
    test_result 0 "Metrics collected successfully" || \
    test_result 1 "Metrics collection incomplete"
echo ""

echo "📋 Test 6: Multiple Incidents (Consistency)"
echo "------"
for i in 1 2 3; do
    INCIDENT="Test incident $i with various symptoms"
    curl -s -X POST http://localhost:8000/analyze-incident \
        -H "Content-Type: application/json" \
        -d "{\"incident_description\": \"$INCIDENT\"}" > /dev/null
done

# Check aggregated metrics
AGG_METRICS=$(curl -s http://localhost:8000/metrics)
REQUEST_COUNT=$(echo "$AGG_METRICS" | grep -o '"request_count": [0-9]*' | grep -o '[0-9]*')
[[ $REQUEST_COUNT -ge 4 ]] && test_result 0 "Processed $REQUEST_COUNT requests total" || test_result 1 "Request count mismatch"
echo ""

echo "📋 Test 7: Error Handling"
echo "------"
# Test with empty input
ERROR_RESPONSE=$(curl -s -X POST http://localhost:8000/analyze-incident \
    -H "Content-Type: application/json" \
    -d '{"incident_description": ""}')

HAS_ERROR=$(echo "$ERROR_RESPONSE" | grep -c '"error"' || echo "$ERROR_RESPONSE" | grep -c '"root_cause"' || true)
[[ $HAS_ERROR -ge 0 ]] && test_result 0 "Error handling functional" || test_result 1 "Error handling failed"
echo ""

echo "📋 Test 8: System Stats"
echo "------"
STATS=$(curl -s http://localhost:8000/stats)
HAS_COLLECTION=$(echo "$STATS" | grep -c '"collection"' || true)
HAS_LLM=$(echo "$STATS" | grep -c '"llm_available"' || true)

[[ $HAS_COLLECTION -gt 0 && $HAS_LLM -gt 0 ]] && \
    test_result 0 "System stats available" || \
    test_result 1 "System stats incomplete"
echo ""

# Summary
echo "================================================="
echo "📊 Test Summary"
echo "================================================="
TOTAL=$((TESTS_PASSED + TESTS_FAILED))
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo "Total:  $TOTAL"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}⚠️  Some tests failed. Check logs above.${NC}"
    exit 1
fi
