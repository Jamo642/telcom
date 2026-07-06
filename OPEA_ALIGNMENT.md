# OPEA Alignment for TeleNOC AI

TeleNOC AI is built on OPEA's composable microservice architecture.

It uses the OPEA GenAIComps stack as the retrieval and orchestration layer while keeping the existing FastAPI business logic for telecom operations.

## OPEA Microservices in Use

- `opea/embedding-tei` for vectorizing alarm logs, manuals, and runbooks
- `opea/retriever-redis` for semantic search over the knowledge base
- `opea/dataprep` for document and alarm ingestion
- `opea/chatqna` for RAG pipeline orchestration

## What TeleNOC Keeps Locally

- FastAPI backend for NOC workflows and APIs
- Severity classification
- Alarm correlation
- MTTR tracking
- Degradation trend analysis
- Auto-escalation logic
- MITRE FiGHT security detection
- Ollama fallback for local generation when OPEA or cloud providers are unavailable

## Integration Summary

- The backend sends documents to OPEA dataprep using multipart uploads.
- The retrieval layer calls OPEA retriever-redis over REST.
- RAG queries prefer OPEA chatqna and fall back to direct Groq, NVIDIA, HuggingFace, or Ollama generation if needed.
- Service health is exposed through `/opea/health`.
- All keys and endpoints are configured through environment variables.

## Hackathon Fit

This implementation is designed for the OPEA x ITU AI for Good Hackathon and supports single-node deployment for SME ISP and telco NOC workflows in East Africa.

It keeps the telecom domain logic intact while replacing the embedding and retrieval layer with real OPEA components.

## Status

TeleNOC AI is aligned with OPEA's composable architecture and uses OPEA microservices as the primary RAG substrate.
