# 🚀 Telecom AI Incident Copilot - Quick Start

## One-Command Deploy (Recommended)

```bash
bash setup.sh
```

That's it! The script will:
- ✅ Check Docker is installed
- ✅ Download Docker images (Ollama, FastAPI, Streamlit)
- ✅ Auto-download Llama 2 7B LLM (~4GB, one-time only)
- ✅ Build and start all services
- ✅ Initialize the vector database
- ✅ Print access URLs

**Total time**: 5-15 minutes (mostly model download on first run)

---

## After Setup Completes

### 🌐 Access the Web UI
Open your browser: **http://localhost:8501**

### 🔧 Access the API
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Backend API**: http://localhost:8000

### 🤖 Access Ollama
- **Ollama Interface**: http://localhost:11434

---

## Test the App

### Via Web UI (5 seconds)
1. Navigate to http://localhost:8501
2. Select a demo incident from the dropdown
3. Click "Load Demo"
4. Click "Analyze Incident"
5. See the RCA report with metrics

### Via Command Line
```bash
curl -X POST http://localhost:8000/analyze-incident \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "High packet loss on Node B12",
    "top_k_retrieval": 5
  }' | jq .
```

---

## Managing Services

### 🛑 Stop All Services
```bash
docker compose -f docker/docker-compose.yml down
```

### 📊 View Logs
```bash
docker compose -f docker/docker-compose.yml logs -f
```

### 🔄 Restart Services
```bash
docker compose -f docker/docker-compose.yml restart
```

### 🗑️ Clean Everything (Fresh Start)
```bash
docker compose -f docker/docker-compose.yml down -v
bash setup.sh
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **"Docker is not installed"** | Install Docker: https://docs.docker.com/get-docker/ |
| **"Docker daemon is not running"** | Start Docker Desktop or Docker daemon |
| **Port 8501 already in use** | Kill the process: `lsof -i :8501 \| grep LISTEN \| awk '{print $2}' \| xargs kill -9` |
| **Port 8000 already in use** | Kill the process: `lsof -i :8000 \| grep LISTEN \| awk '{print $2}' \| xargs kill -9` |
| **Ollama download fails** | Check internet connection and restart: `bash setup.sh` |
| **Backend won't start** | Check logs: `docker compose logs backend` |

---

## System Requirements

- **OS**: Linux, macOS, or Windows (WSL2)
- **CPU**: 4 cores minimum (8+ recommended)
- **RAM**: 8GB minimum (16GB+ recommended)
- **Disk**: 20GB free (for models and data)
- **Internet**: Required for initial setup only

---

## What's Running

- **Ollama** (Port 11434): Local LLM inference engine
- **FastAPI Backend** (Port 8000): Orchestration and RAG pipeline
- **Streamlit Frontend** (Port 8501): Web UI for incident analysis

All services run in Docker containers for easy isolation and deployment.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Browser (Port 8501)                       │
│              Streamlit Web UI (Frontend)                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
                    HTTP API (Port 8000)
                            │
┌───────────────────────────▼─────────────────────────────────┐
│              FastAPI Backend (Orchestrator)                 │
│  ┌──────────────┬──────────────┬──────────────────────┐    │
│  │   Embedding  │  Retrieval   │  LLM Service         │    │
│  │  (sentence-  │ (ChromaDB +  │ (Ollama Llama2)      │    │
│  │ transformers)│  semantic    │                      │    │
│  │              │  search)     │                      │    │
│  └──────────────┴──────────────┴──────────────────────┘    │
└────────────────────┬──────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
    Port 11434              ChromaDB Vector
    (Ollama)              Database (/data)
```

---

## Next Steps

1. **Explore the API**: Visit http://localhost:8000/docs
2. **Run a demo**: Upload a telecom incident and see the analysis
3. **Check metrics**: View performance dashboards in the web UI
4. **Customize**: Modify incident data in `/data/` directory

---

## Support

For issues, check:
- Setup logs: `bash setup.sh 2>&1 | tee setup.log`
- Docker logs: `docker compose logs -f`
- Specific service: `docker compose logs -f <service-name>`

---

Enjoy your AI-powered telecom incident analysis! 🎉
