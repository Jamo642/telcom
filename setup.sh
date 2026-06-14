#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}🚀 Telecom AI Incident Copilot - One-Command Setup${NC}"
echo "=============================================="
echo ""
echo -e "${BLUE}💡 DEPLOYMENT OPTIONS:${NC}"
echo ""
echo -e "${YELLOW}Option 1 - Fast (model downloads during first run):${NC}"
echo "   Just run: ${GREEN}./setup.sh${NC}"
echo ""
echo -e "${YELLOW}Option 2 - Production (model baked into image):${NC}"
echo "   First: ${GREEN}./build_ollama_with_model.sh${NC}  (requires internet, ~10 min)"
echo "   Then:  ${GREEN}./setup.sh${NC}  (no internet needed for deployment)"
echo ""

# Check Docker
echo -e "${YELLOW}Checking prerequisites...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed.${NC}"
    echo "   Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed.${NC}"
    exit 1
fi

# Check Docker daemon is running
if ! docker ps &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running.${NC}"
    echo "   Please start Docker Desktop or Docker daemon."
    exit 1
fi

echo -e "${GREEN}✅ Docker and Docker Compose found${NC}"
echo ""

# Create .env from .env.example if not exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo -e "${YELLOW}Creating .env configuration...${NC}"
        cp .env.example .env
        echo -e "${GREEN}✅ .env created${NC}"
    fi
fi

# Clean up old containers if they exist
echo -e "${YELLOW}Cleaning up old containers...${NC}"
docker compose -f docker/docker-compose.yml down --remove-orphans 2>/dev/null || true
echo -e "${GREEN}✅ Old containers cleaned${NC}"
echo ""

# Build Docker images
echo -e "${YELLOW}Building Docker images (backend, frontend)...${NC}"
docker compose -f docker/docker-compose.yml build --no-cache 2>&1 | grep -E "Building|Step|Successfully"
echo -e "${GREEN}✅ Images built${NC}"
echo ""

# Start Ollama service
echo -e "${YELLOW}Starting Ollama service...${NC}"
docker compose -f docker/docker-compose.yml up -d ollama 2>&1 | tail -1
echo -e "${GREEN}✅ Ollama container started${NC}"
echo ""

# Wait for Ollama to be ready and pull model
echo -e "${YELLOW}Waiting for Ollama to be ready...${NC}"
OLLAMA_READY=false
for i in {1..60}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Ollama is ready${NC}"
        OLLAMA_READY=true
        break
    fi
    echo -n "."
    sleep 2
done

if [ "$OLLAMA_READY" = false ]; then
    echo -e "${RED}❌ Ollama failed to start${NC}"
    docker compose -f docker/docker-compose.yml logs ollama | tail -20
    exit 1
fi

echo ""
echo -e "${YELLOW}Downloading Llama 2 7B model (first time only, ~4GB)...${NC}"
echo -e "${BLUE}This requires an internet connection. Retrying up to 3 times...${NC}"

# Try to pull model with retries
MODEL_PULLED=false
for attempt in {1..3}; do
    echo ""
    echo -e "${YELLOW}Attempt $attempt/3:${NC}"
    if timeout 900 docker compose -f docker/docker-compose.yml exec -T ollama ollama pull llama2 2>&1 | tail -10; then
        echo -e "${GREEN}✅ Llama 2 model ready${NC}"
        MODEL_PULLED=true
        break
    else
        if [ $attempt -lt 3 ]; then
            echo -e "${YELLOW}⚠️  Download attempt $attempt failed, retrying in 10 seconds...${NC}"
            sleep 10
        else
            echo -e "${YELLOW}⚠️  Model download failed after 3 attempts${NC}"
            echo -e "${YELLOW}   (The application can still run - model will be pulled on next startup if internet is available)${NC}"
        fi
    fi
done

if [ "$MODEL_PULLED" = false ]; then
    echo -e "${YELLOW}ℹ️  Continuing without model (will attempt to pull on container restart)${NC}"
fi

# Start Backend and Frontend
echo -e "${YELLOW}Starting Backend API and Streamlit Frontend...${NC}"
docker compose -f docker/docker-compose.yml up -d backend frontend 2>&1 | tail -2
echo -e "${GREEN}✅ Services started${NC}"
echo ""

# Wait for Backend to be ready
echo -e "${YELLOW}Waiting for Backend API to be ready...${NC}"
BACKEND_READY=false
for i in {1..60}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend API is ready${NC}"
        BACKEND_READY=true
        break
    fi
    echo -n "."
    sleep 2
done

if [ "$BACKEND_READY" = false ]; then
    echo -e "${RED}❌ Backend failed to start${NC}"
    docker compose -f docker/docker-compose.yml logs backend | tail -20
    exit 1
fi

echo ""

# Initialize database with synthetic data
echo -e "${YELLOW}Initializing database with incident data...${NC}"
if [ -f "scripts/initialize_data.py" ]; then
    if curl -s -X POST http://localhost:8000/initialize \
        -H "Content-Type: application/json" \
        -d '{}' > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Database initialized${NC}"
    else
        echo -e "${YELLOW}⚠️  Database initialization request sent (may still be processing)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Database initialization script not found${NC}"
fi

echo ""
echo "=============================================="
echo -e "${GREEN}✅ SETUP COMPLETE!${NC}"
echo "=============================================="
echo ""
echo -e "${BLUE}🌐 Access the application:${NC}"
echo "   🖥️  Frontend (Web UI): ${BLUE}http://localhost:8501${NC}"
echo "   🔧 Backend (API):     ${BLUE}http://localhost:8000${NC}"
echo "   📚 API Docs:         ${BLUE}http://localhost:8000/docs${NC}"
echo "   🤖 Ollama:           ${BLUE}http://localhost:11434${NC}"
echo ""
echo -e "${BLUE}💡 Next steps:${NC}"
echo "   1. Open http://localhost:8501 in your browser"
echo "   2. Select a demo incident"
echo "   3. Click 'Analyze Incident' to see the copilot in action"
echo ""
echo -e "${YELLOW}To stop all services:${NC}"
echo "   docker compose -f docker/docker-compose.yml down"
echo ""
echo -e "${YELLOW}To view logs:${NC}"
echo "   docker compose -f docker/docker-compose.yml logs -f"
echo ""
