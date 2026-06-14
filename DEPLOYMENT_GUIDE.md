# 🚀 Telecom AI Incident Copilot - Deployment Guide

## Quick Start (One Command)

```bash
./setup.sh
```

This downloads everything and starts the application at:
- **Frontend**: http://localhost:8501
- **Backend API**: http://localhost:8000

---

## Production Deployment (Model Baked Into Image)

### **For Offline/No-Internet Environments**

This is the **best option** if judges/users won't have internet when deploying.

**Step 1: Build image with model (one-time, requires internet, ~10 min)**
```bash
chmod +x build_ollama_with_model.sh
./build_ollama_with_model.sh
```

This:
- Builds the Ollama Docker image
- Pre-downloads the 4GB Llama 2 model
- Stores it in a Docker volume (`ollama_model_cache`)
- Creates image: `ollama:with-model-local`

**Step 2: Switch docker-compose to use pre-built image**

Edit `docker/docker-compose.yml`, change the ollama service from:
```yaml
ollama:
  build:
    context: .
    dockerfile: Dockerfile.ollama
```

To:
```yaml
ollama:
  image: ollama:with-model-local
```

**Step 3: Deploy anywhere (no internet required)**
```bash
./setup.sh
```

Everything works instantly - model is already baked in!

---

## For Limited Internet Environments

### **Scenario 1: You have internet NOW, but won't during deployment**

**Step 1: Pre-download the model (optional, alternative to build)**
```bash
chmod +x download_ollama_model.sh
./download_ollama_model.sh
```

**Step 2: Deploy anywhere**
```bash
./setup.sh
```
Uses the pre-downloaded model from persistent Docker volume.

---

### **Scenario 2: Offline deployment**

1. **On a machine with internet:**
   ```bash
   ./build_ollama_with_model.sh
   ```

2. **Transfer the Docker image (if needed):**
   ```bash
   docker save ollama:with-model-local | gzip > ollama_with_model.tar.gz
   ```
   Transfer the file (2GB) to target machine.

3. **On target machine (no internet):**
   ```bash
   docker load < ollama_with_model.tar.gz
   # Update docker/docker-compose.yml to use: image: ollama:with-model-local
   ./setup.sh
   ```

---

## What's Included

✅ **Auto-starting services** (depends_on ensures correct order):
- Ollama (LLM inference engine)
- Backend API (FastAPI + ChromaDB)
- Frontend (Streamlit UI)

✅ **Network fixes**:
- DNS configured to 8.8.8.8 for reliable internet access
- Service-to-service communication via Docker network

✅ **Smart model handling**:
- **Option 1**: Downloads once, reuses across restarts (works anywhere)
- **Option 2**: Model baked into image (fastest, no runtime downloads)
- Graceful degradation if internet unavailable
- Retry logic with proper error messages

---

## Troubleshooting

### Model build taking too long?
The build process is normal - downloading 4GB takes 5-10 minutes depending on internet speed.
Monitor progress:
```bash
docker ps  # See ollama_build_temp container
docker logs ollama_build_temp -f
```

### "Image not found: ollama:with-model-local"?
Run the build first:
```bash
./build_ollama_with_model.sh
```

### Backend shows "unhealthy" but working?
```bash
curl http://localhost:8000/health
```
The health check is strict. If API responds, it's working.

### Model won't download?
Make sure you have **at least 5GB free disk space** and internet connection.
Then run: 
```bash
./build_ollama_with_model.sh
```

### Services not starting?
Check logs:
```bash
docker compose -f docker/docker-compose.yml logs
```

### Clean restart?
```bash
docker compose -f docker/docker-compose.yml down --volumes
./setup.sh
```

---

## Architecture

```
User → Frontend (Streamlit on 8501)
         ↓
       Backend API (FastAPI on 8000)
         ├─ Embedding Service (sentence-transformers)
         ├─ Retrieval Service (ChromaDB vector DB)
         ├─ LLM Service → Ollama (Llama 2 on 11434)
         └─ Evaluation Service (metrics)
```

All services automatically start in dependency order via `docker compose up -d`.

---

## Key Files

| File | Purpose |
|------|---------|
| `setup.sh` | One-command deployment (fast, requires internet) |
| `build_ollama_with_model.sh` | **NEW** - Build image with model baked in (production) |
| `download_ollama_model.sh` | Alternative: Download model to persistent volume |
| `docker/docker-compose.yml` | Service orchestration with `depends_on` |
| `docker/Dockerfile.backend` | Backend API image |
| `docker/Dockerfile.frontend` | Frontend UI image |
| `docker/Dockerfile.ollama` | Ollama with smart startup (handles model pulling) |
