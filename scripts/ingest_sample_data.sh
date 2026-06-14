#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# TeleNOC AI - Sample Data Ingestion Script
# ═══════════════════════════════════════════════════════════════════
#
# Loads sample alarm data into TeleNOC AI for demo/testing.
# Can be run standalone after deployment or called from deploy.sh.
#
# Usage:
#   ./scripts/ingest_sample_data.sh
#
# This will:
#   1. Wait for backend health check
#   2. POST sample_alarms.json to the ingest endpoint
#   3. Display ingestion results
# ═══════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
ALARMS_FILE="${ALARMS_FILE:-/data/sample_alarms.json}"
MAX_RETRIES=30

echo -e "${CYAN}📡 TeleNOC AI - Sample Data Ingestion${NC}"
echo ""

# ─── Wait for Backend ──────────────────────────────────────────────
echo -e "${YELLOW}Waiting for backend at ${BACKEND_URL}...${NC}"

for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "${BACKEND_URL}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready${NC}"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo -e "${RED}❌ Backend not available after ${MAX_RETRIES} attempts${NC}"
        echo "   Make sure TeleNOC AI is running: docker compose -f docker/docker-compose.yml up -d"
        exit 1
    fi
    echo -n "."
    sleep 2
done
echo ""

# ─── Ingest Alarm Data ─────────────────────────────────────────────
echo -e "${YELLOW}Ingesting alarm data from ${ALARMS_FILE}...${NC}"

RESPONSE=$(curl -s -X POST "${BACKEND_URL}/ingest" \
    -H "Content-Type: application/json" \
    -d "{\"filepath\": \"${ALARMS_FILE}\"}")

echo ""
echo -e "Response: ${RESPONSE}" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

INGESTED=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('ingested','error'))" 2>/dev/null || echo "error")

if [ "$INGESTED" != "error" ] && [ "$INGESTED" -gt 0 ] 2>/dev/null; then
    echo ""
    echo -e "${GREEN}✅ Successfully ingested ${INGESTED} alarms${NC}"
    echo ""
    echo -e "${CYAN}📊 Dashboard: ${BACKEND_URL/8000/8080}${NC}"
    echo -e "${CYAN}📚 API Docs:  ${BACKEND_URL}/docs${NC}"
else
    echo -e "${YELLOW}⚠️  Ingestion had issues. Check backend logs:${NC}"
    echo "   docker compose -f docker/docker-compose.yml logs backend"
fi

echo ""
echo -e "${GREEN}✅ Done!${NC}"