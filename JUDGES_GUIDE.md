# Judges Guide — TeleNOC AI

## One-Click Deployment

```bash
git clone https://github.com/Jamo642/telcom.git
cd telcom

# Add your free OpenRouter key (https://openrouter.ai — no credit card)
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY=sk-or-v1-...

./deploy.sh
```

That is the entire procedure. The script handles everything:
- Docker prerequisite check
- `.env` auto-creation if missing
- Image build (~2–3 min cold, <1 min warm)
- Service startup (Redis → Backend → UI)
- Sample alarm ingestion (50 alarms, runs in background)
- MITRE FiGHT embedding into ChromaDB (auto-skipped if already done)

## Hardware Requirements

| Resource | Required | Configured |
|---|---|---|
| CPU | 4 cores | Uses all available |
| RAM | ≤ 64 GB | Backend 1 GB · Redis 256 MB · UI 128 MB |
| GPU | Optional | Not required — LLM is via OpenRouter API |
| Network | Yes | OpenRouter API calls only (no heavy model downloads) |

## Timing on Clean Environment

| Phase | Time |
|---|---|
| `docker pull python:3.10-slim` + `redis:7-alpine` + `nginx:alpine` | ~1–2 min |
| `pip install` (slim backend deps only — no streamlit/pandas/sklearn) | ~1 min |
| Embedding model download (`BAAI/bge-small-en-v1.5`, 130 MB, baked into image) | ~45 s |
| Backend startup + health check | ~20 s |
| **Total cold** | **~3–4 min** |
| **Total warm (cached images)** | **~30 s** |

No OPEA images are pulled by default — they are in `profile: [opea]` which is off unless explicitly activated.

## Verification Checklist

After `./deploy.sh` completes:

```bash
# 1. Backend health
curl http://localhost:8000/health
# → {"status":"healthy","version":"2.0.0"}

# 2. Active alerts
curl http://localhost:8000/incidents | python3 -m json.tool | head -10

# 3. Agent chat (tool-using)
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the most critical active alerts?"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:300])"

# 4. FiGHT detection
curl -s -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Run detect_fight_techniques on: SS7 MAP SRI queries flooding from external ISPC, SCCP message flood on STP-Core-01"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:400])"

# 5. UI
open http://localhost:8080   # or visit in browser
```

## Tabs in the UI

| Tab | Function |
|---|---|
| 🔍 Diagnose | Submit any alarm → get AI root-cause + "How to Fix" with agent fix steps |
| 🤖 AI Agent | Multi-step tool-using chat — queries live DB, logs, ChromaDB, FiGHT engine |
| 🛡️ FiGHT | Paste alarm text → MITRE FiGHT 5G threat detection with Approve/Dismiss remediation |
| 🔔 Escalations | Live escalation queue |

## AI Provider

Default: **OpenRouter free tier** (`nvidia/nemotron-3-super-120b-a12b:free`, ~1.5 s response)
Fallback chain: `nemotron-ultra:free` → `gemma-4-31b:free` → `nemotron-nano:free`

No Ollama, no GPU, no HuggingFace download needed. A free OpenRouter key is sufficient.

## Stop / Logs

```bash
# Stop
docker compose -f docker/docker-compose.yml down

# Logs
docker compose -f docker/docker-compose.yml logs -f backend
```

## Compliance Artifacts

| Artifact | File |
|---|---|
| One-click deploy | [`deploy.sh`](deploy.sh) |
| Docker Compose | [`docker/docker-compose.yml`](docker/docker-compose.yml) |
| License (Apache 2.0) | [`LICENSE`](LICENSE) |
| OPEA alignment | [`OPEA_ALIGNMENT.md`](OPEA_ALIGNMENT.md) |
