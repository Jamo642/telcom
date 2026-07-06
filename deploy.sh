#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# TeleNOC AI - Deployment Script
# ═══════════════════════════════════════════════════════════════════
#
# Usage:
#   ./deploy.sh
#
# Prerequisites:
#   - Docker & Docker Compose
#   - OPENROUTER_API_KEY set in .env (get a free key at openrouter.ai)
# ═══════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        📡 TeleNOC AI - Deployment Script        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Step 1: Prerequisites ────────────────────────────────────────────
echo -e "${YELLOW}[1/5] Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed.${NC}"
    echo "   Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed.${NC}"
    exit 1
fi

if ! docker ps &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running. Please start Docker first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose ready${NC}"
echo ""

# ─── Step 2: Environment Configuration ────────────────────────────────
echo -e "${YELLOW}[2/5] Configuring environment...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env created from .env.example${NC}"
    fi
fi

# Source .env
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Check for AI provider key
if [ -n "$OPENROUTER_API_KEY" ] && [ "$OPENROUTER_API_KEY" != "your_openrouter_api_key_here" ]; then
    echo -e "${GREEN}✅ OpenRouter API key found — using OpenRouter as primary LLM${NC}"
    export LLM_PROVIDER=openrouter
elif [ -n "$GROQ_API_KEY" ]; then
    echo -e "${GREEN}✅ Groq API key found — using Groq as primary LLM${NC}"
    export LLM_PROVIDER=groq
elif [ -n "$NVIDIA_API_KEY" ]; then
    echo -e "${GREEN}✅ NVIDIA API key found — using NVIDIA as primary LLM${NC}"
    export LLM_PROVIDER=nvidia
else
    echo -e "${YELLOW}⚠️  No API key found. Falling back to local Ollama (slower, needs ~4GB download).${NC}"
    echo -e "${YELLOW}   Add OPENROUTER_API_KEY to .env for instant startup (free at openrouter.ai).${NC}"
    export LLM_PROVIDER=ollama
fi
echo ""

# ─── Step 3: Clean Up & Start Services ───────────────────────────────
echo -e "${YELLOW}[3/5] Cleaning up old containers...${NC}"
docker compose -f docker/docker-compose.yml down --remove-orphans 2>/dev/null || true
echo -e "${GREEN}✅ Old containers cleaned${NC}"
echo ""

echo -e "${YELLOW}[4/5] Building and starting services...${NC}"
echo -e "${BLUE}   Services: Redis, Backend (FastAPI + ChromaDB RAG + MITRE FiGHT), UI${NC}"
echo ""

# Build backend image
docker compose -f docker/docker-compose.yml build backend 2>&1 | grep -E "^#|Building|built|error" || true

# Start services — include ollama profile only when needed
if [ "$LLM_PROVIDER" = "ollama" ]; then
    COMPOSE_PROFILES=ollama docker compose -f docker/docker-compose.yml up -d
else
    docker compose -f docker/docker-compose.yml up -d
fi

echo -e "${GREEN}✅ Services started${NC}"
echo ""

# ─── Step 4: Wait for Backend ────────────────────────────────────────
echo -e "${YELLOW}[5/5] Waiting for backend to be ready...${NC}"

BACKEND_READY=false
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready${NC}"
        BACKEND_READY=true
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

if [ "$BACKEND_READY" = false ]; then
    echo -e "${RED}❌ Backend failed to start. Showing logs:${NC}"
    docker compose -f docker/docker-compose.yml logs backend --tail 30
    exit 1
fi

# ─── Step 5: Ingest Sample Data ──────────────────────────────────────
INGEST_RESULT=$(curl -s -X POST http://localhost:8000/ingest \
    -H "Content-Type: application/json" \
    -d '{"filepath": "/data/sample_alarms.json"}' 2>&1)

INGESTED=$(echo "$INGEST_RESULT" | grep -o '"ingested":[0-9]*' | cut -d: -f2)
if [ -n "$INGESTED" ] && [ "$INGESTED" -gt 0 ]; then
    echo -e "${GREEN}✅ Ingested $INGESTED sample alarms${NC}"
fi

# ─── Step 6: Ensure MITRE FiGHT techniques are in ChromaDB ──────────
# Check by counting fight_techniques.json entries vs chroma — fast, no model load
FIGHT_JSON_COUNT=$(docker compose -f docker/docker-compose.yml exec -T backend \
    python3 -c "
import json, pathlib
p = pathlib.Path('/data/fight_techniques.json')
print(len(json.loads(p.read_text())) if p.exists() else 0)
" 2>/dev/null)

CHROMA_FIGHT_COUNT=$(docker compose -f docker/docker-compose.yml exec -T backend \
    python3 -c "
import sys; sys.path.insert(0,'/app')
try:
    import chromadb
    c = chromadb.PersistentClient(path='/data/chroma_db')
    col = c.get_collection('telecom_incidents')
    print(len(col.get(where={'source':'mitre_fight'})['ids']))
except Exception:
    print(0)
" 2>/dev/null)

if [ "${CHROMA_FIGHT_COUNT:-0}" -lt "${FIGHT_JSON_COUNT:-1}" ] 2>/dev/null; then
    echo -e "${YELLOW}   Embedding MITRE FiGHT techniques into ChromaDB (offline mode)...${NC}"
    docker compose -f docker/docker-compose.yml exec -T \
        -e CHROMA_DB_PATH=/data/chroma_db \
        -e FIGHT_JSON=/data/fight_techniques.json \
        -e TRANSFORMERS_OFFLINE=1 \
        -e HF_DATASETS_OFFLINE=1 \
        -e SENTENCE_TRANSFORMERS_HOME=/root/.cache/torch/sentence_transformers \
        backend python3 /app/scripts/ingest_fight.py 2>&1 | grep -v "telemetry\|hugging\|Retry\|warned" | tail -6
    echo -e "${GREEN}✅ MITRE FiGHT techniques embedded${NC}"
else
    echo -e "${GREEN}✅ MITRE FiGHT already in ChromaDB (${CHROMA_FIGHT_COUNT}/${FIGHT_JSON_COUNT} techniques)${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅ DEPLOYMENT COMPLETE!                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}   🖥️  Dashboard:      http://localhost:8080${NC}"
echo -e "${CYAN}   🔧 API:            http://localhost:8000${NC}"
echo -e "${CYAN}   📚 API Docs:       http://localhost:8000/docs${NC}"
echo -e "${CYAN}   🤖 Agent Chat:     POST http://localhost:8000/agent/chat${NC}"
echo -e "${CYAN}   🛡️  FiGHT Engine:  detect_fight_techniques tool via agent${NC}"
echo ""
echo -e "${YELLOW}🛑 To stop:${NC} docker compose -f docker/docker-compose.yml down"
echo -e "${YELLOW}📖 Logs:${NC}   docker compose -f docker/docker-compose.yml logs -f backend"
echo ""
