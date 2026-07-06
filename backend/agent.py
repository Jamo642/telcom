"""
Master Diagnosis Agent for TeleNOC AI

Orchestrates the full alarm diagnosis pipeline:
1. Receive raw alarm → check maintenance/transient filters
2. Classify severity (severity.py) via LLM + rule-based fallback
3. Correlate with recent alarms (correlator.py)
4. Start MTTR timer (mttr.py)
5. Detect degradation trends (trends.py)
6. Check escalation SLA (escalation.py)
7. Return structured JSON diagnosis

Supports English and Swahili via Accept-Language header.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)

# Swahili translations for NOC operations
SWAHILI_TRANSLATIONS = {
    "P1": "Muhimu (P1)",
    "P2": "Kubwa (P2)",
    "P3": "Wastani (P3)",
    "P4": "Onyo (P4)",
    "severity": "Ukali",
    "root_cause": "Chanzo cha Tatizo",
    "recommended_action": "Hatua Inayopendekezwa",
    "relevant_runbook": "Mwongozo husika",
    "escalate_to": "Peleka kwa",
    "respond_within": "Jibu ndani ya",
    "confidence": "Uhakika",
    "node_name": "Jina la Nodi",
    "alarm_type": "Aina ya Tahadhari",
    "maintenance_mode": "Nodi iko kwenye matengenezo",
    "transient_alarm": "Tahadhari ya muda mfupi",
    "NOC Lead": "Kiongozi wa NOC",
    "NOC Supervisor": "Msimamizi wa NOC",
    "Network Engineer": "Mhandisi wa Mtandao",
    "Junior Engineer": "Mhandisi Mganga",
}

SUPPORTED_LANGUAGES = {"en", "sw"}


class Language(Enum):
    ENGLISH = "en"
    SWAHILI = "sw"


def diagnose_alarm(
    alarm: Dict[str, Any],
    recent_alarms: Optional[List[Dict[str, Any]]] = None,
    language: str = "en",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Master diagnosis pipeline for a single alarm.
    
    Args:
        alarm: Dict with keys: alarm_id, alarm_text, node_name, alarm_type, timestamp
        recent_alarms: Optional list of recent alarms for correlation
        language: Language code ('en' or 'sw')
        db_path: Path to SQLite database
    
    Returns:
        Structured JSON diagnosis matching the spec:
        {
            "alarm_id": str,
            "severity": "P1"|"P2"|"P3"|"P4",
            "confidence": float,
            "root_cause": str,
            "recommended_action": str,
            "relevant_runbook": str,
            "escalate_to": str,
            "respond_within": str,
            "mttr_started_at": str,
            "needs_review": bool,
            "filtered": bool,
            "filter_reason": str
        }
    """
    try:
        from backend.database import DB_PATH as DEFAULT_DB_PATH
    except Exception:
        DEFAULT_DB_PATH = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db")

    db_path = db_path or os.environ.get("TELENOC_DB_PATH", DEFAULT_DB_PATH)

    try:
        from backend.database import init_db

        init_db(db_path=db_path)
    except Exception as exc:
        logger.warning("Database initialization check failed: %s", exc)

    alarm_id = alarm.get("alarm_id", "ALM-UNKNOWN")
    alarm_text = alarm.get("alarm_text", "")
    node_name = alarm.get("node_name", "")
    alarm_type = alarm.get("alarm_type", "")
    timestamp = alarm.get("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))

    logger.info(f"Diagnosing alarm {alarm_id} | Node: {node_name} | Type: {alarm_type}")

    # Normalize language
    lang = language if language in SUPPORTED_LANGUAGES else "en"

    # Initialize result with defaults
    result = {
        "alarm_id": alarm_id,
        "alarm_name": alarm.get("alarm_name", ""),
        "severity": "P4",
        "confidence": 0.0,
        "root_cause": "",
        "recommended_action": "",
        "relevant_runbook": "",
        "escalate_to": "",
        "respond_within": "",
        "mttr_started_at": "",
        "needs_review": False,
        "filtered": False,
        "filter_reason": "",
        "correlation_group": None,
        "trend_alert": None,
        "escalation": None,
    }

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Pre-filtering
    # ═══════════════════════════════════════════════════════════════════

    # 1a. Check maintenance window
    try:
        from backend.database import is_in_maintenance_window
        if is_in_maintenance_window(node_name, timestamp, db_path=db_path):
            result["filtered"] = True
            result["filter_reason"] = f"Node {node_name} is in planned maintenance window"
            result["severity"] = "P4"
            logger.info(f"Alarm {alarm_id} filtered: maintenance window")
            return _finalize(result, lang)
    except ImportError:
        pass

    # 1b. Check transient alarm (if already seen)
    try:
        from backend.database import is_transient_alarm
        if is_transient_alarm(alarm_id, db_path=db_path):
            result["filtered"] = True
            result["filter_reason"] = f"Alarm {alarm_id} previously identified as transient"
            result["severity"] = "P4"
            logger.info(f"Alarm {alarm_id} filtered: transient")
            return _finalize(result, lang)
    except ImportError:
        pass

    # Record this alarm for transient tracking
    try:
        from backend.database import record_transient_alarm
        record_transient_alarm(alarm_id, node_name, alarm_type, db_path=db_path)
    except ImportError:
        pass

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Severity Classification
    # ═══════════════════════════════════════════════════════════════════

    try:
        from backend.severity import classify_severity
        severity_result = classify_severity(
            alarm_text=alarm_text,
            alarm_type=alarm_type,
            node_name=node_name,
            recent_alarms=recent_alarms,
        )

        result["severity"] = severity_result.get("severity", "P4")
        result["confidence"] = severity_result.get("confidence", 0.0)
        result["root_cause"] = severity_result.get("root_cause", "")
        result["recommended_action"] = severity_result.get("recommended_action", "")
        result["relevant_runbook"] = severity_result.get("relevant_runbook", "")
        result["escalate_to"] = severity_result.get("escalate_to", "")
        result["respond_within"] = severity_result.get("respond_within", "")
        result["needs_review"] = severity_result.get("needs_review", False)
    except Exception as e:
        logger.error(f"Severity classification failed for {alarm_id}: {e}")
        result["severity"] = "P3"
        result["confidence"] = 0.3
        result["root_cause"] = "Classification error - manual review needed"
        result["needs_review"] = True

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Start MTTR Timer
    # ═══════════════════════════════════════════════════════════════════

    try:
        from backend.mttr import start_mttr_timer
        result["mttr_started_at"] = start_mttr_timer(alarm_id)
    except Exception as e:
        logger.warning(f"MTTR timer start failed for {alarm_id}: {e}")
        result["mttr_started_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Alarm Correlation (if recent alarms available)
    # ═══════════════════════════════════════════════════════════════════

    if recent_alarms and isinstance(recent_alarms, list) and len(recent_alarms) > 0:
        try:
            from backend.correlator import correlate_alarms, find_related_alarms

            # Combine current alarm with recent ones for correlation
            all_alarms = recent_alarms + [{
                "alarm_id": alarm_id,
                "alarm_text": alarm_text,
                "node_name": node_name,
                "alarm_type": alarm_type,
                "timestamp": timestamp,
                "severity": result["severity"],
            }]

            correlation_groups = correlate_alarms(all_alarms)
            related_group = find_related_alarms(alarm_id, correlation_groups)

            if related_group:
                result["correlation_group"] = {
                    "group_id": related_group.get("group_id"),
                    "confidence": related_group.get("confidence"),
                    "alarm_count": related_group.get("alarm_count"),
                    "nodes": related_group.get("nodes"),
                    "suggested_root_cause": related_group.get("suggested_root_cause"),
                    "time_range": related_group.get("time_range"),
                }

                # If correlation suggests a different root cause, update it
                if related_group.get("suggested_root_cause"):
                    result["root_cause"] = (
                        f"{result['root_cause']} | "
                        f"Correlated: {related_group['suggested_root_cause']}"
                    )
        except Exception as e:
            logger.warning(f"Correlation failed for {alarm_id}: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 5: Trend Detection
    # ═══════════════════════════════════════════════════════════════════

    try:
        from backend.trends import detect_trends
        trend_result = detect_trends(
            alarms=[{
                "node_name": node_name,
                "severity": result["severity"],
                "timestamp": timestamp,
                "alarm_type": alarm_type,
            }],
            db_path=db_path,
        )

        if trend_result.get("trend_alerts"):
            result["trend_alert"] = trend_result["trend_alerts"][0]
    except Exception as e:
        logger.warning(f"Trend detection failed for {alarm_id}: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 6: Escalation Check
    # ═══════════════════════════════════════════════════════════════════

    try:
        from backend.database import get_incident_by_alarm_id, log_incident
        # Log incident to database first
        try:
            incident = log_incident(
                alarm_id=alarm_id,
                alarm_name=alarm.get("alarm_name", ""),
                node_name=node_name,
                alarm_type=alarm_type,
                severity=result["severity"],
                confidence=result["confidence"],
                root_cause=result["root_cause"],
                recommended_action=result["recommended_action"],
                relevant_runbook=result["relevant_runbook"],
                escalate_to=result["escalate_to"],
                respond_within=result["respond_within"],
                raw_alarm_text=alarm_text,
                db_path=db_path,
            )
        except Exception:
            incident = get_incident_by_alarm_id(alarm_id, db_path=db_path)

        if not incident:
            result["escalation"] = {
                "should_escalate": False,
                "reason": "Incident persistence unavailable; escalation check skipped",
            }
            return _finalize(result, lang)

        # Check escalation
        from backend.escalation import check_escalation
        escalation_result = check_escalation(incident, db_path=db_path)
        result["escalation"] = escalation_result

        # If escalation needed, update escalate_to
        if escalation_result.get("should_escalate") and incident.get("id"):
            from backend.database import create_escalation
            create_escalation(
                incident_id=incident["id"],
                alarm_id=alarm_id,
                escalated_to=escalation_result["escalate_to"],
                sla_deadline=escalation_result["sla_deadline"],
                reason=escalation_result["reason"],
                db_path=db_path,
            )
            # Also update incident escalate_to
            from backend.database import update_incident
            update_incident(incident["id"], {
                "status": "escalated",
                "escalate_to": escalation_result["escalate_to"],
            }, db_path=db_path)
            result["escalate_to"] = escalation_result["escalate_to"]

    except Exception as e:
        logger.warning(f"Escalation check failed for {alarm_id}: {e}")

    # ═══════════════════════════════════════════════════════════════════
    # STEP 7: Low Confidence Audit
    # ═══════════════════════════════════════════════════════════════════

    if result["needs_review"]:
        try:
            from backend.database import log_confidence_audit
            log_confidence_audit(
                alarm_id=alarm_id,
                confidence=result["confidence"],
                decision="flag_for_review",
                reason=f"Low confidence ({result['confidence']:.2f}) or P1 unconfirmed",
                db_path=db_path,
            )
        except Exception as e:
            logger.warning(f"Confidence audit failed for {alarm_id}: {e}")

    return _finalize(result, lang)


def _finalize(result: Dict[str, Any], language: str) -> Dict[str, Any]:
    """
    Finalize the diagnosis result.
    If language is Swahili, translate relevant fields.
    Remove internal fields and ensure spec-compliant output.
    """
    if language == "sw":
        result = _translate_to_swahili(result)

    # Ensure all required fields are present
    result.setdefault("escalation", None)
    result.setdefault("correlation_group", None)
    result.setdefault("trend_alert", None)

    # Add formatted response fields
    result["mttr_started_at"] = result.get("mttr_started_at", "")
    result["respond_within"] = result.get("respond_within", "4 hours")
    result["escalate_to"] = result.get("escalate_to", "Network Engineer")
    result["relevant_runbook"] = result.get("relevant_runbook", "NOC-SOP-GEN-001")

    return result


def _translate_to_swahili(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate key fields to Swahili.
    """
    sw = SWAHILI_TRANSLATIONS

    # Translate severity
    if result["severity"] in sw:
        result["severity_display"] = sw[result["severity"]]

    # Translate escalation target
    if result.get("escalate_to") in sw:
        result["escalate_to"] = sw[result["escalate_to"]]

    # Add Swahili field labels
    result["_labels"] = {
        "severity": sw["severity"],
        "root_cause": sw["root_cause"],
        "recommended_action": sw["recommended_action"],
        "confidence": sw["confidence"],
        "escalate_to": sw["escalate_to"],
        "respond_within": sw["respond_within"],
    }

    return result


def diagnose_batch(
    alarms: List[Dict[str, Any]],
    language: str = "en",
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Diagnose multiple alarms in batch.
    
    Args:
        alarms: List of alarm dicts to diagnose
        language: Language code ('en' or 'sw')
        db_path: Path to SQLite database
    
    Returns:
        List of structured diagnosis results
    """
    try:
        from backend.database import DB_PATH as DEFAULT_DB_PATH
    except Exception:
        DEFAULT_DB_PATH = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db")

    db_path = db_path or os.environ.get("TELENOC_DB_PATH", DEFAULT_DB_PATH)

    logger.info(f"Batch diagnosing {len(alarms)} alarms")

    results = []
    all_alarms_for_correlation = list(alarms)  # All alarms for cross-correlation

    for i, alarm in enumerate(alarms):
        # For each alarm, use other alarms as context for correlation
        other_alarms = [a for j, a in enumerate(alarms) if j != i]
        result = diagnose_alarm(
            alarm=alarm,
            recent_alarms=other_alarms,
            language=language,
            db_path=db_path,
        )
        results.append(result)

    return results