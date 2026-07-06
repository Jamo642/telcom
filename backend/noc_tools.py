"""
NOC Agent Tools — callable functions exposed to the LLM via function-calling.

Each tool has:
  - A Python implementation that calls the real data source
  - A JSON schema descriptor (TOOL_SCHEMAS) for OpenRouter's function-calling API
  - read_only=True unless it mutates state

Mutating tools (read_only=False) are listed in MUTATING_TOOLS and must be
confirmed by the user before the agent executes them.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Tool Schemas (passed to the LLM) ────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_active_alerts",
            "description": (
                "Returns current NOC incidents/alerts from the database. "
                "Optionally filter by severity (P1/P2/P3/P4) and/or node name. "
                "Use this first to understand what is currently active."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["P1", "P2", "P3", "P4"],
                        "description": "Filter by severity level. Omit to get all.",
                    },
                    "node_name": {
                        "type": "string",
                        "description": "Filter by node/device name. Omit to get all nodes.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of alerts to return (default 20).",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_logs",
            "description": (
                "Fetches raw syslog lines from on-disk log files for a given source/node. "
                "Use this to dig into what happened on a specific device. "
                "Available sources: bgp_convergence_region_a, bng_east_high_cpu, "
                "dns_timeout_resolution, node_b12_packet_loss, router03_disk_full."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": (
                            "Log source name (filename without .log extension). "
                            "E.g. 'bng_east_high_cpu' or 'bgp_convergence_region_a'."
                        ),
                    },
                    "time_range": {
                        "type": "string",
                        "description": (
                            "Describe the time range of interest in plain text, "
                            "e.g. 'last hour', '2024-01-15 18:30 to 19:00'. "
                            "Used for filtering log lines by timestamp."
                        ),
                    },
                    "keyword": {
                        "type": "string",
                        "description": "Optional keyword to filter log lines (case-insensitive).",
                    },
                },
                "required": ["source"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_incident",
            "description": (
                "Returns full details of a known incident by its alarm_id "
                "(e.g. 'ALM-001') or incident database ID. "
                "Use this to get root cause, recommended actions, severity, "
                "and status for a specific alarm."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": (
                            "The alarm_id (e.g. 'ALM-042') or numeric incident DB id."
                        ),
                    },
                },
                "required": ["incident_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Searches the incident history and knowledge base for past incidents "
                "similar to a query. Returns matching incidents ranked by relevance. "
                "Use this when you need historical context or runbook guidance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what to search for.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# Tools that mutate state — require explicit user confirmation before execution
MUTATING_TOOLS: set[str] = set()  # all current tools are read-only

# ─── Tool Implementations ─────────────────────────────────────────────────────

def _db_path() -> str:
    try:
        from backend.database import DB_PATH
        return DB_PATH
    except Exception:
        return os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db")


def get_active_alerts(
    severity: Optional[str] = None,
    node_name: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Read-only: query incidents table."""
    try:
        from backend.database import list_incidents
        # Get a large batch to compute accurate total count
        all_rows = list_incidents(
            status=None,
            severity=severity,
            node_name=node_name,
            limit=500,
            offset=0,
            db_path=_db_path(),
        )
        total = len(all_rows)
        rows = all_rows[:limit]
        # Trim large fields for LLM context
        slim = []
        for r in rows:
            slim.append({
                "alarm_id":   r.get("alarm_id"),
                "alarm_name": r.get("alarm_name"),
                "node_name":  r.get("node_name"),
                "alarm_type": r.get("alarm_type"),
                "severity":   r.get("severity"),
                "status":     r.get("status"),
                "root_cause": r.get("root_cause", "")[:200],
                "created_at": r.get("created_at"),
            })
        return {"alerts": slim, "count": total, "shown": len(slim)}
    except Exception as exc:
        logger.error("get_active_alerts failed: %s", exc)
        return {"error": str(exc), "alerts": [], "count": 0}


def get_logs(
    source: str,
    time_range: str = "",
    keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """Read-only: read on-disk log files."""
    log_dir = Path(os.environ.get("LOG_DIR", "/data/logs"))
    if not log_dir.exists():
        # Try relative path for local dev
        log_dir = Path(__file__).parent.parent / "data" / "logs"

    target = log_dir / f"{source}.log"
    if not target.exists():
        available = [p.stem for p in log_dir.glob("*.log")]
        return {
            "error": f"Log source '{source}' not found.",
            "available_sources": available,
            "lines": [],
        }

    try:
        lines = target.read_text().splitlines()
    except Exception as exc:
        return {"error": str(exc), "lines": []}

    # Apply keyword filter
    if keyword:
        lines = [l for l in lines if keyword.lower() in l.lower()]

    # Apply rough time-range filter if a timestamp hint was given
    if time_range and "last" not in time_range.lower():
        # Extract any timestamps from time_range and filter
        filtered = []
        for line in lines:
            # Keep lines that contain any token from the time_range hint
            tokens = [t for t in time_range.split() if len(t) > 4]
            if any(t in line for t in tokens):
                filtered.append(line)
        if filtered:
            lines = filtered

    return {
        "source": source,
        "time_range": time_range or "all",
        "lines": lines,
        "count": len(lines),
    }


def lookup_incident(incident_id: str) -> Dict[str, Any]:
    """Read-only: fetch one incident by alarm_id or numeric id."""
    try:
        from backend.database import get_incident_by_alarm_id, get_incident_by_id
        # Try alarm_id string first (e.g. "ALM-001")
        row = get_incident_by_alarm_id(incident_id, db_path=_db_path())
        if not row:
            # Try numeric DB id
            try:
                row = get_incident_by_id(int(incident_id), db_path=_db_path())
            except (ValueError, TypeError):
                pass
        if not row:
            return {"error": f"Incident '{incident_id}' not found."}
        return {"incident": dict(row)}
    except Exception as exc:
        logger.error("lookup_incident failed: %s", exc)
        return {"error": str(exc)}


def search_knowledge_base(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Read-only: semantic vector search over ChromaDB knowledge base.
    Falls back to keyword search over SQLite incidents if ChromaDB is unavailable.
    """
    # ── Try ChromaDB vector search first ─────────────────────────────────────
    try:
        import chromadb
        from services.embedding_service import get_embedding_service

        chroma_path = os.environ.get("CHROMA_DB_PATH", "/data/chroma_db")
        if not Path(chroma_path).exists():
            chroma_path = str(Path(__file__).parent.parent / "data" / "chroma_db")

        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection("telecom_incidents")

        emb_svc = get_embedding_service()
        query_vector = emb_svc.embed_text(query).tolist()

        hits = collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        results = []
        docs      = hits.get("documents", [[]])[0]
        metas     = hits.get("metadatas", [[]])[0]
        distances = hits.get("distances",  [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            similarity = round(1.0 - dist, 4)  # ChromaDB returns L2 distance
            results.append({
                "document":   doc[:400],
                "metadata":   meta,
                "similarity": similarity,
                "source":     meta.get("source", "unknown"),
            })

        logger.info("ChromaDB RAG: %d results for query '%s'", len(results), query[:60])
        return {
            "results": results,
            "count":   len(results),
            "query":   query,
            "backend": "chromadb_vector",
        }

    except Exception as chroma_exc:
        logger.warning("ChromaDB search failed (%s), falling back to keyword search", chroma_exc)

    # ── Keyword fallback over SQLite incidents ────────────────────────────────
    try:
        from backend.database import list_incidents
        all_rows = list_incidents(limit=200, db_path=_db_path())
        query_lower = query.lower()
        tokens = [t for t in query_lower.split() if len(t) > 3]

        scored = []
        for row in all_rows:
            text = " ".join([
                str(row.get("alarm_name", "")),
                str(row.get("alarm_type", "")),
                str(row.get("root_cause", "")),
                str(row.get("raw_alarm_text", "")),
                str(row.get("recommended_action", "")),
            ]).lower()
            score = sum(text.count(t) for t in tokens)
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, row in scored[:top_k]:
            results.append({
                "alarm_id":           row.get("alarm_id"),
                "alarm_name":         row.get("alarm_name"),
                "node_name":          row.get("node_name"),
                "severity":           row.get("severity"),
                "root_cause":         row.get("root_cause", "")[:300],
                "recommended_action": row.get("recommended_action", "")[:300],
                "relevant_runbook":   row.get("relevant_runbook"),
                "source":             "sqlite_keyword",
            })
        return {
            "results": results,
            "count":   len(results),
            "query":   query,
            "backend": "sqlite_keyword",
        }
    except Exception as exc:
        logger.error("search_knowledge_base fallback failed: %s", exc)
        return {"error": str(exc), "results": [], "backend": "error"}


# ─── FiGHT tool wrappers (thin — delegate to fight_engine.py) ────────────────

def detect_fight_techniques(
    alerts: Optional[List[Dict[str, Any]]] = None,
    logs: Optional[List[str]] = None,
    asset: str = "",
) -> Dict[str, Any]:
    """Read-only: detect MITRE FiGHT techniques from alert/log evidence."""
    from backend.fight_engine import detect_fight_techniques as _detect
    return _detect(alerts or [], logs or [], asset=asset)


def explain_fight_technique(technique_id: str) -> Dict[str, Any]:
    """Read-only: RAG-grounded explanation of a MITRE FiGHT technique."""
    from backend.fight_engine import explain_fight_technique as _explain
    return _explain(technique_id)


def remediate_fight_technique(
    technique_id: str,
    target: str,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """MUTATING (requires approval): propose/execute remediation for a FiGHT technique."""
    from backend.fight_engine import remediate_fight_technique as _remediate
    return _remediate(technique_id, target, confirmed=confirmed)


# ─── Add FiGHT schemas to TOOL_SCHEMAS ────────────────────────────────────────

TOOL_SCHEMAS.extend([
    {
        "type": "function",
        "function": {
            "name": "detect_fight_techniques",
            "description": (
                "Analyse a list of NOC alerts and log lines for MITRE FiGHT 5G/telecom "
                "threat techniques. Returns findings with confidence scores, matched "
                "indicators, kill-chain notes, and self-critique. "
                "Call this when alarms suggest SS7/Diameter/GTP anomalies, rogue base "
                "stations, authentication storms, or signalling floods."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alerts": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of alert/incident dicts from get_active_alerts.",
                    },
                    "logs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of raw log line strings from get_logs.",
                    },
                    "asset": {
                        "type": "string",
                        "description": "Node/asset name for allowlist lookup.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_fight_technique",
            "description": (
                "Return a RAG-grounded, NOC-operator-friendly explanation of a specific "
                "MITRE FiGHT technique — what it is, how to detect it, and top mitigations. "
                "Use after detect_fight_techniques surfaces a finding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "technique_id": {
                        "type": "string",
                        "description": "MITRE FiGHT technique ID, e.g. 'FGT5019'.",
                    },
                },
                "required": ["technique_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remediate_fight_technique",
            "description": (
                "⚠️ MUTATING — requires operator approval. "
                "Propose a remediation action for a detected FiGHT technique. "
                "Returns a proposal with 'approve? (yes/no)'. "
                "Only call this when the operator explicitly requests remediation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "technique_id": {"type": "string", "description": "FiGHT technique ID."},
                    "target":       {"type": "string", "description": "Target asset/node name."},
                    "confirmed":    {"type": "boolean", "description": "Set true only on explicit operator approval.", "default": False},
                },
                "required": ["technique_id", "target"],
            },
        },
    },
])

# ─── Dispatch table ───────────────────────────────────────────────────────────

MUTATING_TOOLS: set[str] = {"remediate_fight_technique"}

TOOL_IMPLEMENTATIONS: Dict[str, Any] = {
    "get_active_alerts":        get_active_alerts,
    "get_logs":                 get_logs,
    "lookup_incident":          lookup_incident,
    "search_knowledge_base":    search_knowledge_base,
    "detect_fight_techniques":  detect_fight_techniques,
    "explain_fight_technique":  explain_fight_technique,
    "remediate_fight_technique": remediate_fight_technique,
}
