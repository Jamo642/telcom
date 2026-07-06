"""
Async tool functions for the TeleNOC autonomous agent.

These tools wrap existing TeleNOC modules so the autonomous agent can run
ReAct-style action steps without blocking the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.agent_memory import AgentMemory, get_agent_memory

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(ts: Optional[datetime] = None) -> str:
    value = ts or _utc_now()
    return value.isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _default_db_path() -> str:
    try:
        from backend.database import DB_PATH  # pylint: disable=import-outside-toplevel

        return DB_PATH
    except Exception:
        return os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db")


async def tool_diagnose(
    alarm_text: str,
    alarm_id: str,
    *,
    alarm_name: str = "",
    node_name: str = "",
    alarm_type: str = "",
    timestamp: Optional[str] = None,
    language: str = "en",
    recent_alarms: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the existing full diagnosis pipeline as an async tool."""
    from backend.agent import diagnose_alarm

    alarm = {
        "alarm_id": alarm_id,
        "alarm_name": alarm_name,
        "alarm_text": alarm_text,
        "node_name": node_name,
        "alarm_type": alarm_type,
        "timestamp": timestamp or _utc_iso(),
    }

    resolved_db_path = db_path or _default_db_path()

    diagnosis = await asyncio.to_thread(
        diagnose_alarm,
        alarm,
        recent_alarms,
        language,
        resolved_db_path,
    )

    return {
        "status": "success",
        "tool": "diagnose",
        "alarm_id": alarm_id,
        "diagnosis": diagnosis,
    }


async def tool_correlate(
    alarm: Dict[str, Any],
    recent_alarms: Optional[List[Dict[str, Any]]] = None,
    *,
    window_seconds: int = 300,
) -> Dict[str, Any]:
    """Correlate an alarm with nearby alarm context using existing correlator logic."""
    from backend.correlator import correlate_alarms, find_related_alarms

    history = list(recent_alarms or [])
    all_alarms = history + [alarm]

    groups = await asyncio.to_thread(correlate_alarms, all_alarms, window_seconds)
    related = await asyncio.to_thread(find_related_alarms, alarm.get("alarm_id", ""), groups)

    return {
        "status": "success",
        "tool": "correlate",
        "alarm_id": alarm.get("alarm_id", ""),
        "group_count": len(groups),
        "related_group": related,
    }


async def tool_escalate(
    alarm_id: str,
    severity: str,
    team: Optional[str] = None,
    *,
    reason: str = "Autonomous escalation",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create an escalation record and update incident status.

    Notification dispatch is represented as a structured result so this tool can
    be upgraded later for real webhook/email integrations.
    """
    from backend.database import (
        create_escalation,
        get_incident_by_alarm_id,
        log_incident,
        update_incident,
    )
    from backend.escalation import SLA_ROLES, SLA_TIMERS, check_escalation

    resolved_db_path = db_path or _default_db_path()
    incident = await asyncio.to_thread(get_incident_by_alarm_id, alarm_id, resolved_db_path)

    if not incident:
        incident = await asyncio.to_thread(
            log_incident,
            alarm_id,
            severity,
            1.0,
            "Autonomous escalation pending diagnosis",
            "Manual triage recommended",
            "NOC-SOP-GEN-001",
            team or SLA_ROLES.get(severity, "Network Engineer"),
            "immediate",
            "",
            "",
            "",
            "",
            resolved_db_path,
        )

    escalation_check = await asyncio.to_thread(check_escalation, incident, resolved_db_path)

    escalated_to = team or escalation_check.get("escalate_to") or SLA_ROLES.get(severity, "Network Engineer")
    timer_seconds = SLA_TIMERS.get(severity, 3600)
    default_deadline = _utc_iso(_utc_now() + timedelta(seconds=timer_seconds))
    sla_deadline = escalation_check.get("sla_deadline") or default_deadline

    escalation_row = await asyncio.to_thread(
        create_escalation,
        incident["id"],
        alarm_id,
        escalated_to,
        sla_deadline,
        reason,
        resolved_db_path,
    )

    updated_incident = await asyncio.to_thread(
        update_incident,
        incident["id"],
        {
            "status": "escalated",
            "escalate_to": escalated_to,
        },
        resolved_db_path,
    )

    return {
        "status": "success",
        "tool": "escalate",
        "alarm_id": alarm_id,
        "incident_id": incident["id"],
        "escalated_to": escalated_to,
        "sla_deadline": sla_deadline,
        "escalation": escalation_row,
        "incident": updated_incident,
        "notification": {
            "sent": True,
            "channel": "internal_webhook_simulated",
            "message": f"Escalated {alarm_id} to {escalated_to}",
        },
    }


async def tool_watch(
    node_name: str,
    reason: str,
    *,
    ttl_minutes: int = 120,
    memory: Optional[AgentMemory] = None,
) -> Dict[str, Any]:
    """Add a node to the agent watchlist for tighter monitoring."""
    mem = memory or get_agent_memory()
    await mem.add_watch(node_name=node_name, reason=reason, ttl_minutes=ttl_minutes)

    return {
        "status": "success",
        "tool": "watch",
        "node_name": node_name,
        "reason": reason,
        "expires_at": _utc_iso(_utc_now() + timedelta(minutes=ttl_minutes)),
    }


async def tool_resolve(
    alarm_id: str,
    *,
    resolution_notes: str = "Autonomous resolution",
    memory: Optional[AgentMemory] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve an incident and stop MTTR timing."""
    from backend.database import get_incident_by_alarm_id, update_incident
    from backend.mttr import stop_mttr_timer

    resolved_db_path = db_path or _default_db_path()
    incident = await asyncio.to_thread(get_incident_by_alarm_id, alarm_id, resolved_db_path)

    if not incident:
        return {
            "status": "error",
            "tool": "resolve",
            "alarm_id": alarm_id,
            "error": "Incident not found",
        }

    mttr = await asyncio.to_thread(stop_mttr_timer, alarm_id, incident.get("mttr_started_at", _utc_iso()))

    updated_incident = await asyncio.to_thread(
        update_incident,
        incident["id"],
        {
            "status": "resolved",
            "mttr_resolved_at": mttr.get("mttr_resolved_at"),
            "mttr_seconds": mttr.get("mttr_seconds"),
            "recommended_action": resolution_notes,
        },
        resolved_db_path,
    )

    mem = memory or get_agent_memory()
    await mem.resolve_incident(alarm_id, resolution="resolved")

    return {
        "status": "success",
        "tool": "resolve",
        "alarm_id": alarm_id,
        "incident": updated_incident,
        "mttr": mttr,
    }


async def tool_fight_check(
    alarm_text: str,
    alarm_id: str,
    *,
    node_name: str = "",
    memory: Optional[AgentMemory] = None,
) -> Dict[str, Any]:
    """
    Run MITRE FiGHT detection when the detector module is available.

    If the module is unavailable, a conservative keyword heuristic is used.
    """
    mem = memory or get_agent_memory()

    detection: Dict[str, Any]
    try:
        from backend import fight_detector  # type: ignore

        if hasattr(fight_detector, "analyze_alarm"):
            raw = await asyncio.to_thread(fight_detector.analyze_alarm, alarm_text)
        elif hasattr(fight_detector, "fight_check"):
            raw = await asyncio.to_thread(fight_detector.fight_check, alarm_text)
        else:
            raw = {"detected": False, "reason": "Unsupported fight detector API"}

        detection = {
            "alarm_id": alarm_id,
            "node_name": node_name,
            "detected": bool(raw.get("detected") or raw.get("is_threat")),
            "signature": raw.get("signature") or raw.get("technique") or "",
            "confidence": float(raw.get("confidence", 0.0) or 0.0),
            "details": raw,
            "detected_at": _utc_iso(),
        }
    except Exception:
        lower_text = alarm_text.lower()
        keywords = [
            "ss7",
            "map anomaly",
            "diameter",
            "gt spoof",
            "signaling flood",
            "sctp reset storm",
        ]
        matched = [word for word in keywords if word in lower_text]
        detection = {
            "alarm_id": alarm_id,
            "node_name": node_name,
            "detected": len(matched) > 0,
            "signature": "FGT-HEURISTIC-001" if matched else "",
            "confidence": 0.65 if matched else 0.0,
            "details": {
                "mode": "heuristic",
                "matched_keywords": matched,
            },
            "detected_at": _utc_iso(),
        }

    if detection["detected"]:
        await mem.remember_fight_detection(detection)

    return {
        "status": "success",
        "tool": "fight_check",
        "alarm_id": alarm_id,
        "detection": detection,
    }


async def tool_summarize(
    time_window_hours: int = 8,
    *,
    memory: Optional[AgentMemory] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate shift handover summary from incidents, MTTR stats, and memory."""
    from backend.database import get_pending_escalations, list_incidents
    from backend.mttr import get_mttr_report

    mem = memory or get_agent_memory()
    resolved_db_path = db_path or _default_db_path()

    all_recent = await asyncio.to_thread(
        list_incidents,
        None,
        None,
        None,
        1000,
        0,
        resolved_db_path,
    )

    cutoff = _utc_now() - timedelta(hours=time_window_hours)
    handled = []
    for incident in all_recent:
        created_at = incident.get("created_at")
        if not created_at:
            continue
        try:
            if _parse_iso(created_at) >= cutoff:
                handled.append(incident)
        except Exception:
            continue

    p1s = [inc for inc in handled if (inc.get("severity") or "").upper() == "P1"]
    open_incidents = [inc for inc in all_recent if (inc.get("status") or "").lower() != "resolved"]

    pending_escalations = await asyncio.to_thread(get_pending_escalations, resolved_db_path)
    mttr_report = await asyncio.to_thread(
        get_mttr_report,
        None,
        None,
        time_window_hours,
        resolved_db_path,
    )
    mem_metrics = await mem.get_shift_metrics()
    logs = await mem.get_recent_logs(limit=50)

    return {
        "status": "success",
        "tool": "summarize",
        "window_hours": time_window_hours,
        "generated_at": _utc_iso(),
        "summary": {
            "alarms_handled": len(handled),
            "p1_detected": len(p1s),
            "fight_detections": mem_metrics.get("fight_threats", 0),
            "open_incidents": len(open_incidents),
            "pending_escalations": len(pending_escalations),
            "watchlist_nodes": mem_metrics.get("watchlist_nodes", 0),
            "average_mttr_seconds": (mttr_report.get("overall_mttr") or {}).get("mean", 0),
        },
        "mttr": mttr_report,
        "recent_logs": logs,
    }


TOOL_REGISTRY = {
    "DIAGNOSE": tool_diagnose,
    "CORRELATE": tool_correlate,
    "ESCALATE": tool_escalate,
    "WATCH": tool_watch,
    "RESOLVE": tool_resolve,
    "FIGHT_CHECK": tool_fight_check,
    "SUMMARIZE": tool_summarize,
}
