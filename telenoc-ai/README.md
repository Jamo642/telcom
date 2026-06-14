# 📡 TeleNOC AI — Intelligent Telecom Network Fault Diagnosis

**Built for OPEA x ITU AI for Good Hackathon**

TeleNOC AI is an enterprise-grade NOC (Network Operations Center) assistant that uses OPEA's RAG pipeline and LLM APIs to diagnose telecom network faults, classify alarms by severity, correlate related incidents, track MTTR, detect degradation trends, and auto-escalate based on SLA timers.

## Features

- **AI-Powered Diagnosis** — Uses NVIDIA API (Llama3-70B) with Groq/HuggingFace/Ollama fallback
- **Severity Classification** — P1 (Critical) through P4 (Warning) with confidence scoring
- **Alarm Correlation** — Groups related alarms into root cause clusters
- **MTTR Tracking** — Per-node and per-severity resolution time analytics
- **Degradation Trends** — Pre-outage detection using statistical anomaly analysis
- **SLA Escalation** — Auto-escalation with configurable timers (P1=15min to P4=8hrs)
- **False Positive Prevention** — Maintenance windows, transient filtering, P1 confirmation
- **Multi-Language** — English and Swahili support
- **No GPU Required** — All LLM inference via API, Ollama as local fallback

## Quick Start

```bash
# One-click deployment
./deploy.sh

# Dashboard: http://localhost:8080
# API:       http://localhost:8000
# API Docs:  http://localhost:8000/docs
```

## Architecture

```
User → Web UI (index.html) → FastAPI (main.py) → Agent (agent.py)
                                                      │
                    ┌─────────────────────────────────┤
                    │              │                  │
               severity.py   correlator.py        mttr.py
                    │              │                  │
               trends.py     escalation.py      database.py
                    │              │                  │
                    └──────────────┴──────────────────┘
                              │
                         OPEA Pipeline
                    (embedding → retriever → chatqna)
                              │
                         ChromaDB (Vector Store)
                              │
                    NVIDIA API / Groq / HF / Ollama
```

## Project Structure

```
telenoc-ai/
├── docker-compose.yml       # OPEA + ChromaDB + app services
├── Dockerfile               # Backend container build
├── nginx.conf               # UI proxy config
├── deploy.sh                # One-click setup script
├── .env.example             # API keys template
├── LICENSE                  # Apache 2.0
├── README.md                # This file
├── backend/
│   ├── main.py              # FastAPI app (14 endpoints)
│   ├── agent.py             # Diagnosis agent orchestrator
│   ├── correlator.py        # Alarm correlation engine
│   ├── severity.py          # P1-P4 classifier (NVIDIA API)
│   ├── mttr.py              # MTTR tracker
│   ├── trends.py            # Degradation trend detector
│   ├── escalation.py        # SLA-aware auto-escalation
│   ├── ingest.py            # Alarm log ingestion
│   └── database.py          # SQLite schema + queries
├── data/
│   └── sample_alarms.json   # 50 synthetic telecom alarms
├── scripts/
│   └── ingest_sample_data.sh
└── ui/
    └── index.html           # NOC Dashboard
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/diagnose` | Diagnose a single alarm |
| POST | `/diagnose/batch` | Batch diagnose multiple alarms |
| GET | `/mttr` | MTTR report |
| GET | `/trends` | Degradation trends |
| GET | `/escalations` | Escalation queue |
| POST | `/escalations/{id}/acknowledge` | Acknowledge escalation |
| POST | `/maintenance` | Register maintenance window |
| GET | `/maintenance` | Active maintenance windows |
| GET | `/incidents` | List incidents (filterable) |
| GET | `/incidents/{alarm_id}` | Get incident details |
| POST | `/incidents/{alarm_id}/resolve` | Resolve incident |
| POST | `/ingest` | Ingest alarm data |
| GET | `/review` | Low-confidence review queue |
| POST | `/correlate` | Correlate alarms |
| GET | `/dashboard` | All dashboard data in one call |
| GET | `/health` | Health check |

## Sample Diagnosis Output

```json
{
  "alarm_id": "ALM-001",
  "severity": "P1",
  "confidence": 0.91,
  "root_cause": "BGP peer session dropped on upstream link",
  "recommended_action": "Check interface GigE0/1 on Router R3",
  "relevant_runbook": "NOC-SOP-BGP-003",
  "escalate_to": "NOC Lead",
  "respond_within": "15 minutes",
  "mttr_started_at": "2026-06-13T08:32:00Z"
}
```

## False Positive Prevention

- **Maintenance Windows** — Alarms on nodes in planned maintenance are suppressed
- **Transient Filtering** — Alarms that self-clear in <60 seconds are ignored
- **Confidence Gates** — Low confidence (<0.75) flagged for human review, no auto-escalate
- **P1 Confirmation** — Requires 2 similar alarms within 5 minutes before P1 classification

## License

Apache 2.0 — See [LICENSE](LICENSE)

---

**Built for OPEA x ITU AI for Good Hackathon**