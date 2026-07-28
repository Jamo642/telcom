# TeleNOC AI — Autonomous Telecom NOC Assistant

An autonomous, tool-using AI agent for telecom Network Operations Centres (NOC).  
Built for the **OPEA × ITU Innovation Challenge**.

## What It Does

- **AI Agent** — multi-step tool-using loop (not a chatbot): queries live alerts, logs, runbooks, and MITRE FiGHT threat database to answer NOC questions
- **MITRE FiGHT 5G Detection** — matches SS7/GTP/5G-core/RAN alarm patterns against 10 curated FiGHT techniques with confidence scoring and self-critique
- **RAG Knowledge Base** — ChromaDB vector search over 50 telecom runbooks and past incidents (BAAI/bge-small-en-v1.5 embeddings)
- **Gated Remediation** — agent proposes fixes; operator clicks **Approve & Apply** — mutating actions never auto-execute
- **Alarm Diagnosis** — root-cause classification + "How to Fix" section with agent-generated step-by-step instructions

## One-Click Setup

```bash
git clone https://github.com/Jamo642/telcom.git
cd telcom
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY (free at https://openrouter.ai)
./deploy.sh
```

Open **http://localhost:8080** when the script completes (~3–4 min cold, ~30 s warm).

**With full OPEA microservice stack:**
```bash
./deploy.sh --opea   # starts embedding-tei, retriever-redis, dataprep, chatqna
```

## Requirements

- Docker + Docker Compose
- 4-core CPU, ≤ 64 GB RAM (uses ~1.4 GB total)
- No GPU required — LLM is via OpenRouter free API
- Internet access for OpenRouter API calls

## Architecture

```
Browser (UI)  →  nginx:8080
                    ↓
FastAPI backend:8000
  ├── /agent/chat      ← tool-using agent loop
  ├── /diagnose        ← severity + root-cause
  ├── /ingest          ← alarm ingestion
  └── /escalations     ← escalation queue

Backend tools:
  ├── get_active_alerts      → SQLite (telenoc.db)
  ├── get_logs               → data/logs/*.log
  ├── lookup_incident        → SQLite
  ├── search_knowledge_base  → ChromaDB (BAAI/bge-small-en-v1.5)
  ├── detect_fight_techniques → fight_engine.py (10 MITRE FiGHT techniques)
  ├── explain_fight_technique → ChromaDB RAG + LLM
  └── remediate_fight_technique → gated (confirmed=true required)

LLM: OpenRouter free tier (nvidia/nemotron-3-super-120b-a12b:free, ~1.5s)
     Fallback chain: nemotron-ultra → gemma-4-31b → nemotron-nano
```

## UI Tabs

| Tab | What it does |
|---|---|
| 🔍 **Diagnose** | Submit alarm → AI root-cause + severity + "How to Fix" with one-click agent fix steps |
| 🤖 **AI Agent** | Ask any NOC question — agent calls real tools and streams a structured answer |
| 🛡️ **FiGHT** | Paste alarm/log text → MITRE FiGHT 5G threat scan with confidence tiers + approve/dismiss remediation |
| 🔔 **Escalations** | Live escalation queue |

## Configuration

```bash
cp .env.example .env
```

Key variables in `.env`:

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | **Required.** Free key from https://openrouter.ai |
| `OPENROUTER_MODEL` | Default: `nvidia/nemotron-3-super-120b-a12b:free` (fast, ~1.5s) |

## OPEA Integration

OPEA services (`embedding`, `retriever`, `dataprep`, `chatqna`) are included in `docker/docker-compose.yml` under `profile: [opea]`.  
They are **off by default** to stay within the 10-minute setup constraint.  
The system uses its own embedding stack (sentence-transformers + ChromaDB) which is baked into the Docker image at build time.

To enable full OPEA stack:
```bash
COMPOSE_PROFILES=opea docker compose -f docker/docker-compose.yml up -d
```

## Demo Commands

```bash
# Check system health
curl http://localhost:8000/health

# Diagnose a telecom alarm (rule-based, no API key needed)
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"alarm_text": "BGP session dropped on Router-KNB-04", \
       "alarm_id": "ALM-001", "node_name": "Router-KNB-04", "alarm_type": "bgp"}'

# Test FiGHT security detection
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{"alarm_text": "SS7 MAP send routing info requests detected on STP-01", \
       "alarm_id": "ALM-051", "node_name": "STP-01", "alarm_type": "security"}'

# Check MTTR stats
curl http://localhost:8000/mttr

# View pending human approvals
curl http://localhost:8000/approvals/pending

# Check agent status
curl http://localhost:8000/agent/status
```

## Stop / Logs

```bash
docker compose -f docker/docker-compose.yml down          # stop
docker compose -f docker/docker-compose.yml logs -f backend  # logs
```

## Third-Party Dependencies

All dependencies are MIT/Apache/BSD licensed and compatible with this project's Apache 2.0 license.

| Library | License | Purpose |
|---------|---------|---------|
| FastAPI | MIT | REST API framework |
| uvicorn | BSD | ASGI server |
| pydantic | MIT | Data validation |
| ChromaDB | Apache 2.0 | Vector database for RAG |
| sentence-transformers | Apache 2.0 | Local embeddings (BAAI/bge-small-en-v1.5) |
| httpx | BSD | Async HTTP client |
| python-dotenv | BSD | Environment config |
| python-multipart | Apache 2.0 | File upload support |
| numpy / pandas | BSD | Numerical processing |
| scikit-learn | BSD | Alarm correlation |
| requests | Apache 2.0 | HTTP client |


## Expected Outcomes

After `./deploy.sh` completes, a judge should see:

**1. Health check**
```json
{"status":"healthy","timestamp":"...","version":"2.0.0"}
```

**2. Agent answers a NOC question in 2–6 steps**
```
Query: "What are the most critical active alerts?"
→ Calls get_active_alerts (1 tool call)
→ Answer: "There are 54 active alerts. The most severe are 22 P2 alerts.
  Most recent: ALM-050 (BGP session failure, Router-KNB-04, P2)..."
```

**3. FiGHT detection fires on threat evidence**
```
Input: "SS7 MAP SRI queries from external ISPC, SCCP flood on STP-Core-01"
→ FGT5019 detected: SS7 Location Tracking via MAP-SRI
→ Confidence: 55 (LOW tier), 3 matched indicators
→ Approve & Apply remediation button rendered
```

**4. Approve remediation logs action**
```json
{"status":"executed","technique_id":"FGT5019","target":"STP-Core-01",
 "action_taken":"Deploy GSMA FS.11/FS.19 SS7 firewall...","logged_to":"/data/fight_remediations.jsonl"}
```

**5. OPEA health endpoint**
```
GET http://localhost:8000/opea/health
→ Shows embedding/retriever/dataprep/chatqna reachability status
→ Default deploy: degraded (OPEA off). Run ./deploy.sh --opea for full stack.
```

## License

Apache 2.0 — see [LICENSE](LICENSE)

## Author

Submitted to the **OPEA × ITU AI for Good Hackathon 2025** by Jamo642.
