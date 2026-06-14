# 📡 Telecom AI Incident Resolution Copilot

**Enterprise AI system for network incident diagnosis and resolution using OPEA principles**

## Overview

This is a production-style AI-Native Telecom Operations Copilot demonstrating:

- **Modular OPEA Architecture**: Independent microservices (embedding, retrieval, reasoning, evaluation)
- **RAG Pipeline**: Semantic retrieval from vector database + LLM-based reasoning
- **Local Inference**: No cloud APIs required (Ollama + Llama 2 7B)
- **Performance Metrics**: Full observability and evaluation
- **Enterprise Workflow**: Incident → Analysis → Root Cause → Actions → Report

## 🏗️ System Architecture

```
User Input (Streamlit)
    ↓
FastAPI Orchestrator
    ├→ Embedding Service (sentence-transformers)
    ├→ Retrieval Service (ChromaDB semantic search)
    ├→ LLM Service (Ollama → Llama 2 7B)
    ├→ Evaluation Service (metrics collection)
    └→ Structured Report Generation
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Frontend** | Streamlit | Web UI for incident input and report display |
| **Orchestrator** | FastAPI | Request routing and workflow orchestration |
| **Embedding** | sentence-transformers (bge-small-en) | Convert text to vectors |
| **Retrieval** | ChromaDB | Semantic search on vector DB |
| **LLM** | Ollama + Llama 2 7B | Local inference for reasoning |
| **Evaluation** | Custom service | Performance metrics calculation |

## 📊 Dataset

Includes **30 synthetic telecom incidents** covering:

- Packet loss and network congestion
- BGP routing issues and convergence delays
- DNS resolution failures
- High CPU/memory utilization
- Disk space management
- Interface hardware problems
- QoS policy violations
- And more...

Plus:
- **5 network log samples** (realistic syslog output)
- **5 troubleshooting manuals** (diagnostic guides)

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- 4-core CPU, 8GB RAM minimum
- ~15GB disk space (for Ollama model)

### 1. Setup (One Command)

```bash
cd /home/king/itu
chmod +x setup.sh
./setup.sh
```

This will:
- Pull Docker images
- Download Llama 2 7B model (~4GB)
- Initialize vector database
- Start all services

### 2. Access the System

Once complete, navigate to:

- **Frontend**: http://localhost:8501
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Ollama**: http://localhost:11434

### 3. Demo

1. Open http://localhost:8501
2. Select a demo incident from sidebar
3. Click "Load Demo" → "Analyze Incident"
4. View RCA, actions, and metrics

## 📖 Usage

### Via Web UI (Recommended)

1. Enter incident description in the text area
2. Click "Analyze Incident"
3. View structured report with:
   - Root cause analysis
   - Recommended actions
   - Evidence from retrieved documents
   - Severity classification
   - Performance metrics

### Via API

```bash
curl -X POST http://localhost:8000/analyze-incident \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "High packet loss on Node B12",
    "top_k_retrieval": 5,
    "temperature": 0.7
  }'
```

### Initialization

Ensure vector DB is populated:

```bash
curl -X POST http://localhost:8000/initialize \
  -H "Content-Type: application/json" \
  -d '{
    "incidents_csv_path": "/data/incidents/incidents.csv",
    "logs_dir_path": "/data/logs",
    "manuals_dir_path": "/data/manuals"
  }'
```

## 🔧 Project Structure

```
/home/king/itu/
├── backend/
│   └── app.py                 # FastAPI orchestrator
├── services/
│   ├── embedding_service.py   # Sentence-transformers wrapper
│   ├── retrieval_service.py   # ChromaDB semantic search
│   ├── llm_service.py         # Ollama integration
│   ├── evaluation_service.py  # Metrics calculation
│   └── data_ingestion.py      # Load datasets
├── frontend/
│   └── app.py                 # Streamlit UI
├── data/
│   ├── incidents/incidents.csv    # 30 synthetic incidents
│   ├── logs/                      # Network log samples
│   └── manuals/                   # Troubleshooting guides
├── docker/
│   ├── docker-compose.yml     # Multi-service orchestration
│   ├── Dockerfile.backend     # Backend container
│   └── Dockerfile.frontend    # Frontend container
├── tests/
│   └── test_integration.py    # Integration tests
├── scripts/
│   └── initialize_data.py     # Data initialization
├── requirements.txt           # Python dependencies
├── setup.sh                   # One-click setup script
└── README.md                  # This file
```

## 📈 Workflow Example

### Input
```
"High packet loss on Node B12. Users report degraded service. RTT increased from 15ms to 45ms."
```

### Processing
1. **Embedding**: Convert query to vector (384-dim embedding)
2. **Retrieval**: Search ChromaDB for top-5 similar documents
   - Past incident: "Packet Loss on Node B12"
   - Manual: "Packet Loss Diagnosis and Resolution"
   - Log: "node_b12_packet_loss.log"
3. **Reasoning**: LLM analyzes incident + context
4. **Evaluation**: Calculate metrics (latency, accuracy, confidence)

### Output
```json
{
  "root_cause": "Output queue buffer overflow due to congestion",
  "evidence": ["Queue depth at 95%", "CRC errors detected"],
  "recommended_actions": [
    {
      "step": 1,
      "action": "Increase buffer size to 65536 bytes",
      "rationale": "Current buffer too small for traffic volume"
    },
    {
      "step": 2,
      "action": "Enable weighted round-robin queueing",
      "rationale": "Better traffic distribution"
    }
  ],
  "severity": "High",
  "confidence_score": 0.89
}
```

## 📊 Metrics

The system tracks:

| Metric | Target | Purpose |
|--------|--------|---------|
| **Latency** | <2 seconds | End-to-end response time |
| **Retrieval Accuracy** | >80% | Relevance of retrieved documents |
| **Response Quality** | >0.80 | Completeness and confidence of analysis |
| **Confidence Score** | >0.80 | LLM's self-rated confidence |
| **Throughput** | 2-3 RPS | Requests per second capacity |

## 🧪 Testing

### Run Integration Tests

```bash
cd /home/king/itu
pip install pytest
pytest tests/test_integration.py -v
```

### Manual Testing

1. Backend health:
   ```bash
   curl http://localhost:8000/health
   ```

2. System stats:
   ```bash
   curl http://localhost:8000/stats
   ```

3. Aggregated metrics:
   ```bash
   curl http://localhost:8000/metrics
   ```

## 🛑 Stopping Services

```bash
docker-compose -f docker/docker-compose.yml down
```

## 🔍 Troubleshooting

### Backend not responding
- Check Docker: `docker ps`
- Check logs: `docker-compose -f docker/docker-compose.yml logs backend`
- Verify Ollama: `docker-compose -f docker/docker-compose.yml logs ollama`

### Vector DB not initialized
- Manually trigger: `curl -X POST http://localhost:8000/initialize`
- Check logs: `docker-compose -f docker/docker-compose.yml logs backend`

### Slow inference
- Ollama may still be loading model
- First query is always slower (~5-10 seconds)
- Subsequent queries faster (~2-3 seconds)

### Out of memory
- Reduce Llama 2 to Ollama's smallest quantization
- Or use Phi-3 instead (lighter weight)

## 📚 Documentation

- **Architecture**: See [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **API Reference**: http://localhost:8000/docs
- **Incident Dataset**: [incidents.csv](data/incidents/incidents.csv)
- **Manuals**: [data/manuals/](data/manuals/)

## 🎯 Key Features

✅ **Enterprise-Ready Architecture**
- Modular OPEA design
- Production-style error handling
- Comprehensive logging

✅ **OPEA Alignment**
- Service-oriented architecture
- Composable components
- Standardized interfaces

✅ **Performance Optimization**
- Semantic search (dense embeddings)
- Local inference (no API latency)
- Efficient vector indexing

✅ **Observability**
- Detailed metrics reporting
- Request tracing
- System statistics

## 🚀 Demo Flow (3 Minutes)

1. **Setup** (30s): Start system with `./setup.sh`
2. **UI Load** (10s): Navigate to http://localhost:8501
3. **Demo Query** (60s): Select demo incident → Analyze
   - Wait for LLM reasoning
   - View RCA and actions
4. **Metrics Review** (30s): Check performance metrics (latency, accuracy, confidence)
5. **Architecture Walkthrough** (60s): Explain modular design and workflow

## 💡 Customization

### Add Custom Incidents

1. Edit `data/incidents/incidents.csv`
2. Add CSV rows with incident data
3. Restart backend to re-index:
   ```bash
   docker-compose -f docker/docker-compose.yml restart backend
   ```

### Change LLM Model

Edit `services/llm_service.py` and change model name:
```python
def __init__(self, ollama_host: str = "http://ollama:11434", model_name: str = "mistral"):
```

Supported models (via Ollama):
- `llama2` (7B, default)
- `mistral` (7B, faster reasoning)
- `phi` (3B, lightweight)
- `neural-chat` (7B, optimized for chat)

### Adjust Retrieval Parameters

Edit `.env`:
```
TOP_K_RETRIEVAL=5              # Number of documents to retrieve
SIMILARITY_THRESHOLD=0.3       # Minimum similarity score
```

## 📄 License

This project is part of ITU FG-AINN Challenge on Generative AI Applications for Enterprise Scenarios Using OPEA.

## 👥 Support

For issues or questions:
1. Check troubleshooting section above
2. Review logs: `docker-compose logs`
3. Verify services running: `docker ps`

---

**Built with ❤️ for Enterprise Telecom Operations**
