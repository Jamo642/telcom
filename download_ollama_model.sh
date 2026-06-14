#!/bin/bash

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}📦 Ollama Model Download Script${NC}"
echo "=================================="
echo ""

# Check if models directory exists
MODELS_DIR="$HOME/.ollama/models"
mkdir -p "$MODELS_DIR"

echo -e "${YELLOW}Model directory: $MODELS_DIR${NC}"
echo ""

# Check if docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Starting local Ollama pull (requires internet)...${NC}"
    echo "Make sure Ollama is installed: https://ollama.ai"
    echo ""
    echo "Run this command to pull llama2:"
    echo "  ollama pull llama2"
    exit 0
fi

# Use Docker to download model (with proper volume mounting)
echo -e "${YELLOW}Downloading Llama 2 7B model (this may take 5-10 minutes)...${NC}"
echo "This will be saved to: $MODELS_DIR"
echo ""

docker run -it \
    -v "$MODELS_DIR:/root/.ollama/models" \
    ollama/ollama:latest \
    ollama pull llama2

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Model downloaded successfully!${NC}"
    echo ""
    echo "Model is saved at: $MODELS_DIR"
    echo ""
    echo -e "${BLUE}📝 Next steps:${NC}"
    echo "1. Run: ./setup.sh"
    echo "2. The application will use the downloaded model (no internet needed)"
else
    echo -e "${YELLOW}⚠️  Download failed. Please check your internet connection.${NC}"
    exit 1
fi
