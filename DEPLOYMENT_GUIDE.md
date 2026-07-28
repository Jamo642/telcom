# Deployment Guide — TeleNOC AI

## One-Command Deploy

```bash
git clone https://github.com/Jamo642/telcom.git
cd telcom
cp .env.example .env
# Edit .env — set at least one API key (OPENROUTER_API_KEY, NVIDIA_API_KEY, or GROQ_API_KEY)
./deploy.sh
```

`deploy.sh` handles everything: Docker checks, `.env` auto-creation, image build, service startup (Redis → Backend → UI), sample alarm ingestion, and MITRE FiGHT ChromaDB embedding.

## Default Stack (no OPEA images pulled)

```
redis:7-alpine          256 MB RAM
backend (FastAPI)       1 GB RAM
ui (nginx:alpine)       128 MB RAM
```

OPEA microservices (`embedding-tei`, `retriever-redis`, `dataprep`, `chatqna`) are **off by default** under `profile: opea`. The system uses its own local ChromaDB + sentence-transformers stack (`BAAI/bge-small-en-v1.5`, baked into the Docker image) — zero additional downloads at runtime.

## Full OPEA Stack (optional)

```bash
./deploy.sh --opea
# or: COMPOSE_PROFILES=opea docker compose -f docker/docker-compose.yml up -d
```

⚠ First run pulls ~8 GB of OPEA images — allow 10–20 min on a cold machine.

## Timing

| Scenario | Time |
|---|---|
| Cold (no cached images) | ~3–4 min |
| Warm (images cached) | ~30 s |
| With OPEA, cold | ~15–20 min |
| With OPEA, warm | ~2–3 min |

## Timed Evaluation Pre-Pull (optional)

To ensure a clean timed run stays under 10 min, pre-pull the base images once:

```bash
docker pull redis:7-alpine
docker pull nginx:alpine
docker pull python:3.10-slim
```

Do **not** pre-pull OPEA images unless you plan to run `--opea`.

## Health Verification

```bash
# Backend health
curl http://localhost:8000/health
# → {"status":"healthy","version":"2.0.0"}

# OPEA service reachability (shows degraded when --opea not active — expected)
curl http://localhost:8000/opea/health
```

## Runtime Endpoints

| Endpoint | URL |
|---|---|
| Web UI | http://localhost:8080 |
| REST API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| OPEA Health | http://localhost:8000/opea/health |

## Fallback Behaviour

| Tier | Provider | Condition |
|---|---|---|
| 1 | NVIDIA NIM (`NVIDIA_API_KEY`) | Preferred when key present |
| 2 | OpenRouter (`OPENROUTER_API_KEY`) | Used when NVIDIA key absent |
| 3 | Groq (`GROQ_API_KEY`) | Fallback |
| 4 | Rule-based diagnosis | No API key at all |

RAG path: OPEA `chatqna` (when `--opea`) → local ChromaDB + sentence-transformers.

## Troubleshooting

### Backend not healthy after 2 min
```bash
docker compose -f docker/docker-compose.yml logs backend --tail 50
```

### Clean restart
```bash
docker compose -f docker/docker-compose.yml down -v
./deploy.sh
```

### Pull errors (transient network issues)
Retry the failing `docker pull` individually, restart the Docker daemon if needed, then rerun `./deploy.sh`.

## Stop / Logs

```bash
# Stop all services
docker compose -f docker/docker-compose.yml down

# Stream backend logs
docker compose -f docker/docker-compose.yml logs -f backend
```
