# 🏆 Submission Summary — TeleNOC AI

## 📦 What You're Submitting

An **autonomous, tool-using AI agent** for telecom Network Operations Centres (NOCs) that reduces alert triage time from ~8 min to ~45 s through OPEA-compliant RAG microservices, MITRE FiGHT 5G threat detection, and gated remediation.

---

## 🚀 Getting Started (For Judges)

### One-Command Deploy

```bash
git clone https://github.com/Jamo642/telcom.git
cd telcom
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY (free at https://openrouter.ai)
./deploy.sh
```

**What happens**:
1. ✅ Checks Docker + Docker Compose are installed
2. ✅ Reads API key from `.env` (NVIDIA / OpenRouter / Groq — any one will do)
3. ✅ Builds backend image (FastAPI + ChromaDB + MITRE FiGHT engine)
4. ✅ Starts Redis → Backend → NGINX UI
5. ✅ Ingests 50 sample alarms into SQLite
6. ✅ Embeds MITRE FiGHT techniques into ChromaDB

**Time**: ~3–4 min cold · ~30 s warm (no GPU, no large model downloads)

### Access the Application

| Interface | URL |
|---|---|
| Web UI | http://localhost:8080 |
| REST API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| OPEA Health | http://localhost:8000/opea/health |

---

## 📚 Documentation Structure

### Core Documentation (For Judges)
```
JUDGES_GUIDE.md        ← START HERE (evaluation walkthrough)
TECHNICAL_REPORT.md    ← Full technical write-up
OPEA_ALIGNMENT.md      ← OPEA component mapping
BUSINESS_CASE.md       ← ROI analysis
ARCHITECTURE.md        ← System design
```

### Source Code (All Complete)
```
backend/app.py          ← FastAPI orchestrator
backend/noc_agent.py    ← ReAct tool-using agent loop
backend/fight_engine.py ← MITRE FiGHT detection pipeline
backend/ingest.py       ← Alarm ingestion
services/llm_service.py ← LLM provider chain
ui/index.html           ← Single-page NOC dashboard
```

### Deployment (Fully Automated)
```
deploy.sh                    ← One-command setup
docker/docker-compose.yml    ← Service orchestration
docker/Dockerfile.backend    ← Backend container
docker/nginx.conf            ← NGINX reverse proxy
```

### Data
```
data/sample_alarms.json      ← 50 synthetic NOC alarms
data/fight_techniques.json   ← 10 MITRE FiGHT techniques
data/logs/                   ← Network log files
data/runbooks/               ← Telecom runbooks (RAG source)
```

---

## 🎯 Submission Form Values

| Form Field | Value |
|---|---|
| ApplicationName | TeleNOC AI |
| IndustryVertical | Telecommunications |
| OpenSourceCommitment | True (Apache 2.0) |
| OPEAComponents | LLM, RAG, Vector DB, Orchestration |
| Project URL | https://github.com/Jamo642/telcom |

**Method name:** Autonomous Tool-Using NOC Agent with MITRE FiGHT 5G Threat Detection

**Method description:** TeleNOC AI is a ReAct-style tool-using AI agent for telecom NOCs. It queries live alarm databases, retrieves runbook knowledge via OPEA RAG (embedding-tei + retriever-redis + chatqna), detects MITRE FiGHT 5G attack patterns across SS7/GTP/RAN interfaces, and presents gated remediation steps requiring operator approval before execution. OPEA components: LLM, RAG, Vector DB, Orchestration.

---

## 🎯 Scoring Breakdown

### Base Score (100 pts)

| Category | Points | Evidence |
|---|---|---|
| **OPEA Usage** | 20 | `opea/embedding-tei`, `opea/retriever-redis`, `opea/dataprep`, `opea/chatqna` in docker-compose; `/opea/health` endpoint |
| **System Efficiency** | 20 | ~1.4 GB RAM total; 4-core CPU; no GPU; 15–45 s agent response |
| **Originality** | 15 | MITRE FiGHT detection, gated remediation, self-critique pass |
| **Business Relevance** | 15 | BUSINESS_CASE.md — 8 min → 45 s triage; SS7/GTP threat coverage |
| **Code Quality** | 15 | Type hints, docstrings, PEP 8; modular service architecture |
| **Completeness** | 15 | Full agent + RAG + UI + Docker + one-command deploy |

---

## 📋 What's in the Box

### ✅ Fully Functional System
- [x] FastAPI backend with agent, diagnose, ingest, escalation, and OPEA health endpoints
- [x] NGINX-served single-page UI (4 tabs: Diagnose, AI Agent, FiGHT, Escalations)
- [x] ChromaDB vector database with 50 runbooks + 10 MITRE FiGHT embeddings
- [x] OpenRouter / NVIDIA NIM / Groq LLM chain with automatic fallback
- [x] ReAct tool-using agent loop (max 8 iterations, fully logged to SQLite)
- [x] MITRE FiGHT pipeline: 10 techniques, confidence scoring, self-critique pass
- [x] Gated remediation: approve-before-execute, logged to `/data/fight_remediations.jsonl`
- [x] One-command deployment (`./deploy.sh`)

### ✅ OPEA Components
- [x] `opea/embedding-tei` — vectorises alarm text and runbooks
- [x] `opea/retriever-redis` — semantic search over knowledge base
- [x] `opea/dataprep` — document ingestion pipeline
- [x] `opea/chatqna` — RAG orchestration
- [x] All four under `profile: opea` (enable with `./deploy.sh --opea`)
- [x] `/opea/health` exposes live reachability status

### ✅ Complete Documentation
- [x] JUDGES_GUIDE.md — evaluation walkthrough with curl commands
- [x] TECHNICAL_REPORT.md — architecture, OPEA integration, metrics
- [x] OPEA_ALIGNMENT.md — component mapping
- [x] BUSINESS_CASE.md — ROI analysis
- [x] DEPLOYMENT_GUIDE.md — deployment reference
- [x] Apache 2.0 LICENSE

---

## 🔧 Technical Specifications

| Parameter | Value |
|---|---|
| Deploy command | `./deploy.sh` |
| Cold start | ~3–4 min |
| Warm start | ~30 s |
| RAM (default) | ~1.4 GB (backend 1 GB + Redis 256 MB + UI 128 MB) |
| RAM (with OPEA) | ~8 GB additional |
| CPU | 4-core; no GPU required |
| LLM | OpenRouter free tier (nvidia/nemotron or llama-3.3-70b fallback) |
| Embedding | BAAI/bge-small-en-v1.5 (130 MB, baked into Docker image) |
| Vector DB | ChromaDB (persistent) |
| Database | SQLite (`/data/telenoc.db`) |

---

## 🎬 Evaluation Path (20 minutes)

### Phase 1: Deploy (5 min)
```bash
./deploy.sh
```
See: Redis healthy → backend healthy → "DEPLOYMENT COMPLETE" banner

### Phase 2: Quick API checks (5 min)
```bash
# Health
curl http://localhost:8000/health

# Agent answers a NOC question
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the most critical active alerts?"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:400])"

# FiGHT threat detection
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Run detect_fight_techniques on: SS7 MAP SRI queries flooding from external ISPC on STP-Core-01"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:400])"
```

### Phase 3: UI walkthrough (5 min)
- Open http://localhost:8080
- **Diagnose tab** — submit any alarm text, observe AI root-cause + "How to Fix"
- **AI Agent tab** — ask a free-text NOC question
- **FiGHT tab** — paste alarm text, observe MITRE technique match + Approve/Dismiss card

### Phase 4: OPEA stack (optional, 5 min)
```bash
./deploy.sh --opea    # starts embedding-tei, retriever-redis, dataprep, chatqna
curl http://localhost:8000/opea/health
```

---

*Apache 2.0 · Submitted to the OPEA × ITU AI for Good Hackathon 2025 by Jamo642*
