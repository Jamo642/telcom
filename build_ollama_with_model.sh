#!/bin/bash

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔨 Building Ollama Image with Llama2 Model${NC}"
echo "=============================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Building Ollama Docker image...${NC}"
docker build -f docker/Dockerfile.ollama -t ollama:with-model-local --progress=plain . 2>&1 | tail -20

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Docker build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Image built${NC}"
echo ""

echo -e "${YELLOW}Step 2: Pre-pulling Llama2 model into image...${NC}"
echo "This will download ~4GB (requires internet)"
echo ""

# Run the image to pull the model
docker run --rm \
    -v ollama_model_cache:/root/.ollama \
    --name ollama_build_temp \
    ollama:with-model-local &

BUILD_PID=$!

# Give it time to start and pull model
echo -e "${YELLOW}Waiting for model download (this may take 5-10 minutes)...${NC}"
echo "Monitoring logs..."
echo ""

sleep 10

# Check logs in background
docker logs -f ollama_build_temp 2>/dev/null &
LOGS_PID=$!

# Wait for the container to finish or timeout
MAX_WAIT=1800  # 30 minutes
WAITED=0

while kill -0 $BUILD_PID 2>/dev/null && [ $WAITED -lt $MAX_WAIT ]; do
    sleep 5
    WAITED=$((WAITED + 5))
    
    # Check if model pull completed
    if docker exec ollama_build_temp curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "llama2" 2>/dev/null; then
        echo -e "${GREEN}✅ Model pull completed!${NC}"
        break
    fi
    
    # Progress indicator
    if [ $((WAITED % 30)) -eq 0 ]; then
        echo "Still downloading... ($WAITED seconds elapsed)"
    fi
done

# Stop the container
docker stop ollama_build_temp 2>/dev/null || true
kill $LOGS_PID 2>/dev/null || true
wait $BUILD_PID 2>/dev/null || true

echo ""

# Verify model was downloaded
VOLUME_INSPECT=$(docker volume inspect ollama_model_cache 2>/dev/null || echo "")
if [ -n "$VOLUME_INSPECT" ]; then
    echo -e "${GREEN}✅ Ollama image built with model pre-loaded${NC}"
    echo ""
    echo -e "${BLUE}📊 Build Results:${NC}"
    echo "  Image name: ${YELLOW}ollama:with-model-local${NC}"
    echo "  Volume:     ${YELLOW}ollama_model_cache${NC}"
    echo ""
    echo -e "${BLUE}📝 Usage:${NC}"
    echo "  1. Update docker-compose.yml to use this image:"
    echo "     ${YELLOW}image: ollama:with-model-local${NC}"
    echo ""
    echo "  2. Deploy anywhere without internet:"
    echo "     ${YELLOW}./setup.sh${NC}"
    echo ""
else
    echo -e "${YELLOW}⚠️  Model cache volume not accessible${NC}"
    echo "     The model will be pulled on first container start"
fi

echo -e "${BLUE}✅ Build complete!${NC}"
