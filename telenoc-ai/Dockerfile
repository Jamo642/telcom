# ═══════════════════════════════════════════════════════════════════
# TeleNOC AI - Backend Dockerfile
# FastAPI + OPEA RAG integration + Custom Agent Logic
# ═══════════════════════════════════════════════════════════════════
#
# Uses NVIDIA API (primary) with Groq/HuggingFace/Ollama fallback.
# No GPU required — all LLM inference via API calls.
# ═══════════════════════════════════════════════════════════════════

FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY ui/ ./ui/
COPY data/ ./data/

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI app
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]