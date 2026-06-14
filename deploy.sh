#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# TeleNOC AI - One-Click Deployment Script
# ═══════════════════════════════════════════════════════════════════
# 
# Usage:
#   ./deploy.sh              # Deploy with NVIDIA API (recommended for judges)
#   NVIDIA_API_KEY="" ./deploy.sh  # Deploy with Ollama fallback only
#
# Prerequisites:
#   - Docker & Docker Compose
#   - 4-core CPU, 8GB RAM minimum
#   - Internet connection (for API-based AI inference)
#
# This script will:
#   1. Check prerequisites
#   2. Create .env from .env.example if needed
#   3. Start all Docker services
#   4. Initialize database
#   5. Ingest sample alarm data
#   6. Print access URLs
# ═══════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        📡 TeleNOC AI - Deployment Script        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ─── Step 1: Prerequisites ────────────────────────────────────────────
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

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
    echo -e "${RED}❌ Docker daemon is not running.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose found${NC}"
echo ""

# ─── Step 2: Environment Configuration ────────────────────────────────
echo -e "${YELLOW}[2/6] Configuring environment...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ .env created from .env.example${NC}"
        echo -e "${YELLOW}   📝 Edit .env to add your API keys if needed${NC}"
    fi
else
    echo -e "${GREEN}✅ .env already exists${NC}"
fi

# Source .env if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Check for AI provider
if [ -n "$NVIDIA_API_KEY" ]; then
    echo -e "${GREEN}✅ NVIDIA API key found — using NVIDIA AI as primary provider${NC}"
elif [ -n "$GROQ_API_KEY" ]; then
    echo -e "${GREEN}✅ Groq API key found — using Groq as primary provider${NC}"
else
    echo -e "${YELLOW}⚠️  No API keys found. Will use Ollama (local fallback).${NC}"
    echo -e "${YELLOW}   To use NVIDIA AI (recommended), set NVIDIA_API_KEY in .env${NC}"
fi
echo ""

# ─── Step 3: Clean Up Old Containers ─────────────────────────────────
echo -e "${YELLOW}[3/6] Cleaning up old containers...${NC}"
docker compose -f docker/docker-compose.yml down --remove-orphans 2>/dev/null || true
echo -e "${GREEN}✅ Old containers cleaned${NC}"
echo ""

# ─── Step 4: Start Services ──────────────────────────────────────────
echo -e "${YELLOW}[4/6] Starting Docker services...${NC}"
echo -e "${BLUE}   This will start: ChromaDB, Ollama, Backend, UI${NC}"
echo ""

# Start all services
docker compose -f docker/docker-compose.yml up -d 2>&1 | tail -3
echo -e "${GREEN}✅ All services started${NC}"
echo ""

# ─── Step 5: Wait for Backend ────────────────────────────────────────
echo -e "${YELLOW}[5/6] Waiting for backend to be ready...${NC}"

BACKEND_READY=false
for i in $(seq 1 60); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready (attempt $i)${NC}"
        BACKEND_READY=true
        break
    fi
    if [ $((i % 10)) -eq 0 ]; then
        echo -n "."
    fi
    sleep 2
done

if [ "$BACKEND_READY" = false ]; then
    echo -e "${RED}❌ Backend failed to start${NC}"
    docker compose -f docker/docker-compose.yml logs backend --tail 20
    exit 1
fi
echo ""

# ─── Step 6: Ingest Sample Data ──────────────────────────────────────
echo -e "${YELLOW}[6/6] Ingesting sample alarm data...${NC}"

INGEST_RESULT=$(curl -s -X POST http://localhost:8000/ingest \
    -H "Content-Type: application/json" \
    -d '{"filepath": "/data/sample_alarms.json"}' 2>&1)

INGESTED=$(echo "$INGEST_RESULT" | grep -o '"ingested":[0-9]*' | cut -d: -f2)
if [ -n "$INGESTED" ] && [ "$INGESTED" -gt 0 ]; then
    echo -e "${GREEN}✅ Ingested $INGESTED sample alarms${NC}"
else
    echo -e "${YELLOW}⚠️  Ingestion result: $INGEST_RESULT${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅ DEPLOYMENT COMPLETE!                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📡 TeleNOC AI is now running!${NC}"
echo ""
echo -e "${CYAN}   🖥️  Dashboard:    http://localhost:8080${NC}"
echo -e "${CYAN}   🔧 API:          http://localhost:8000${NC}"
echo -e "${CYAN}   📚 API Docs:     http://localhost:8000/docs${NC}"
echo -e "${CYAN}   💾 ChromaDB:     http://localhost:8001${NC}"
echo ""
echo -e "${YELLOW}📋 Quick Demo:${NC}"
echo -e "   1. Open ${CYAN}http://localhost:8080${NC} in your browser"
echo -e "   2. Click '📥 Ingest All 50 Sample Alarms'"
echo -e "   3. Use the Diagnose tab to analyze alarms"
echo -e "   4. Check Incidents, MTTR, Trends, and Escalations tabs"
echo ""
echo -e "${YELLOW}🛑 To stop all services:${NC}"
echo -e "   docker compose -f docker/docker-compose.yml down -v"
echo ""
echo -e "${YELLOW}📖 To view logs:${NC}"
echo -e "   docker compose -f docker/docker-compose.yml logs -f backend"
echo ""