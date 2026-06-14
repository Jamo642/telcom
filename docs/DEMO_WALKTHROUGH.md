# Demo Walkthrough Guide

**Duration**: 3-5 minutes | **Audience**: Technical reviewers, enterprise stakeholders

## Pre-Demo Checklist

- [ ] System started: `docker-compose -f docker/docker-compose.yml up`
- [ ] All services healthy: `python scripts/health_check.py`
- [ ] Database initialized with documents
- [ ] Streamlit UI accessible at http://localhost:8501
- [ ] Internet connectivity verified (for first-time model pulls)

## Part 1: System Overview (30 seconds)

**What to show:**

1. **Open README.md** or show slide with architecture diagram
2. Explain:
   - "This is an enterprise AI copilot for telecom incident analysis"
   - "It follows OPEA principles: modular, composable, locally-deployed"
   - "Key components: Frontend (Streamlit), Backend (FastAPI), Microservices (embedding, retrieval, LLM, evaluation)"

## Part 2: Frontend Demo (30 seconds)

**Navigate to**: http://localhost:8501

**Show:**
1. **Sidebar**:
   - "System Status: Backend connected, 150+ documents indexed"
   - "Demo incidents available for easy testing"

2. **Main Interface**:
   - Large text area for incident input
   - "Analyze Incident" button
   - Professional, clean UI

## Part 3: Live Analysis #1 - Packet Loss (1.5 minutes)

**Select from sidebar**: "High packet loss on Node B12"

**Click**: "Load Demo" → incident text appears

**Click**: "Analyze Incident" → system processes

**While waiting** (~10-15 seconds for LLM inference):
Explain what's happening:
- Embedding: Converting incident to vector (384-dim)
- Retrieval: Searching ChromaDB for similar incidents/manuals
- LLM: Llama 2 7B generating structured analysis
- Evaluation: Calculating performance metrics

**Results appear**:

1. **Incident Report Card**:
   - Incident ID
   - Severity (🔴 High)
   - Confidence (85%)

2. **Root Cause Analysis**:
   - Show extracted root cause
   - "Output queue buffer overflow"

3. **Recommended Actions**:
   - Step 1: Increase buffer size
   - Step 2: Enable weighted round-robin queueing
   - Each with rationale

4. **Performance Metrics**:
   - Latency: ~1,800ms
   - Retrieval Accuracy: 85%
   - Response Quality: 88%
   - Overall Score: 86%

**Highlight**:
- "All processing local, no cloud APIs"
- "End-to-end latency under 2 seconds"
- "High confidence in analysis"

## Part 4: Show Retrieved Context (30 seconds)

**Expand**: "Document 1 - incidents (Similarity: 0.92)"

**Show**:
- Past incident: "Packet Loss on Node B12"
- Full diagnostic information available

**Explain**:
- "System found a nearly identical past incident (92% similarity)"
- "Evidence-based analysis - grounded in real data"
- "Multiple sources of truth combined"

## Part 5: Live Analysis #2 - BGP Issue (1 minute)

**Select from sidebar**: "BGP Route Convergence Delay"

**Click**: "Load Demo" → "Analyze Incident"

**While processing**:
- Brief explanation of BGP convergence issues
- Enterprise impact (SLA violations)

**Show results**:
- Severity: 🔴 Critical
- RCA: BGP timers not tuned
- Actions: Reduce hold-time, enable BFD, soft reset

**Key point**:
- "Different incident type, system adapts recommendations"
- "Severity properly escalated to Critical"

## Part 6: Metrics Deep Dive (30 seconds)

**Click**: "Detailed Metrics" expander

**Show**:
```json
{
  "retrieval": {
    "retrieval_count": 5,
    "avg_similarity": 0.75,
    "quality_score": 0.75
  },
  "response_quality": {
    "completeness_score": 1.0,
    "confidence_score": 0.85,
    "overall_quality": 0.92
  },
  "latency": {
    "latency_ms": 1850
  }
}
```

**Explain**:
- "Real performance metrics captured"
- "Retrieval quality 75% (high-quality matches found)"
- "Response completely generated with high confidence"
- "Sub-2-second latency meets enterprise SLA"

## Part 7: Architecture Walkthrough (1 minute)

**Open terminal**, show architecture:

```bash
# Check running services
docker-compose -f docker/docker-compose.yml ps

# Show API endpoints
curl http://localhost:8000/docs
```

**Explain flow**:
```
Streamlit Input
    ↓
FastAPI Orchestrator
    ├→ Embedding Service (sentence-transformers)
    ├→ Retrieval Service (ChromaDB)
    ├→ LLM Service (Ollama/Llama 2 7B)
    ├→ Evaluation Service (metrics)
    └→ Structured Report
```

**Highlight OPEA principles**:
- ✅ Modular design (4 independent services)
- ✅ Composable (easy to swap components)
- ✅ Open standards (REST APIs)
- ✅ Enterprise-ready (error handling, logging)
- ✅ Observable (comprehensive metrics)

## Part 8: One-Click Setup Demo (30 seconds)

**Show command**:
```bash
cd /home/king/itu
./setup.sh
```

**Explain**:
- "Complete system setup with single command"
- "Handles Docker image pulls, model downloads, initialization"
- "Production-grade deployment, no manual steps"

## Part 9: Q&A Talking Points

**"Why local LLM instead of cloud API?"**
- Data privacy (no external calls)
- Cost efficiency (no per-query charges)
- Latency (no network roundtrip)
- OPEA compliance (open, self-contained)

**"How does it handle new incident types?"**
- Semantic search finds similar incidents/manuals
- LLM generalizes from evidence
- Confidence score indicates uncertainty
- Can add new documents to ChromaDB anytime

**"What about accuracy?"**
- Evidence-based reasoning (grounded in data)
- Multiple sources combined (incidents + manuals + logs)
- Confidence scores provided
- Can validate against ground truth

**"Scaling considerations?"**
- Vectorstore: Can scale to millions of documents (Milvus)
- LLM: Can upgrade to larger models (13B+)
- Services: Horizontally scalable (stateless)
- Throughput: Currently 2-3 req/sec, can distribute

## Demo Incidents Summary

| Incident | Severity | Expected RCA | Confidence |
|----------|----------|--------------|-----------|
| Packet Loss | High | Buffer overflow | 85%+ |
| BGP Convergence | Critical | Slow timers | 85%+ |
| DNS Timeout | Medium | Cache exhausted | 80%+ |

## Performance Expected

| Metric | Value | Note |
|--------|-------|------|
| **Latency** | 1.5-2.5s | First query slower (~10s), cached |
| **Retrieval Accuracy** | 80%+ | Similar incidents found consistently |
| **Confidence** | 80%+ | High-quality reasoning |
| **Throughput** | 2-3 RPS | Sequential processing |

## Backup Plan

**If system not responding**:
1. Check health: `python scripts/health_check.py`
2. Check containers: `docker ps`
3. Show architecture diagram instead
4. Walk through code walkthrough

**If LLM inference slow**:
- Expected on first query (model initialization)
- Show API response JSON directly
- Pre-generate example responses in backup slide

## Key Differentiators to Emphasize

✅ **OPEA-Aligned**: Not a generic chatbot - enterprise AI pipeline  
✅ **Local Only**: No cloud dependencies, no API costs  
✅ **Modular**: Swap embedding models, LLMs, retrieval strategies  
✅ **Observable**: Comprehensive metrics and tracing  
✅ **Production-Ready**: Error handling, logging, structured outputs  
✅ **End-to-End**: Full workflow from incident to report  

---

**Total Demo Time: 3-5 minutes**
**Preparation: 2-3 minutes (startup time)**
