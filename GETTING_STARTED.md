# Getting Started Guide

Welcome to the **Telecom AI Incident Resolution Copilot**! This guide will get you up and running in minutes.

## 📋 Prerequisites

- **Operating System**: Linux, macOS, or Windows with WSL2
- **Docker**: Latest stable version
- **Docker Compose**: v1.29+
- **System Requirements**:
  - CPU: 4 cores minimum (8+ recommended)
  - RAM: 8GB minimum (16GB+ recommended for comfort)
  - Disk: 20GB free (for models and data)
  - Network: Internet access (for initial setup)

### Check Prerequisites

```bash
# Docker
docker --version

# Docker Compose
docker-compose --version

# Disk space
df -h
```

## 🚀 Quick Start (2 minutes)

### Step 1: Navigate to Project

```bash
cd /home/king/itu
```

### Step 2: Run Setup

```bash
chmod +x setup.sh
./setup.sh
```

This script will:
- ✅ Pull Docker images
- ✅ Download Llama 2 7B model (~4GB)
- ✅ Build backend and frontend containers
- ✅ Start all services
- ✅ Initialize vector database

**Expected duration**: 5-10 minutes (mostly model download)

### Step 3: Verify System

```bash
python scripts/health_check.py
```

You should see:
```
✅ PASS - Docker
✅ PASS - Docker Containers
✅ PASS - Backend Health
✅ PASS - Streamlit UI
✅ PASS - Database Initialized
```

### Step 4: Open Web UI

Navigate to: **http://localhost:8501**

## 🎯 Your First Analysis

### Via Web UI (Recommended)

1. **Open** http://localhost:8501
2. **Select** a demo incident from the sidebar
3. **Click** "Load Demo"
4. **Click** "Analyze Incident"
5. **View** the structured report with RCA and metrics

### Via Command Line

```bash
# Single analysis
curl -X POST http://localhost:8000/analyze-incident \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "High packet loss on Node B12",
    "top_k_retrieval": 5,
    "temperature": 0.7
  }' | jq .
```

## 📊 Run Demo

For a quick end-to-end demonstration:

```bash
bash scripts/demo.sh
```

This runs 3 pre-configured incidents and shows:
- Incident analysis
- Retrieved context
- Performance metrics

## 🧪 Run Tests

Verify system integrity:

```bash
bash scripts/run_tests.sh
```

Tests:
- Backend health
- Database initialization
- Incident analysis
- Retrieval quality
- Metrics collection
- Error handling

## 📈 Run Evaluation

Comprehensive system evaluation:

```bash
bash scripts/evaluate.sh
```

Generates:
- Performance metrics for 5 diverse incidents
- Aggregated statistics
- System report saved to `results/evaluation_report_*.json`

## 📚 Accessing Documentation

| Resource | Location | Purpose |
|----------|----------|---------|
| **README** | [README.md](README.md) | System overview |
| **Architecture** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical design |
| **Demo Guide** | [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) | Demo script |
| **API Docs** | http://localhost:8000/docs | Interactive API reference |

## 🔧 Management Commands

### Start Services

```bash
# Foreground (see logs in real-time)
docker-compose -f docker/docker-compose.yml up

# Background
docker-compose -f docker/docker-compose.yml up -d
```

### Stop Services

```bash
docker-compose -f docker/docker-compose.yml down
```

### View Logs

```bash
# All services
docker-compose -f docker/docker-compose.yml logs -f

# Specific service
docker-compose -f docker/docker-compose.yml logs backend
docker-compose -f docker/docker-compose.yml logs ollama
docker-compose -f docker/docker-compose.yml logs frontend
```

### Check Service Status

```bash
docker-compose -f docker/docker-compose.yml ps
```

## 🔄 Adding Custom Data

### Add New Incidents

1. Edit `data/incidents/incidents.csv`
2. Add rows with: incident_id, name, description, root_cause, severity, resolution_steps, timestamp
3. Restart backend to re-index:
   ```bash
   docker-compose -f docker/docker-compose.yml restart backend
   ```

### Add New Manuals

1. Create `.md` file in `data/manuals/`
2. Restart backend
3. System automatically indexes new content

### Add Log Files

1. Add `.log` files to `data/logs/`
2. Restart backend

## 🐛 Troubleshooting

### Backend Not Responding

```bash
# Check service is running
docker-compose -f docker/docker-compose.yml ps

# View logs
docker-compose -f docker/docker-compose.yml logs backend

# Restart
docker-compose -f docker/docker-compose.yml restart backend
```

### Ollama Model Not Loading

```bash
# Check if pulling
docker-compose -f docker/docker-compose.yml logs ollama

# May take time on first run (~5-10 min for Llama 2)
# Check progress: ps aux | grep ollama
```

### Streamlit Not Accessible

```bash
# Check service
docker-compose -f docker/docker-compose.yml ps frontend

# Logs
docker-compose -f docker/docker-compose.yml logs frontend

# Try different port: edit docker-compose.yml, change 8501:8501
```

### Out of Memory

```bash
# Use smaller model
# Edit backend service in docker-compose.yml
# Change OLLAMA_MODEL from llama2 to phi

# Or increase Docker memory limit
# Docker Desktop: Settings → Resources → Memory
```

### Database Not Initialized

```bash
# Manually initialize
curl -X POST http://localhost:8000/initialize

# Check status
curl http://localhost:8000/stats
```

## 📊 Performance Tips

### For Faster Inference

1. **Use faster model**: Change `OLLAMA_MODEL` to `phi` (3B) or `mistral` (7B faster)
2. **Reduce context**: Set `TOP_K_RETRIEVAL=3` instead of 5
3. **Lower temperature**: Use 0.5 for faster convergence

### For Better Accuracy

1. **Use better model**: Upgrade to `mistral` or `llama2-uncensored`
2. **More context**: Increase `TOP_K_RETRIEVAL` to 10
3. **Add more data**: Expand `data/incidents/incidents.csv`

### For Scaling

1. **Multiple workers**: Deploy FastAPI with Gunicorn
2. **Distributed embedding**: Use Qdrant or Milvus instead of ChromaDB
3. **GPU inference**: Install CUDA for Ollama (check Ollama docs)

## 💾 Persistence & Cleanup

### Backup Data

```bash
# Backup vector database
cp -r data/chroma_db data/chroma_db.backup

# Backup custom incidents
cp data/incidents/incidents.csv data/incidents/incidents.csv.backup
```

### Clean Up

```bash
# Remove containers (data persisted)
docker-compose -f docker/docker-compose.yml down

# Full cleanup (removes everything)
docker-compose -f docker/docker-compose.yml down -v
rm -rf data/chroma_db
```

## 📞 Support

### Get Help

1. **Check logs**: `docker-compose logs`
2. **Test system**: `python scripts/health_check.py`
3. **Review README**: [README.md](README.md)
4. **Check Architecture**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

### View API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🎓 Learning Resources

### Understand the System

1. Read [ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design
2. Explore `backend/app.py` for orchestration logic
3. Check `services/*.py` for component details
4. Review `frontend/app.py` for UI code

### Extend the System

1. **Add new embedding model**: Modify `services/embedding_service.py`
2. **Change LLM**: Edit `services/llm_service.py`
3. **Custom metrics**: Extend `services/evaluation_service.py`
4. **New UI features**: Edit `frontend/app.py`

## ✅ Verification Checklist

After setup, verify:

- [ ] Docker is running: `docker ps`
- [ ] All containers healthy: `docker-compose ps`
- [ ] Backend responds: `curl http://localhost:8000/health`
- [ ] Frontend loads: Open http://localhost:8501
- [ ] Database has data: `curl http://localhost:8000/stats`
- [ ] Can analyze incident: Run demo or manual test
- [ ] Metrics collected: `curl http://localhost:8000/metrics`

## 🎉 Next Steps

1. **Try demos**: Run `bash scripts/demo.sh`
2. **Run tests**: Execute `bash scripts/run_tests.sh`
3. **Evaluate system**: Run `bash scripts/evaluate.sh`
4. **Add custom data**: Edit `data/incidents/incidents.csv`
5. **Explore API**: Visit http://localhost:8000/docs
6. **Review code**: Study `backend/app.py` and services

---

**You're all set! Enjoy the Telecom AI Incident Copilot! 🎉**
