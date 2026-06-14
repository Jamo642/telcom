# Architecture Documentation

## System Overview

The Telecom AI Incident Copilot is an enterprise-grade system following OPEA (Open Platform for Enterprise AI) principles. It demonstrates a production-style RAG (Retrieval Augmented Generation) pipeline for telecom operations.

## 🏛️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND LAYER                           │
│  Streamlit UI (localhost:8501)                              │
│  - Incident input form                                       │
│  - Report display                                            │
│  - Metrics dashboard                                         │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/REST
┌────────────────────▼────────────────────────────────────────┐
│           ORCHESTRATION LAYER (FastAPI)                     │
│  - Request routing                                           │
│  - Workflow coordination                                     │
│  - Error handling                                            │
│  - Service composition                                       │
└─┬──────────┬──────────┬──────────┬──────────────────────────┘
  │          │          │          │
  │          │          │          │
┌─▼──┐   ┌──▼────┐  ┌──▼──┐   ┌──▼────┐
│EMB │   │RETRI  │  │LLM  │   │EVAL   │
│    │   │EVAL   │  │     │   │       │
└────┘   └───────┘  └─────┘   └───────┘
  │          │          │          │
  └──────────┴──────────┴──────────┘
      DATA LAYER (ChromaDB)
    - 30 incidents
    - 5 network logs
    - 5 manuals
    - ~150 indexed documents
```

## 🔄 Request Workflow

### Phase 1: Embedding
```
User Input
    ↓
Tokenization (sentence-transformers)
    ↓
Vector Generation (384-dimensional)
    ↓
Query Embedding
```

### Phase 2: Retrieval
```
Query Embedding
    ↓
ChromaDB Semantic Search
    ↓
ANN (Approximate Nearest Neighbor) matching
    ↓
Cosine Similarity Ranking
    ↓
Top-K Documents (k=5 default)
```

### Phase 3: Context Assembly
```
Top-K Documents
    ↓
Metadata Extraction
    ↓
Relevance Filtering
    ↓
Context Formatting
```

### Phase 4: LLM Reasoning
```
Incident + Context
    ↓
Structured Prompt Engineering
    ↓
Ollama API Call
    ↓
Llama 2 7B Inference
    ↓
Structured JSON Generation
```

### Phase 5: Evaluation
```
Response & Metrics Collection
    ├─ Latency Calculation
    ├─ Retrieval Quality Score
    ├─ Response Completeness
    ├─ Confidence Extraction
    └─ Aggregation
```

## 🔧 Microservices Architecture

### 1. Embedding Service (`services/embedding_service.py`)

**Purpose**: Convert text to semantic vectors

**Model**: `BAAI/bge-small-en-v1.5`
- 384-dimensional embeddings
- ~110M parameters
- 100-200ms per query

**Interfaces**:
```python
embed_text(text: str) -> np.ndarray  # Single text
embed_batch(texts: List[str]) -> List[np.ndarray]  # Multiple
similarity(text1: str, text2: str) -> float  # Cosine similarity
```

**Design Pattern**: Singleton
- Lazy initialization
- Model loaded once, reused across requests

### 2. Retrieval Service (`services/retrieval_service.py`)

**Purpose**: Semantic search and ranking

**Database**: ChromaDB (local, file-based)
- Persistent storage at `/data/chroma_db`
- Cosine similarity metric
- ~150 documents indexed

**Interfaces**:
```python
add_documents(docs: List[str], metadatas: List[Dict], ids: List[str])
search(query: str, top_k: int, threshold: float) -> List[Dict]
get_collection_stats() -> Dict
```

**Design Pattern**: Singleton with persistent storage
- Connects to local ChromaDB instance
- Supports incremental indexing

### 3. LLM Service (`services/llm_service.py`)

**Purpose**: Local inference for reasoning

**Engine**: Ollama
- Model: Llama 2 7B (~4GB VRAM)
- Quantization: Q4 (4-bit)
- API: REST endpoint at `http://ollama:11434`

**Interfaces**:
```python
generate_response(prompt: str, temperature: float, ...) -> Dict
structured_reasoning(incident: str, context: str) -> Dict
is_available() -> bool
```

**Prompt Engineering**:
- Forces JSON-structured output
- Provides incident + context
- Specifies required fields (root_cause, severity, actions, etc.)

### 4. Evaluation Service (`services/evaluation_service.py`)

**Purpose**: Metrics collection and aggregation

**Metrics Tracked**:
1. **Latency**: End-to-end response time (ms)
2. **Retrieval Quality**: Avg similarity of top-k results
3. **Response Quality**: Completeness + confidence score
4. **Retrieval Accuracy**: Heuristic-based (top similarity > 0.7 → 85% accuracy)

**Interfaces**:
```python
evaluate_retrieval(docs: list) -> Dict
evaluate_latency(start: float, end: float) -> Dict
evaluate_response_quality(response: Dict) -> Dict
create_metrics_report(...) -> Dict
get_aggregated_metrics() -> Dict
save_metrics(filepath: str)
```

**Design Pattern**: Singleton with history tracking
- Maintains metrics_history list
- Aggregates across requests

### 5. Data Ingestion Service (`services/data_ingestion.py`)

**Purpose**: Load and prepare datasets

**Data Sources**:
- `incidents.csv`: 30 telecom incidents
- `logs/`: 5 network log files
- `manuals/`: 5 troubleshooting guides

**Processing**:
```
Raw Data
  ├─ Incidents: Full incident record as single document
  ├─ Logs: Each log file as document
  └─ Manuals: Split by sections (---), each section indexed
       ↓
Metadata Enrichment
  (source, severity, timestamp, etc.)
       ↓
Embedding & Indexing
  (via embedding service)
       ↓
ChromaDB Storage
  (~150 documents total)
```

## 🎯 Component Interactions

### Normal Flow (Happy Path)

```
Streamlit User Input
       ↓
FastAPI /analyze-incident endpoint
       ├─ Call: embedding_service.embed_text(incident)
       │         → Returns: query embedding
       │
       ├─ Call: retrieval_service.search(query_embedding, top_k=5)
       │         → Returns: List[Document with metadata and similarity]
       │
       ├─ Format: Context assembly
       │         → "RETRIEVED CONTEXT:\n---Document 1---\n..."
       │
       ├─ Call: llm_service.structured_reasoning(incident, context)
       │         → Returns: Structured JSON (root_cause, actions, etc.)
       │
       ├─ Call: evaluation_service.evaluate_*()
       │         → Returns: Metrics (latency, accuracy, quality)
       │
       └─ Response: IncidentAnalysisResponse (incident_id, analysis, metrics)
             ↓
Streamlit Display Report
         ├─ Root Cause
         ├─ Actions
         ├─ Severity
         ├─ Retrieved Context
         └─ Metrics
```

### Error Handling

```
Error at any stage
       ↓
Log error with context
       ↓
Return partial response with error flag
       ↓
Frontend displays error gracefully
       ↓
User can retry or modify input
```

## 📦 Data Structures

### IncidentAnalysisRequest
```python
{
    "incident_description": str,
    "top_k_retrieval": int = 5,
    "temperature": float = 0.7
}
```

### IncidentAnalysisResponse
```python
{
    "incident_id": str,
    "incident_description": str,
    "retrieved_context": [
        {
            "document": str,
            "source": str,  # "incidents", "logs", or "manuals"
            "similarity": float
        }
    ],
    "analysis": {
        "root_cause": str,
        "evidence": List[str],
        "recommended_actions": [
            {
                "step": int,
                "action": str,
                "rationale": str
            }
        ],
        "severity": "Critical|High|Medium|Low",
        "similar_incidents": List[str],
        "confidence_score": float
    },
    "metrics": {
        "timestamp": str,
        "latency": {"latency_ms": float, "latency_sec": float},
        "retrieval": {
            "retrieval_count": int,
            "avg_similarity": float,
            "quality_score": float
        },
        "response_quality": {
            "completeness_score": float,
            "confidence_score": float,
            "overall_quality": float
        },
        "retrieval_accuracy": float,
        "overall_score": float
    },
    "timestamp": str
}
```

## 🚀 Performance Characteristics

### Latency Breakdown (Typical)

| Component | Time (ms) | Notes |
|-----------|-----------|-------|
| Embedding | 100-150 | sentence-transformers inference |
| Retrieval | 50-100 | ChromaDB ANN search + sorting |
| LLM Inference | 1000-3000 | Llama 2 7B generation (first: slower) |
| Evaluation | 50-100 | Metrics calculation |
| Network/Overhead | 100-200 | Inter-service calls, serialization |
| **Total** | **1300-3550ms** | Most time spent in LLM |

### Scaling Characteristics

- **Embedding**: O(1) per query (model loaded once)
- **Retrieval**: O(log n) with HNSW index (n = document count)
- **LLM**: O(1) per query (single inference)
- **Overall**: Near-linear with document corpus size

### Resource Usage

| Component | Typical | Peak |
|-----------|---------|------|
| CPU | 1-2 cores | 3-4 cores during LLM |
| Memory (Backend) | 500MB | 1GB with models |
| Memory (Ollama) | 4GB (Llama 2 7B) | 4GB stable |
| Disk (ChromaDB) | 10-20MB | Grows with corpus |

## 🔐 Design Decisions & Rationales

| Decision | Rationale |
|----------|-----------|
| **Singleton Services** | Avoid recreating models/connections; efficient resource usage |
| **REST APIs** | Language-agnostic; easy to scale; standard enterprise pattern |
| **Structured Prompts** | Consistent, parseable outputs; easier debugging; reliable automation |
| **Local Inference** | No API latency; cost-effective; full data privacy; OPEA compliance |
| **ChromaDB** | No external service; automatic HNSW indexing; Python native; simple setup |
| **Embedding-only Retrieval** | Fast MVP; can add hybrid (BM25) later if needed |
| **JSON Metrics** | Easy aggregation; time-series friendly; integrates with monitoring |

## 🔄 Extensibility Points

### Easy to Add
- New incident sources (Kafka, SNMP traps, etc.)
- Additional embedding models (swap in `embedding_service.py`)
- Different LLM models (change in `.env` or `llm_service.py`)
- Custom evaluation metrics (extend `evaluation_service.py`)
- Additional retrieval strategies (e.g., hybrid BM25)

### Would Require Refactoring
- Multi-GPU inference (needs Ollama configuration)
- Distributed vector DB (migrate from ChromaDB to Milvus/Weaviate)
- Real-time streaming (add async/streaming to FastAPI)
- Multi-tenant system (add auth, isolation layers)

## 📊 Monitoring & Observability

### Available Endpoints

- `GET /health` — System health check
- `GET /stats` — Collection and service status
- `GET /metrics` — Aggregated performance metrics
- `POST /initialize` — Trigger database initialization
- `POST /analyze-incident` — Main analysis endpoint

### Metrics Storage

- In-memory history (volatile)
- Can export to JSON: `evaluation_service.save_metrics("/results/metrics.json")`
- Can integrate with Prometheus/Grafana

## 🎓 Educational Value (OPEA Alignment)

This system demonstrates:

1. **Modularity**: Each service independent, testable, replaceable
2. **Composition**: Clean APIs enable orchestration
3. **Open Standards**: REST, JSON, standard ML frameworks
4. **Enterprise Patterns**: Error handling, logging, metrics
5. **Scalability**: Stateless services, external storage
6. **Observability**: Comprehensive metrics, structured logging

Perfect reference architecture for OPEA-based enterprise AI applications.

---

For API documentation, see `/docs` endpoint.
For code examples, see test files in `tests/`.
