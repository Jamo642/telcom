"""
MTTR (Mean Time To Repair) Tracker for TeleNOC AI

Tracks alarm resolution times and computes:
- Per-node MTTR statistics (mean, median, p90, p95)
- Per-severity MTTR statistics
- Rolling MTTR over configurable time windows (last 24h, 7d, 30d)
- MTTR trend analysis (increasing/decreasing/stable)

Stores data in SQLite via database.py module.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from statistics import mean, median

logger = logging.getLogger(__name__)

# Default MTTR targets per severity (seconds)
MTTR_TARGETS = {
    "P1": 900,    # 15 minutes
    "P2": 1800,   # 30 minutes
    "P3": 7200,   # 2 hours
    "P4": 28800,  # 8 hours
}


def start_mttr_timer(alarm_id: str) -> str:
    """
    Start the MTTR timer for an alarm.
    Returns the ISO 8601 timestamp of when tracking started.
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info(f"MTTR timer started for {alarm_id} at {now}")
    return now


def stop_mttr_timer(alarm_id: str, started_at: str) -> Dict[str, Any]:
    """
    Stop the MTTR timer and record resolution time.
    
    Args:
        alarm_id: The alarm identifier
        started_at: ISO 8601 timestamp when MTTR tracking started
    
    Returns:
        Dict with alarm_id, mttr_seconds, status (on_target/missed), and severity comparison
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # Calculate elapsed seconds
    try:
        start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(now.replace("Z", "+00:00"))
        mttr_seconds = (end_time - start_time).total_seconds()
    except (ValueError, AttributeError) as e:
        logger.error(f"Failed to calculate MTTR for {alarm_id}: {e}")
        mttr_seconds = 0.0

    result = {
        "alarm_id": alarm_id,
        "mttr_started_at": started_at,
        "mttr_resolved_at": now,
        "mttr_seconds": round(mttr_seconds, 1),
    }

    logger.info(f"MTTR for {alarm_id}: {mttr_seconds:.0f}s")
    return result


def get_mttr_report(
    node_name: Optional[str] = None,
    severity: Optional[str] = None,
    hours: int = 24,
    db_path: str = "/data/telenoc.db",
) -> Dict[str, Any]:
    """
    Get MTTR report for a time window.
    
    Args:
        node_name: Optional filter by node name
        severity: Optional filter by severity (P1/P2/P3/P4)
        hours: Lookback window in hours
        db_path: Path to SQLite database
    
    Returns:
        Dict with overall_mttr, per_node, per_severity, targets, trends
    """
    from backend.database import get_db, DB_PATH
    import sqlite3

    db_path = db_path or DB_PATH
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build query conditions
    conditions = ["mttr_resolved_at IS NOT NULL", "mttr_started_at >= ?"]
    params = [cutoff]

    if node_name:
        conditions.append("node_name = ?")
        params.append(node_name)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)

    where_clause = " AND ".join(conditions)

    with get_db(db_path) as conn:
        # Get all resolved incidents for calculation
        rows = conn.execute(
            f"""SELECT node_name, severity, mttr_seconds, mttr_started_at, mttr_resolved_at
                FROM incidents WHERE {where_clause} ORDER BY mttr_started_at ASC""",
            params,
        ).fetchall()

    incidents = [dict(row) for row in rows]
    n_incidents = len(incidents)

    if n_incidents == 0:
        return {
            "overall_mttr": 0,
            "n_incidents": 0,
            "per_node": {},
            "per_severity": {},
            "targets": MTTR_TARGETS,
            "status": "no_data",
            "hours_analyzed": hours,
        }

    # Calculate overall MTTR
    mttr_values = [i["mttr_seconds"] for i in incidents if i["mttr_seconds"] is not None]
    if not mttr_values:
        return {
            "overall_mttr": 0,
            "n_incidents": 0,
            "per_node": {},
            "per_severity": {},
            "targets": MTTR_TARGETS,
            "status": "no_data",
            "hours_analyzed": hours,
        }

    overall_mean = mean(mttr_values)
    overall_median = median(mttr_values)
    overall_p90 = _percentile(mttr_values, 90)
    overall_p95 = _percentile(mttr_values, 95)

    # Per-node breakdown
    node_stats = {}
    for incident in incidents:
        node = incident["node_name"] or "unknown"
        mttr_val = incident["mttr_seconds"]
        if node not in node_stats:
            node_stats[node] = {"values": [], "count": 0}
        if mttr_val is not None:
            node_stats[node]["values"].append(mttr_val)
        node_stats[node]["count"] += 1

    per_node = {}
    for node, stats in node_stats.items():
        vals = stats["values"]
        per_node[node] = {
            "mean_mttr": round(mean(vals), 1) if vals else 0,
            "median_mttr": round(median(vals), 1) if vals else 0,
            "p90_mttr": round(_percentile(vals, 90), 1) if vals else 0,
            "count": stats["count"],
        }

    # Per-severity breakdown
    severity_stats = {}
    for incident in incidents:
        sev = incident["severity"] or "P4"
        mttr_val = incident["mttr_seconds"]
        if sev not in severity_stats:
            severity_stats[sev] = {"values": [], "count": 0, "on_target": 0, "missed": 0}
        if mttr_val is not None:
            severity_stats[sev]["values"].append(mttr_val)
            target = MTTR_TARGETS.get(sev, float("inf"))
            if mttr_val <= target:
                severity_stats[sev]["on_target"] += 1
            else:
                severity_stats[sev]["missed"] += 1
        severity_stats[sev]["count"] += 1

    per_severity = {}
    for sev, stats in severity_stats.items():
        vals = stats["values"]
        total = stats["on_target"] + stats["missed"]
        per_severity[sev] = {
            "mean_mttr": round(mean(vals), 1) if vals else 0,
            "median_mttr": round(median(vals), 1) if vals else 0,
            "p90_mttr": round(_percentile(vals, 90), 1) if vals else 0,
            "count": stats["count"],
            "on_target": stats["on_target"],
            "missed": stats["missed"],
            "sla_compliance_pct": round(stats["on_target"] / total * 100, 1) if total > 0 else 0,
            "target_seconds": MTTR_TARGETS.get(sev, 0),
        }

    # Trend direction
    trend = _calculate_mttr_trend(mttr_values, n_incidents)

    return {
        "overall_mttr": {
            "mean": round(overall_mean, 1),
            "median": round(overall_median, 1),
            "p90": round(overall_p90, 1),
            "p95": round(overall_p95, 1),
        },
        "n_incidents": n_incidents,
        "per_node": per_node,
        "per_severity": per_severity,
        "targets": MTTR_TARGETS,
        "trend": trend,
        "status": "healthy" if overall_mean <= 300 else "warning" if overall_mean <= 600 else "critical",
        "hours_analyzed": hours,
    }


def _percentile(values: List[float], percentile: int) -> float:
    """
    Calculate percentile value from a sorted list.
    Uses linear interpolation between closest ranks.
    """
    if not values:
        return 0.0
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    
    if percentile <= 0:
        return sorted_vals[0]
    if percentile >= 100:
        return sorted_vals[-1]
    
    # Calculate rank using the C=0 method
    rank = (percentile / 100.0) * (n - 1)
    lower = int(rank)
    upper = lower + 1 if lower + 1 < n else lower
    weight = rank - lower
    
    return sorted_vals[lower] * (1 - weight) + sorted_vals[upper] * weight


def _calculate_mttr_trend(
    mttr_values: List[float],
    n_incidents: int,
) -> Dict[str, Any]:
    """
    Calculate MTTR trend direction.
    Splits data into two halves and compares means.
    
    Returns:
        Dict with direction (improving/stable/degrading), change_pct, recommendation
    """
    if n_incidents < 4:
        return {
            "direction": "stable",
            "change_pct": 0,
            "recommendation": "Insufficient data for trend analysis",
        }

    midpoint = len(mttr_values) // 2
    first_half = mttr_values[:midpoint]
    second_half = mttr_values[midpoint:]

    if not first_half or not second_half:
        return {"direction": "stable", "change_pct": 0, "recommendation": ""}

    first_mean = mean(first_half)
    second_mean = mean(second_half)

    if first_mean == 0:
        return {"direction": "stable", "change_pct": 0, "recommendation": ""}

    change_pct = ((second_mean - first_mean) / first_mean) * 100

    if change_pct < -10:
        direction = "improving"
        recommendation = "MTTR is decreasing - good trend"
    elif change_pct > 10:
        direction = "degrading"
        recommendation = "MTTR is increasing - investigate root causes"
    else:
        direction = "stable"
        recommendation = "MTTR is within normal range"

    return {
        "direction": direction,
        "change_pct": round(change_pct, 1),
        "recommendation": recommendation,
    }


def get_current_mttr(
    node_name: Optional[str] = None,
    db_path: str = "/data/telenoc.db",
) -> Dict[str, Any]:
    """
    Get current MTTR summary (last 24 hours by default).
    Lightweight version of get_mttr_report for dashboard use.
    """
    return get_mttr_report(node_name=node_name, hours=24, db_path=db_path)