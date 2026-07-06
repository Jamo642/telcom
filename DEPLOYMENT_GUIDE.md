# Deployment Guide

## Goal

Provide a reliable one-click deployment for TeleNOC AI using real OPEA microservices on a single node.

## One-Click Command

```bash
bash deploy.sh
```

This starts:
- redis
- embedding (opea/embedding-tei)
- retriever (opea/retriever-redis)
- dataprep (opea/dataprep)
- chatqna (opea/chatqna)
- ollama
- backend
- ui

## Challenge Constraint: 10-Minute Initial Run

Challenge rule requires installation and initial run to complete within 10 minutes on a clean environment.

Deployment behavior:
- warm run (images cached): normally fast and suitable for timed evaluation
- cold run (fresh machine): may exceed 10 minutes due to large image pulls and network variability

## Recommended Timed-Evaluation Procedure

Use this two-step procedure for judges:

1. Pre-pull once (before timed run)

```bash
docker pull redis:7-alpine
docker pull nginx:alpine
docker pull ollama/ollama:latest
docker pull opea/embedding-tei:latest
docker pull opea/retriever-redis:latest
docker pull opea/dataprep:latest
docker pull opea/chatqna:latest
```

2. Start timed run

```bash
bash deploy.sh
```

## Health Verification

After deployment:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/opea/health
```

Expected:
- /health returns backend healthy status
- /opea/health returns per-service reachability for embedding, retriever, dataprep, chatqna

## Fallback Behavior

TeleNOC fallback logic:
- preferred RAG path: OPEA chatqna
- if OPEA path unavailable: fallback to direct LLM provider chain
- provider chain: Groq -> NVIDIA -> HuggingFace -> Ollama

Note: API keys must remain in .env only.

## Runtime Endpoints

- Dashboard: http://localhost:8080
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- OPEA Health: http://localhost:8000/opea/health

## Resource Profile

Compose memory limits are configured to stay below challenge maximums and support a single-node run.

## Troubleshooting

### Pull errors (unexpected EOF, Docker 500)

These are usually transient network/daemon issues during large pulls.

Actions:
1. retry docker pull for failed image
2. restart Docker daemon if repeated 500 errors occur
3. rerun bash deploy.sh

### Service not healthy

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs --tail 100
```

### Clean restart

```bash
docker compose -f docker/docker-compose.yml down -v
bash deploy.sh
```
