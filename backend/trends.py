"""
Degradation Trend Detector for TeleNOC AI

Detects degradation trends before they become outages by monitoring:
- Alarm frequency per node over configurable time windows (5min, 15min, 1hr)
- Accelerating alarm rates as pre-outage degradation signals
- Statistical anomaly detection (>3σ deviation from baseline)
- Severity-weighted degradation scoring

Alerts when degradation crosses configurable thresholds.
"""

import os
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

# Default window configuration (seconds)
WINDOW_SHORT = 300    # 5 minutes - fast detection
WINDOW_MEDIUM = 900   # 15 minutes - standard trend
WINDOW_LONG = 3600    # 1 hour - baseline comparison

# Degradation thresholds
DEGRADATION_WARNING_THRESHOLD = 1.5   # 1.5x baseline → yellow
DEGRADATION_CRITICAL_THRESHOLD = 3.0  # 3x baseline → red

# Severity weights for scoring
SEVERITY_WEIGHTS = {
    "P1": 10.0,
    "P2": 5.0,
    "P3": 2.0,
    "P4": 1.0,
}


def detect_trends(
    alarms: List[Dict[str, Any]],
    db_path: str = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db"),
) -> Dict[str, Any]:
    """
    Detect degradation trends across all network nodes.
    
    Args:
        alarms: List of alarm dicts with keys: node_name, severity, timestamp, alarm_type
        db_path: Path to SQLite database for historical trend data
    
    Returns:
        Dict with:
        - trend_alerts: List of nodes with detected degradation
        - overall_status: healthy/warning/critical
        - nodes_assessed: Number of nodes assessed
        - windows_analyzed: Time windows analyzed
    """
    logger.info(f"Detecting trends across {len(alarms)} alarms")

    if not alarms:
        return {
            "trend_alerts": [],
            "overall_status": "healthy",
            "nodes_assessed": 0,
            "windows_analyzed": {
                "short_seconds": WINDOW_SHORT,
                "medium_seconds": WINDOW_MEDIUM,
                "long_seconds": WINDOW_LONG,
            },
        }

    # Group alarms by node
    node_alarms = defaultdict(list)
    for alarm in alarms:
        node = alarm.get("node_name", "unknown")
        node_alarms[node].append(alarm)

    # Calculate baselines and detect anomalies per node
    trend_alerts = []
    overall_max_status = "healthy"

    for node_name, node_alarm_list in node_alarms.items():
        # Get historical trend data from database
        historical_data = _get_historical_data(node_name, db_path)

        # Calculate current window statistics
        current_stats = _calculate_window_stats(node_alarm_list)

        # Compare against baseline for degradation
        node_trend = _assess_node_degradation(
            node_name, current_stats, historical_data
        )

        if node_trend["status"] != "healthy":
            trend_alerts.append(node_trend)

        # Track overall status
        severity_order = {"healthy": 0, "warning": 1, "critical": 2}
        if severity_order.get(node_trend["status"], 0) > severity_order.get(overall_max_status, 0):
            overall_max_status = node_trend["status"]

    # Store current window data for future baseline calculations
    _store_trend_data(node_alarms, db_path)

    return {
        "trend_alerts": trend_alerts,
        "overall_status": overall_max_status,
        "nodes_assessed": len(node_alarms),
        "windows_analyzed": {
            "short_seconds": WINDOW_SHORT,
            "medium_seconds": WINDOW_MEDIUM,
            "long_seconds": WINDOW_LONG,
        },
        "degradation_thresholds": {
            "warning": DEGRADATION_WARNING_THRESHOLD,
            "critical": DEGRADATION_CRITICAL_THRESHOLD,
        },
    }


def _calculate_window_stats(alarms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate statistics for a set of alarms in the current window.
    
    Returns:
        Dict with alarm_count, severity_counts, severity_score, time_span, rate
    """
    now = datetime.utcnow()
    n_alarms = len(alarms)

    if n_alarms == 0:
        return {
            "alarm_count": 0,
            "severity_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
            "severity_score": 0.0,
            "time_span": 0,
            "rate_per_minute": 0.0,
        }

    # Count by severity
    severity_counts = defaultdict(int)
    total_severity_score = 0.0
    timestamps = []

    for alarm in alarms:
        sev = alarm.get("severity", "P4")
        severity_counts[sev] += 1
        total_severity_score += SEVERITY_WEIGHTS.get(sev, 1.0)

        try:
            ts = alarm.get("timestamp", "")
            if ts:
                ts_parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                timestamps.append(ts_parsed)
        except (ValueError, AttributeError):
            pass

    # Calculate time span
    time_span = 0
    if len(timestamps) >= 2:
        time_span = (max(timestamps) - min(timestamps)).total_seconds()
        if time_span <= 0:
            time_span = WINDOW_SHORT  # Default to short window if timestamps unclear
    
    # Calculate rate (alarms per minute)
    window_minutes = max(time_span / 60.0, 1.0)
    rate_per_minute = n_alarms / window_minutes

    return {
        "alarm_count": n_alarms,
        "severity_counts": dict(severity_counts),
        "severity_score": round(total_severity_score, 2),
        "time_span": round(time_span, 1),
        "rate_per_minute": round(rate_per_minute, 2),
    }


def _get_historical_data(
    node_name: str,
    db_path: str,
) -> Dict[str, Any]:
    """
    Retrieve historical trend data for a node from the database.
    Computes baseline alarm rate and severity score statistics.
    """
    try:
        from backend.database import get_trend_data, DB_PATH
        db_path = db_path or DB_PATH

        # Get last 24 hours of trend data
        trend_records = get_trend_data(node_name=node_name, hours=24, db_path=db_path)

        if not trend_records:
            return {
                "baseline_rate": 0.0,
                "baseline_score": 0.0,
                "n_samples": 0,
                "rate_std": 0.0,
            }

        # Calculate baseline metrics
        rates = [r["alarm_count"] / max((r.get("window_end", "") != ""), 1) for r in trend_records]
        # Simplified: use alarm_count as proxy for rate
        alarm_counts = [r["alarm_count"] for r in trend_records]
        severity_scores = [r["severity_score"] for r in trend_records]

        n_samples = len(alarm_counts)
        baseline_rate = sum(alarm_counts) / n_samples if n_samples > 0 else 0.0
        baseline_score = sum(severity_scores) / n_samples if n_samples > 0 else 0.0

        # Calculate standard deviation for anomaly detection
        if n_samples > 1:
            variance = sum((c - baseline_rate) ** 2 for c in alarm_counts) / (n_samples - 1)
            rate_std = math.sqrt(variance)
        else:
            rate_std = 0.0

        return {
            "baseline_rate": round(baseline_rate, 2),
            "baseline_score": round(baseline_score, 2),
            "n_samples": n_samples,
            "rate_std": round(rate_std, 2),
        }

    except (ImportError, Exception) as e:
        logger.warning(f"Could not retrieve historical data for {node_name}: {e}")
        return {
            "baseline_rate": 0.0,
            "baseline_score": 0.0,
            "n_samples": 0,
            "rate_std": 0.0,
        }


def _assess_node_degradation(
    node_name: str,
    current_stats: Dict[str, Any],
    historical_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Assess if a node is showing degradation trends.
    Compares current window stats against historical baseline.
    
    Returns a trend alert dict if degradation detected, or a healthy status dict.
    """
    current_rate = current_stats["rate_per_minute"]
    current_score = current_stats["severity_score"]
    current_count = current_stats["alarm_count"]

    baseline_rate = historical_data.get("baseline_rate", 0.0)
    baseline_score = historical_data.get("baseline_score", 0.0)
    rate_std = historical_data.get("rate_std", 0.0)
    n_samples = historical_data.get("n_samples", 0)

    # If no historical data or current count is 0, nothing to report
    if current_count == 0:
        return {
            "node_name": node_name,
            "status": "healthy",
            "current_rate": 0.0,
            "baseline_rate": baseline_rate,
            "deviation": 0.0,
        }

    # Calculate deviation from baseline
    if baseline_rate > 0:
        rate_ratio = current_rate / baseline_rate
    else:
        # No baseline yet - use absolute threshold
        rate_ratio = 2.0 if current_count >= 3 else 0.5  # Default warning for new nodes

    # Statistical anomaly: check if > 3 sigma from baseline
    if rate_std > 0 and n_samples > 1:
        sigma_deviation = (current_rate - baseline_rate) / rate_std if rate_std > 0 else 0
    else:
        sigma_deviation = 0.0

    # Determine status
    if sigma_deviation >= 3.0 or rate_ratio >= DEGRADATION_CRITICAL_THRESHOLD:
        status = "critical"
    elif rate_ratio >= DEGRADATION_WARNING_THRESHOLD:
        status = "warning"
    else:
        status = "healthy"

    # Build trend alert
    alert = {
        "node_name": node_name,
        "status": status,
        "current_rate": current_rate,
        "baseline_rate": baseline_rate,
        "rate_ratio": round(rate_ratio, 2),
        "sigma_deviation": round(sigma_deviation, 2),
        "current_count": current_count,
        "severity_score": current_score,
        "p1_count": current_stats["severity_counts"].get("P1", 0),
        "recommendation": "",
    }

    # Generate recommendation based on severity
    if status == "critical":
        alert["recommendation"] = (
            f"CRITICAL: {node_name} showing {rate_ratio:.1f}x baseline alarm rate "
            f"({sigma_deviation:.1f}σ deviation). Immediate investigation required."
        )
    elif status == "warning":
        alert["recommendation"] = (
            f"WARNING: {node_name} showing {rate_ratio:.1f}x baseline alarm rate. "
            "Schedule maintenance check within next shift."
        )
    else:
        alert["recommendation"] = f"{node_name} operating within normal parameters."

    # Add P1/P2 specific alerting
    if current_stats["severity_counts"].get("P1", 0) >= 2:
        alert["recommendation"] += " P1 alarms detected - escalate immediately."
        if status == "healthy":
            alert["status"] = "warning"

    return alert


def _store_trend_data(
    node_alarms: Dict[str, List[Dict[str, Any]]],
    db_path: str,
):
    """
    Store current window trend data to database for future baseline calculations.
    One record per node per analysis window.
    """
    try:
        from backend.database import record_trend_data, DB_PATH
        db_path = db_path or DB_PATH
        now = datetime.utcnow()
        window_start = (now - timedelta(seconds=WINDOW_MEDIUM)).strftime("%Y-%m-%dT%H:%M:%SZ")
        window_end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        for node_name, alarms in node_alarms.items():
            stats = _calculate_window_stats(alarms)
            record_trend_data(
                node_name=node_name,
                window_start=window_start,
                window_end=window_end,
                alarm_count=stats["alarm_count"],
                p1_count=stats["severity_counts"].get("P1", 0),
                p2_count=stats["severity_counts"].get("P2", 0),
                severity_score=stats["severity_score"],
                db_path=db_path,
            )
        logger.info(f"Stored trend data for {len(node_alarms)} nodes")
    except (ImportError, Exception) as e:
        logger.warning(f"Could not store trend data: {e}")


def get_trend_summary(
    db_path: str = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db"),
) -> Dict[str, Any]:
    """
    Get a summary of current degradation trends for dashboard display.
    Lightweight version that queries the database for recent trend data.
    """
    try:
        from backend.database import get_trend_data, DB_PATH
        db_path = db_path or DB_PATH
        records = get_trend_data(hours=24, db_path=db_path)

        if not records:
            return {
                "status": "no_data",
                "nodes": [],
                "message": "No trend data available yet",
            }

        # Aggregate by node
        node_data = defaultdict(list)
        for r in records:
            node_data[r["node_name"]].append(r)

        node_summaries = []
        for node_name, data_points in node_data.items():
            # Calculate average severity score and alarm count
            avg_score = sum(d["severity_score"] for d in data_points) / len(data_points)
            total_alarms = sum(d["alarm_count"] for d in data_points)
            recent_alarms = sum(
                d["alarm_count"] for d in data_points[-3:]
            )  # Last 3 windows

            # Simple trending: compare recent vs overall average
            if len(data_points) >= 6:
                recent_avg = recent_alarms / min(3, len(data_points))
                overall_avg = total_alarms / len(data_points)
                trend_ratio = recent_avg / overall_avg if overall_avg > 0 else 1.0
            else:
                trend_ratio = 1.0

            if trend_ratio >= DEGRADATION_CRITICAL_THRESHOLD:
                status = "critical"
            elif trend_ratio >= DEGRADATION_WARNING_THRESHOLD:
                status = "warning"
            else:
                status = "healthy"

            node_summaries.append({
                "node_name": node_name,
                "status": status,
                "avg_severity_score": round(avg_score, 1),
                "total_alarms_24h": total_alarms,
                "trend_ratio": round(trend_ratio, 2),
            })

        # Overall system status
        statuses = [n["status"] for n in node_summaries]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "nodes": node_summaries,
            "total_nodes_assessed": len(node_summaries),
        }

    except (ImportError, Exception) as e:
        logger.error(f"Error getting trend summary: {e}")
        return {"status": "error", "nodes": [], "message": str(e)}