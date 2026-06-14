# ⚡ QUICK START - Telecom AI Incident Copilot

## 🚀 **For Judges - Run This:**

### **Option 1: Fastest (assumes you have internet)**
```bash
./setup.sh
```
Done! Open http://localhost:8501

---

### **Option 2: Production-Ready (for offline/no-internet environments)**
```bash
./build_ollama_with_model.sh    # Takes ~10 min (requires internet ONLY for this step)
./setup.sh                       # Then deploy anywhere, anytime
```
Done! Open http://localhost:8501

---

## 📍 **What This Does**

| Component | Port | Purpose |
|-----------|------|---------|
| Frontend (Streamlit) | 8501 | Web interface |
| Backend API | 8000 | RAG engine |
| Ollama (LLM) | 11434 | Llama 2 inference |
| ChromaDB | Internal | Vector database |

---

## ✅ **What You Get**

✓ One-command deployment  
✓ Automatic service startup (ollama → backend → frontend)  
✓ No internet needed at runtime (if pre-built with Option 2)  
✓ 40+ synthetic telecom incidents + logs + knowledge base pre-loaded  
✓ Full RAG pipeline: embed → retrieve → analyze → evaluate  

---

## 🎯 **Try It Out**

1. Open: **http://localhost:8501**
2. Select a demo incident from dropdown
3. Click **"Analyze Incident"**
4. See the AI analysis with:
   - Root cause analysis
   - Evidence from knowledge base
   - Recommended actions
   - Confidence scores
   - Similar past incidents

---

## 🛠️ **If Something Goes Wrong**

**Backend not responding?**
```bash
docker compose -f docker/docker-compose.yml logs backend
```

**Ollama model won't download?**
Make sure you have:
- ✅ At least 5GB free disk space
- ✅ Working internet connection
- ✅ Docker running

Then retry: `./setup.sh`

**Need a clean restart?**
```bash
docker compose -f docker/docker-compose.yml down --volumes
./setup.sh
```

---

## 📚 **Full Documentation**

See `DEPLOYMENT_GUIDE.md` for:
- Detailed setup options
- Offline deployment strategies
- Troubleshooting guide
- Architecture overview

---

## 🎓 **How It Works**

```
Your Incident Description
         ↓
   [Frontend - Streamlit UI]
         ↓
   [Backend API - FastAPI]
         ├─ Embed: Convert incident to vector
         ├─ Retrieve: Find similar incidents/logs/manuals from vector DB
         ├─ Analyze: Send to Ollama (Llama 2) for structured reasoning
         ├─ Evaluate: Score confidence & relevance
         └─ Return: Comprehensive RCA report
         ↓
   [Your AI-Generated Report]
```

All components auto-start and communicate via Docker network.

---

## 🎨 **Architecture**

```
┌─────────────────────────────────────────┐
│  Frontend (Streamlit)                   │
│  http://localhost:8501                  │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Backend API (FastAPI)                  │
│  http://localhost:8000                  │
├──────────────┬──────────────────────────┤
│              │                          │
│  Services    │                          │
│  ├─ Embedding (sentence-transformers)  │
│  ├─ Retrieval (ChromaDB)                │
│  ├─ LLM (Ollama → Llama 2)              │
│  └─ Evaluation (metrics)                │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│  Ollama (LLM Inference)                 │
│  http://localhost:11434                 │
│  Model: Llama 2 7B                      │
└─────────────────────────────────────────┘
```

---

**Questions? See DEPLOYMENT_GUIDE.md or check container logs:**
```bash
docker compose -f docker/docker-compose.yml logs -f
```
