"""
FastAPI Backend for TeleNOC AI

Enterprise-grade NOC assistant with:
- Alarm diagnosis via agent pipeline
- P1/P2/P3/P4 severity classification
- Alarm correlation into root cause clusters
- MTTR tracking and trend detection
- SLA-aware auto-escalation
- Swahili language support
- Low-confidence flagging for human review
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib import error, request

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from backend.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="TeleNOC AI - Telecom NOC Assistant",
    description="AI-powered telecom network fault diagnosis for NOC operations",
    version="2.0.0",
)

# Add CORS middleware — allow UI on :8080 to call API on :8000
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ──────────────────────────────────────────────────────────

class AlarmRequest(BaseModel):
    """Single alarm diagnosis request"""
    alarm_id: str
    alarm_name: str = ""
    node_name: str = ""
    alarm_type: str = ""
    timestamp: str = ""
    alarm_text: str

class BatchAlarmRequest(BaseModel):
    """Batch alarm diagnosis request"""
    alarms: List[AlarmRequest]
    language: str = "en"

class MaintenanceRequest(BaseModel):
    """Register a maintenance window"""
    node_name: str
    start_time: str
    end_time: str
    reason: str = ""
    created_by: str = "system"

class ResolveRequest(BaseModel):
    """Resolve an incident"""
    alarm_id: str
    resolution_notes: str = ""

class AgentChatRequest(BaseModel):
    """Agent chat request — drives the tool-using agent loop"""
    query: str
    session_id: Optional[str] = None


# ─── Startup Event ────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    logger.info("TeleNOC AI backend started")


# ─── Health & Info Endpoints ─────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "TeleNOC AI",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "2.0.0",
    }


@app.get("/opea/health")
async def opea_health_check():
    """Check reachability of the OPEA microservices used by TeleNOC."""
    services = {
        "embedding": _probe_service(os.environ.get("EMBEDDING_SERVICE_HOST", "embedding"), os.environ.get("EMBEDDING_SERVICE_PORT", "6000")),
        "retriever": _probe_service(os.environ.get("RETRIEVER_SERVICE_HOST", "retriever"), os.environ.get("RETRIEVER_SERVICE_PORT", "7000")),
        "dataprep": _probe_service(os.environ.get("DATAPREP_SERVICE_HOST", "dataprep"), os.environ.get("DATAPREP_SERVICE_PORT", "6007")),
        "chatqna": _probe_service(os.environ.get("CHATQNA_SERVICE_HOST", "chatqna"), os.environ.get("CHATQNA_SERVICE_PORT", "8888")),
    }

    overall_status = "healthy" if all(entry["healthy"] for entry in services.values()) else "degraded"
    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": services,
    }


def _probe_service(host: str, port: str) -> Dict[str, Any]:
    """Probe an OPEA service health endpoint."""
    base_url = f"http://{host}:{port}"
    for path in ("/health", "/v1/health"):
        try:
            http_request = request.Request(f"{base_url}{path}", method="GET")
            with request.urlopen(http_request, timeout=5) as response:
                if response.status == 200:
                    return {"healthy": True, "url": f"{base_url}{path}"}
        except Exception:
            continue
    return {"healthy": False, "url": base_url}


# ─── Diagnosis Endpoints ──────────────────────────────────────────────────────

@app.post("/diagnose")
async def diagnose_alarm(request: AlarmRequest, http_request: Request):
    """
    Diagnose a single alarm.
    
    Returns structured JSON with severity, confidence, root cause,
    recommended action, escalation info, and MTTR timer.
    
    Supports language selection via Accept-Language header (en/sw).
    """
    language = _get_language(http_request)
    
    # Check for maintenance window and transient filters first
    logger.info(f"Diagnosing alarm {request.alarm_id} ({request.alarm_name})")

    try:
        from backend.agent import diagnose_alarm as agent_diagnose

        alarm_dict = {
            "alarm_id": request.alarm_id,
            "alarm_name": request.alarm_name,
            "alarm_text": request.alarm_text,
            "node_name": request.node_name,
            "alarm_type": request.alarm_type,
            "timestamp": request.timestamp or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        result = agent_diagnose(
            alarm=alarm_dict,
            recent_alarms=None,
            language=language,
        )

        return {
            "status": "success",
            "diagnosis": result,
            "language": language,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        logger.error(f"Diagnosis failed for {request.alarm_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/diagnose/batch")
async def diagnose_batch(request: BatchAlarmRequest, http_request: Request):
    """
    Diagnose multiple alarms in batch.
    Correlates alarms with each other for root cause analysis.
    """
    language = _get_language(http_request)
    logger.info(f"Batch diagnosing {len(request.alarms)} alarms")

    try:
        from backend.agent import diagnose_batch as agent_batch

        alarm_dicts = [
            {
                "alarm_id": a.alarm_id,
                "alarm_name": a.alarm_name,
                "alarm_text": a.alarm_text,
                "node_name": a.node_name,
                "alarm_type": a.alarm_type,
                "timestamp": a.timestamp or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            for a in request.alarms
        ]

        results = agent_batch(
            alarms=alarm_dicts,
            language=language,
        )

        return {
            "status": "success",
            "diagnoses": results,
            "count": len(results),
            "language": language,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        logger.error(f"Batch diagnosis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── MTTR Endpoints ──────────────────────────────────────────────────────────

@app.get("/mttr")
async def get_mttr(
    node_name: Optional[str] = None,
    severity: Optional[str] = None,
    hours: int = 24,
):
    """
    Get MTTR report.
    
    Query params:
    - node_name: Filter by node
    - severity: Filter by severity (P1/P2/P3/P4)
    - hours: Lookback window (default 24)
    """
    try:
        from backend.mttr import get_mttr_report
        report = get_mttr_report(
            node_name=node_name,
            severity=severity,
            hours=hours,
        )
        return {
            "status": "success",
            "mttr_report": report,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"MTTR report failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Trends Endpoints ────────────────────────────────────────────────────────

@app.get("/trends")
async def get_trends(
    node_name: Optional[str] = None,
    hours: int = 24,
):
    """
    Get degradation trend analysis.
    
    Query params:
    - node_name: Filter by node
    - hours: Lookback window (default 24)
    """
    try:
        from backend.trends import get_trend_summary
        summary = get_trend_summary()
        return {
            "status": "success",
            "trends": summary,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"Trend analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Escalation Endpoints ────────────────────────────────────────────────────

@app.get("/escalations")
async def get_escalations():
    """
    Get the current escalation queue.
    Returns pending escalations sorted by urgency (most urgent first).
    """
    try:
        from backend.escalation import get_escalation_summary
        summary = get_escalation_summary()
        return {
            "status": "success",
            "escalations": summary,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"Escalation queue failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/escalations/{escalation_id}/acknowledge")
async def acknowledge_escalation(escalation_id: int):
    """Acknowledge an escalation"""
    try:
        from backend.database import acknowledge_escalation
        result = acknowledge_escalation(escalation_id)
        if not result:
            raise HTTPException(status_code=404, detail="Escalation not found")
        return {"status": "success", "escalation": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Acknowledge escalation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Maintenance Window Endpoints ────────────────────────────────────────────

@app.post("/maintenance")
async def register_maintenance(request: MaintenanceRequest):
    """Register a planned maintenance window for a node"""
    try:
        from backend.database import register_maintenance_window
        result = register_maintenance_window(
            node_name=request.node_name,
            start_time=request.start_time,
            end_time=request.end_time,
            reason=request.reason,
            created_by=request.created_by,
        )
        return {
            "status": "success",
            "maintenance_window": result,
        }
    except Exception as e:
        logger.error(f"Register maintenance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/maintenance")
async def get_maintenance_windows():
    """Get all active maintenance windows"""
    try:
        from backend.database import get_active_maintenance_windows
        windows = get_active_maintenance_windows()
        return {"status": "success", "windows": windows}
    except Exception as e:
        logger.error(f"Get maintenance windows failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Incidents Endpoints ─────────────────────────────────────────────────────

@app.get("/incidents")
async def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    node_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List incidents with optional filters"""
    try:
        from backend.database import list_incidents
        incidents = list_incidents(
            status=status,
            severity=severity,
            node_name=node_name,
            limit=limit,
            offset=offset,
        )
        return {
            "status": "success",
            "incidents": incidents,
            "count": len(incidents),
        }
    except Exception as e:
        logger.error(f"List incidents failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/incidents/{alarm_id}")
async def get_incident(alarm_id: str):
    """Get a single incident by alarm ID"""
    try:
        from backend.database import get_incident_by_alarm_id
        incident = get_incident_by_alarm_id(alarm_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"status": "success", "incident": incident}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get incident failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/incidents/{alarm_id}/resolve")
async def resolve_incident(alarm_id: str, request: ResolveRequest):
    """Resolve an incident (stops MTTR timer)"""
    try:
        from backend.database import get_incident_by_alarm_id, update_incident
        from backend.mttr import stop_mttr_timer

        incident = get_incident_by_alarm_id(alarm_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Stop MTTR timer
        mttr_result = stop_mttr_timer(alarm_id, incident.get("mttr_started_at", ""))

        # Update incident
        updated = update_incident(incident["id"], {
            "status": "resolved",
            "mttr_resolved_at": mttr_result["mttr_resolved_at"],
            "mttr_seconds": mttr_result["mttr_seconds"],
        })

        return {
            "status": "success",
            "incident": updated,
            "mttr": mttr_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resolve incident failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Ingest Endpoint ─────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_alarms(filepath: str = "/data/sample_alarms.json"):
    """
    Ingest alarm logs from a JSON file already on the server.
    Skips RAG context during bulk ingestion to keep startup fast.
    RAG is used for live single-alarm diagnosis and the agent.
    """
    import asyncio
    try:
        from backend.ingest import ingest_alarm_logs

        def _run():
            os.environ["SKIP_RAG"] = "1"
            try:
                return ingest_alarm_logs(filepath=filepath)
            finally:
                os.environ.pop("SKIP_RAG", None)

        result = await asyncio.to_thread(_run)
        return {
            "status": result["status"],
            "result": result,
        }
    except Exception as e:
        logger.error(f"Ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/upload")
async def ingest_uploaded_logs(file: UploadFile = File(...)):
    """
    Upload and ingest a user-provided alarm log file (.json, .jsonl, or .csv).

    The file is saved to /data/uploads/ and then run through the same
    diagnosis pipeline as the sample data.
    """
    try:
        from backend.ingest import ingest_alarm_logs

        allowed_ext = (".json", ".jsonl", ".csv", ".txt")
        filename = file.filename or "uploaded_logs.json"
        if not filename.lower().endswith(allowed_ext):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Allowed: {', '.join(allowed_ext)}",
            )

        upload_dir = "/data/uploads"
        os.makedirs(upload_dir, exist_ok=True)

        # Avoid overwriting previous uploads
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        safe_name = f"{timestamp}_{filename}"
        dest_path = os.path.join(upload_dir, safe_name)

        contents = await file.read()

        # CSV support: convert to the alarm JSON shape ingest_alarm_logs expects
        if filename.lower().endswith(".csv"):
            import csv
            import io

            text = contents.decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            alarms = [dict(row) for row in reader]

            json_path = dest_path.rsplit(".", 1)[0] + ".json"
            with open(json_path, "w") as f:
                json.dump(alarms, f, indent=2)
            dest_path = json_path
        else:
            with open(dest_path, "wb") as f:
                f.write(contents)

        logger.info(f"Saved uploaded log file to {dest_path}")

        result = ingest_alarm_logs(filepath=dest_path)
        return {
            "status": result["status"],
            "filename": filename,
            "saved_as": dest_path,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Review Queue Endpoint ──────────────────────────────────────────────────

@app.get("/review")
async def get_review_queue():
    """Get items flagged for human review (low confidence)"""
    try:
        from backend.database import get_pending_review_items
        items = get_pending_review_items()
        return {
            "status": "success",
            "items": items,
            "count": len(items),
        }
    except Exception as e:
        logger.error(f"Review queue failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Correlation Endpoint ────────────────────────────────────────────────────

@app.post("/correlate")
async def correlate_alarms(alarms: List[AlarmRequest]):
    """Correlate a set of alarms into root cause clusters"""
    try:
        from backend.correlator import correlate_alarms

        alarm_dicts = [
            {
                "alarm_id": a.alarm_id,
                "alarm_text": a.alarm_text,
                "node_name": a.node_name,
                "alarm_type": a.alarm_type,
                "timestamp": a.timestamp or "",
            }
            for a in alarms
        ]

        groups = correlate_alarms(alarm_dicts)
        return {
            "status": "success",
            "correlation_groups": groups,
            "count": len(groups),
        }
    except Exception as e:
        logger.error(f"Correlation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Dashboard Data Endpoint ─────────────────────────────────────────────────

@app.get("/dashboard")
async def get_dashboard_data():
    """
    Get all dashboard data in one call.
    Combines MTTR, trends, escalations, and incidents overview.
    """
    try:
        from backend.mttr import get_mttr_report
        from backend.trends import get_trend_summary
        from backend.escalation import get_escalation_summary
        from backend.database import list_incidents

        mttr = get_mttr_report()
        trends = get_trend_summary()
        escalations = get_escalation_summary()
        recent_incidents = list_incidents(limit=20)
        open_count = len(list_incidents(status="open"))
        p1_count = len(list_incidents(severity="P1", status="open"))

        return {
            "status": "success",
            "dashboard": {
                "mttr": mttr,
                "trends": trends,
                "escalations": escalations,
                "recent_incidents": recent_incidents,
                "counts": {
                    "open_incidents": open_count,
                    "open_p1": p1_count,
                    "total_recent": len(recent_incidents),
                },
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.error(f"Dashboard data failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Agent Chat Endpoint ─────────────────────────────────────────────────────

@app.post("/agent/chat")
async def agent_chat(request: AgentChatRequest):
    """
    Tool-using agent endpoint.

    Runs the NOC agent loop: the LLM decides which tools to call
    (get_active_alerts, get_logs, lookup_incident, search_knowledge_base),
    executes them against real data, and iterates until it has a final answer.

    Returns the final answer plus a full reasoning trace (which tools were
    called, with what arguments, and what they returned).
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    logger.info("Agent chat request: %s", request.query[:120])

    try:
        import asyncio
        import re
        from backend.noc_agent import run_agent

        # run_agent is synchronous (uses urllib) — run in thread to avoid blocking
        result = await asyncio.to_thread(run_agent, request.query, request.session_id)
        # Strip model citation artifacts some LLMs inject (e.g. 【{"id":0}】)
        answer = re.sub(r'[\u3010\u3011][^】]*[\u3010\u3011]?', '', result["answer"]).strip()
        answer = re.sub(r'\s{2,}', ' ', answer)
        return {
            "status":     "success",
            "answer":     answer,
            "trace":      result["trace"],
            "iterations": result["iterations"],
            "model":      result["model"],
            "session_id": result["session_id"],
            "timestamp":  datetime.utcnow().isoformat() + "Z",
        }
    except Exception as exc:
        logger.error("Agent chat failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_language(request: Request) -> str:
    """Extract language preference from Accept-Language header."""
    accept_lang = request.headers.get("Accept-Language", "en")
    if accept_lang and accept_lang.startswith("sw"):
        return "sw"
    return "en"


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        log_level="info",
        reload=True,
    )