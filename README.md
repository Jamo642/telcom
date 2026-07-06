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

Open **http://localhost:8080** when the script completes (~5–7 min cold, ~30 s warm).

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

LLM: OpenRouter free tier (nvidia/nemotron-3-ultra-550b-a55b:free)
     Fallback chain: llama-3.3-70b → nemotron-super → qwen3-coder → llama-3.2-3b
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
| `OPENROUTER_MODEL` | Default: `nvidia/nemotron-3-ultra-550b-a55b:free` |

## OPEA Integration

OPEA services (`embedding`, `retriever`, `dataprep`, `chatqna`) are included in `docker/docker-compose.yml` under `profile: [opea]`.  
They are **off by default** to stay within the 10-minute setup constraint.  
The system uses its own embedding stack (sentence-transformers + ChromaDB) which is baked into the Docker image at build time.

To enable full OPEA stack:
```bash
COMPOSE_PROFILES=opea docker compose -f docker/docker-compose.yml up -d
```

## Stop / Logs

```bash
docker compose -f docker/docker-compose.yml down          # stop
docker compose -f docker/docker-compose.yml logs -f backend  # logs
```

## License

Apache 2.0 — see [LICENSE](LICENSE)
