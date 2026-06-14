"""
SLA-Aware Auto-Escalation Module for TeleNOC AI

Handles automatic escalation of unresolved alarms based on SLA timers.
Integrates false-positive prevention:
- Maintenance window awareness: skip nodes in planned maintenance
- Transient alarm filtering: ignore alarms that self-clear in under 60 seconds
- Confidence scoring: low confidence (<0.75) flags for human review, no auto-escalate
- P1 confirmation: require 2 similar alarms within 5 minutes before classifying P1

SLA Timers:
- P1 → escalate to NOC Lead after 15 min
- P2 → escalate to NOC Supervisor after 30 min
- P3 → escalate to Network Engineer after 2 hours
- P4 → escalate to Junior Engineer after 8 hours
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# SLA timers in seconds
SLA_TIMERS = {
    "P1": 900,    # 15 minutes
    "P2": 1800,   # 30 minutes
    "P3": 7200,   # 2 hours
    "P4": 28800,  # 8 hours
}

SLA_ROLES = {
    "P1": "NOC Lead",
    "P2": "NOC Supervisor",
    "P3": "Network Engineer",
    "P4": "Junior Engineer",
}

# Minimum confidence for auto-escalation
AUTO_ESCALATE_CONFIDENCE = 0.75
# Transient alarm threshold (seconds)
TRANSIENT_THRESHOLD = 60
# P1 confirmation count and window
P1_CONFIRMATION_COUNT = 2
P1_CONFIRMATION_WINDOW = 300  # 5 minutes


def check_escalation(
    incident: Dict[str, Any],
    db_path: str = "/data/telenoc.db",
) -> Dict[str, Any]:
    """
    Check if an incident needs escalation based on SLA timers and false-positive checks.
    
    Args:
        incident: Incident dict from database (must have severity, confidence, 
                  alarm_id, node_name, created_at, status keys)
        db_path: Path to SQLite database
    
    Returns:
        Dict with:
        - should_escalate: bool
        - reason: Escalation reason or reason not to escalate
        - escalate_to: Who to escalate to
        - sla_deadline: SLA deadline timestamp
        - time_remaining: Seconds remaining before SLA breach
        - is_transient: Whether alarm is transient
        - in_maintenance: Whether node is in maintenance
        - needs_review: Whether human review is needed before escalation
    """
    logger.info(f"Checking escalation for {incident.get('alarm_id', 'unknown')}")

    result = {
        "should_escalate": False,
        "reason": "",
        "escalate_to": "",
        "sla_deadline": "",
        "time_remaining": 0,
        "is_transient": False,
        "in_maintenance": False,
        "needs_review": False,
        "checklist": {
            "confidence_check": False,
            "maintenance_check": False,
            "transient_check": False,
            "p1_confirmation_check": True,  # Default to True for non-P1
            "sla_timer_check": False,
        },
    }

    severity = incident.get("severity", "P4")
    confidence = incident.get("confidence", 0.0)
    node_name = incident.get("node_name", "")
    alarm_id = incident.get("alarm_id", "")
    status = incident.get("status", "open")

    # Only check open or acknowledged incidents
    if status not in ("open", "acknowledged"):
        result["reason"] = f"Incident status is '{status}', no escalation needed"
        return result

    # ─── Check 1: Confidence Check ─────────────────────────────────────────
    if confidence < AUTO_ESCALATE_CONFIDENCE:
        logger.info(f"Confidence {confidence} below auto-escalate threshold for {alarm_id}")
        result["checklist"]["confidence_check"] = False
        result["needs_review"] = True
        result["reason"] = (
            f"Low confidence ({confidence:.2f} < {AUTO_ESCALATE_CONFIDENCE}). "
            "Flagged for human review - no auto-escalation."
        )
        result["escalate_to"] = "NOC Reviewer"
        return result  # Don't auto-escalate, flag for review
    else:
        result["checklist"]["confidence_check"] = True

    # ─── Check 2: Maintenance Window Check ─────────────────────────────────
    if _is_in_maintenance(node_name, db_path):
        logger.info(f"Node {node_name} is in maintenance window - skipping escalation")
        result["checklist"]["maintenance_check"] = False
        result["in_maintenance"] = True
        result["reason"] = (
            f"Node {node_name} is in planned maintenance window. "
            "Alarm suppressed - no escalation."
        )
        return result  # Suppress alarm entirely during maintenance
    else:
        result["checklist"]["maintenance_check"] = True

    # ─── Check 3: Transient Alarm Check ────────────────────────────────────
    if _is_transient(alarm_id, db_path):
        logger.info(f"Alarm {alarm_id} is transient - skipping escalation")
        result["checklist"]["transient_check"] = False
        result["is_transient"] = True
        result["reason"] = (
            f"Alarm {alarm_id} identified as transient (self-cleared < {TRANSIENT_THRESHOLD}s). "
            "No escalation needed."
        )
        return result  # Don't escalate transient alarms
    else:
        result["checklist"]["transient_check"] = True

    # ─── Check 4: P1 Confirmation Check ────────────────────────────────────
    if severity == "P1":
        p1_confirmed = _check_p1_confirmation(alarm_id, node_name, db_path)
        result["checklist"]["p1_confirmation_check"] = p1_confirmed
        if not p1_confirmed:
            result["reason"] = (
                "P1 requires 2 similar alarms within 5 minutes. "
                "Insufficient confirmation - monitoring."
            )
            result["needs_review"] = True
            return result
    else:
        result["checklist"]["p1_confirmation_check"] = True

    # ─── Check 5: SLA Timer Check ──────────────────────────────────────────
    sla_seconds = SLA_TIMERS.get(severity, 7200)
    sla_role = SLA_ROLES.get(severity, "Network Engineer")

    # Calculate deadline
    created_at = incident.get("created_at") or incident.get("mttr_started_at")
    if not created_at:
        created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        sla_deadline_dt = created_dt + timedelta(seconds=sla_seconds)
        now = datetime.utcnow()
        time_elapsed = (now - created_dt).total_seconds()
        time_remaining = (sla_deadline_dt - now).total_seconds()
    except (ValueError, AttributeError) as e:
        logger.error(f"Failed to calculate SLA for {alarm_id}: {e}")
        time_elapsed = 0
        time_remaining = sla_seconds

    result["sla_deadline"] = sla_deadline_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(sla_deadline_dt, datetime) else ""
    result["time_remaining"] = round(time_remaining, 1)
    result["escalate_to"] = sla_role

    # Check if SLA is breached
    if time_elapsed >= sla_seconds:
        result["checklist"]["sla_timer_check"] = True
        result["should_escalate"] = True
        result["reason"] = (
            f"SLA breached: {severity} alarm unresolved after "
            f"{_format_duration(time_elapsed)} (SLA: {_format_duration(sla_seconds)}). "
            f"Escalating to {sla_role}."
        )
    else:
        result["checklist"]["sla_timer_check"] = False
        result["should_escalate"] = False
        result["reason"] = (
            f"SLA not yet breached: {_format_duration(time_elapsed)} elapsed, "
            f"{_format_duration(time_remaining)} remaining before escalation."
        )

    return result


def _is_in_maintenance(node_name: str, db_path: str) -> bool:
    """
    Check if a node is currently in a planned maintenance window.
    Queries the database for active maintenance windows covering this node.
    """
    if not node_name:
        return False
    try:
        from backend.database import is_in_maintenance_window
        return is_in_maintenance_window(node_name, db_path=db_path)
    except (ImportError, Exception) as e:
        logger.debug(f"Cannot check maintenance window: {e}")
        return False


def _is_transient(alarm_id: str, db_path: str) -> bool:
    """
    Check if an alarm is known to be transient (self-cleared under 60 seconds).
    Queries the transient_alarms table.
    """
    if not alarm_id:
        return False
    try:
        from backend.database import is_transient_alarm
        return is_transient_alarm(alarm_id, db_path=db_path)
    except (ImportError, Exception) as e:
        logger.debug(f"Cannot check transient status: {e}")
        return False


def _check_p1_confirmation(alarm_id: str, node_name: str, db_path: str) -> bool:
    """
    Check if P1 is confirmed: require 2 similar alarms within 5 minutes.
    Queries the database for recent incidents on the same node.
    """
    if not node_name:
        return False

    try:
        from backend.database import list_incidents
        cutoff = (datetime.utcnow() - timedelta(seconds=P1_CONFIRMATION_WINDOW)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        # Get recent open incidents on the same node
        recent = list_incidents(
            node_name=node_name,
            limit=P1_CONFIRMATION_COUNT + 1,
            db_path=db_path,
        )

        # Count incidents within confirmation window (excluding current)
        count = 0
        for inc in recent:
            if inc["alarm_id"] == alarm_id:
                continue  # Skip the current alarm itself
            try:
                inc_time = inc.get("created_at", "")
                if inc_time >= cutoff:
                    count += 1
            except (ValueError, TypeError):
                continue

        logger.info(f"P1 confirmation: found {count} recent alarms for {node_name}")
        return count >= (P1_CONFIRMATION_COUNT - 1)  # Need N-1 prior alarms

    except (ImportError, Exception) as e:
        logger.warning(f"Cannot check P1 confirmation: {e}")
        return False  # Fail safe - don't auto-escalate if can't verify


def get_escalation_queue(db_path: str = "/data/telenoc.db") -> List[Dict[str, Any]]:
    """
    Get the current escalation queue: all pending escalations sorted by urgency.
    
    Returns list of escalation items with incident details and time remaining.
    """
    try:
        from backend.database import get_pending_escalations, DB_PATH
        db_path = db_path or DB_PATH

        pending = get_pending_escalations(db_path=db_path)
        now = datetime.utcnow()

        queue = []
        for escalation in pending:
            try:
                deadline = datetime.fromisoformat(
                    escalation["sla_deadline"].replace("Z", "+00:00")
                )
                time_remaining = (deadline - now).total_seconds()
            except (ValueError, AttributeError):
                time_remaining = 0

            queue.append({
                "escalation_id": escalation["id"],
                "incident_id": escalation["incident_id"],
                "alarm_id": escalation["alarm_id"],
                "escalated_to": escalation["escalated_to"],
                "escalated_at": escalation["escalated_at"],
                "sla_deadline": escalation["sla_deadline"],
                "time_remaining_seconds": round(time_remaining, 1),
                "time_remaining_formatted": _format_duration(time_remaining) if time_remaining > 0 else "OVERDUE",
                "status": escalation["status"],
                "reason": escalation.get("reason", ""),
            })

        # Sort by time remaining (most urgent first)
        queue.sort(key=lambda x: x["time_remaining_seconds"])
        return queue

    except (ImportError, Exception) as e:
        logger.error(f"Error getting escalation queue: {e}")
        return []


def get_escalation_summary(db_path: str = "/data/telenoc.db") -> Dict[str, Any]:
    """
    Get a summary of the current escalation state for dashboard display.
    """
    queue = get_escalation_queue(db_path)

    n_pending = sum(1 for e in queue if e["status"] == "pending")
    n_overdue = sum(1 for e in queue if e["time_remaining_seconds"] <= 0 and e["status"] == "pending")
    n_acknowledged = sum(1 for e in queue if e["status"] == "acknowledged")

    return {
        "total_in_queue": len(queue),
        "pending": n_pending,
        "overdue": n_overdue,
        "acknowledged": n_acknowledged,
        "queue": queue[:20],  # Return top 20 most urgent
    }


def _format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.
    E.g., 3661 → "1h 1m 1s"
    """
    if seconds <= 0:
        return "0s"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)