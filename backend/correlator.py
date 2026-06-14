"""
Alarm Correlator for TeleNOC AI

Correlates related alarms into root cause clusters using:
- Time-window proximity (alarms within same window)
- Node affinity (same or adjacent network nodes)
- Semantic similarity (similar alarm text via vector embeddings)
- Confidence scoring for correlation quality

Outputs correlated alarm clusters with root cause probability.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

# Default correlation window (seconds)
CORRELATION_WINDOW_DEFAULT = 300  # 5 minutes
# Extended window for same-node correlations
SAME_NODE_WINDOW = 600  # 10 minutes
# Semantic similarity threshold
SIMILARITY_THRESHOLD = 0.70
# Minimum correlation confidence
MIN_CONFIDENCE = 0.50


def correlate_alarms(
    alarms: List[Dict[str, Any]],
    window_seconds: int = CORRELATION_WINDOW_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Correlate a list of alarms into root cause clusters.
    
    Args:
        alarms: List of alarm dicts with keys: alarm_id, alarm_text, node_name, timestamp, alarm_type
        window_seconds: Time window in seconds for grouping related alarms
    
    Returns:
        List of correlation groups, each with:
        - group_id: Unique correlation group ID
        - root_cause_probability: Confidence this represents a real root cause (0-1)
        - alarms: List of alarms in this group
        - nodes: Set of affected nodes
        - time_range: Start and end timestamps
        - suggested_root_cause: Best-guess root cause description
    """
    logger.info(f"Correlating {len(alarms)} alarms with {window_seconds}s window")

    if not alarms:
        return []

    # Sort alarms by timestamp
    sorted_alarms = sorted(alarms, key=lambda a: a.get("timestamp", ""))
    
    # Step 1: Time-based grouping
    time_groups = _group_by_time_window(sorted_alarms, window_seconds)
    logger.info(f"Time grouping produced {len(time_groups)} groups")

    # Step 2: Node-based sub-grouping within time groups
    node_groups = []
    for group in time_groups:
        subgroups = _group_by_node(group)
        node_groups.extend(subgroups)
    logger.info(f"Node grouping produced {len(node_groups)} groups")

    # Step 3: Semantic similarity scoring within node groups
    correlated_groups = []
    for group in node_groups:
        if len(group) >= 2:
            # Multiple alarms - do semantic correlation
            subgroups = _semantic_correlation(group)
            correlated_groups.extend(subgroups)
        else:
            # Single alarm - standalone group
            correlated_groups.append(group)

    # Step 4: Build output structure
    results = []
    for i, group in enumerate(correlated_groups):
        correlation = _build_correlation_group(group, i)
        if correlation["confidence"] >= MIN_CONFIDENCE:
            results.append(correlation)

    logger.info(f"Final correlation produced {len(results)} groups")
    return results


def _group_by_time_window(
    alarms: List[Dict[str, Any]],
    window_seconds: int,
) -> List[List[Dict[str, Any]]]:
    """
    Group alarms that fall within the same time window.
    Uses sliding window approach: alarms within window_seconds of each other.
    """
    if not alarms:
        return []

    groups = []
    current_group = [alarms[0]]

    for alarm in alarms[1:]:
        prev_time = _parse_timestamp(current_group[-1].get("timestamp", ""))
        curr_time = _parse_timestamp(alarm.get("timestamp", ""))

        if prev_time and curr_time and (curr_time - prev_time).total_seconds() <= window_seconds:
            current_group.append(alarm)
        else:
            if current_group:
                groups.append(current_group)
            current_group = [alarm]

    if current_group:
        groups.append(current_group)

    return groups


def _group_by_node(alarms: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Sub-group alarms by node name within a time group.
    Alarms from the same node (or related nodes) are grouped together.
    """
    node_map = defaultdict(list)

    for alarm in alarms:
        node = alarm.get("node_name", "unknown")
        node_map[node].append(alarm)

    return list(node_map.values())


def _semantic_correlation(alarms: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Correlate alarms within a node group using semantic text similarity.
    Uses embedding service if available, otherwise uses keyword overlap.
    Returns sub-groups of highly correlated alarms.
    """
    if len(alarms) <= 1:
        return [alarms]

    # Try to use embedding service for semantic similarity
    try:
        from services.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()
        has_embeddings = embedding_service is not None
    except (ImportError, Exception):
        has_embeddings = False

    n = len(alarms)
    adjacency = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            if has_embeddings:
                try:
                    similarity = embedding_service.similarity(
                        alarms[i].get("alarm_text", ""),
                        alarms[j].get("alarm_text", ""),
                    )
                except Exception:
                    similarity = _keyword_similarity(
                        alarms[i].get("alarm_text", ""),
                        alarms[j].get("alarm_text", ""),
                    )
            else:
                similarity = _keyword_similarity(
                    alarms[i].get("alarm_text", ""),
                    alarms[j].get("alarm_text", ""),
                )

            adjacency[i][j] = similarity
            adjacency[j][i] = similarity

    # Cluster using simple threshold-based grouping
    visited = set()
    groups = []

    for i in range(n):
        if i in visited:
            continue

        group = [i]
        visited.add(i)

        for j in range(i + 1, n):
            if j in visited:
                continue
            if adjacency[i][j] >= SIMILARITY_THRESHOLD:
                group.append(j)
                visited.add(j)

        groups.append([alarms[idx] for idx in group])

    return groups


def _keyword_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two alarm texts using keyword overlap.
    Fallback when embedding service is unavailable.
    Uses Jaccard similarity on token sets.
    """
    # Tokenize into words (lowercase, remove punctuation)
    import re
    tokens1 = set(re.findall(r'\w+', text1.lower()))
    tokens2 = set(re.findall(r'\w+', text2.lower()))

    if not tokens1 or not tokens2:
        return 0.0

    # Jaccard similarity
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    base_similarity = len(intersection) / len(union) if union else 0.0

    # Boost similarity for same alarm type
    type_keywords = {
        "bgp", "packet_loss", "interface", "power", "cpu", "memory", "dns", "link"
    }
    type_overlap = (tokens1 & type_keywords) & (tokens2 & type_keywords)
    type_boost = 0.15 if type_overlap else 0.0

    return min(base_similarity + type_boost, 1.0)


def _build_correlation_group(
    alarms: List[Dict[str, Any]],
    group_index: int,
) -> Dict[str, Any]:
    """
    Build a correlation group output structure with confidence scoring.
    """
    if not alarms:
        return {}

    group_id = f"CG-{group_index + 1:03d}"
    nodes = list(set(a.get("node_name", "unknown") for a in alarms))
    timestamps = [_parse_timestamp(a.get("timestamp", "")) for a in alarms if _parse_timestamp(a.get("timestamp", ""))]

    # Calculate time range
    time_start = min(timestamps).isoformat() + "Z" if timestamps else alarms[0].get("timestamp", "")
    time_end = max(timestamps).isoformat() + "Z" if timestamps else alarms[-1].get("timestamp", "")

    # Confidence scoring factors
    n_alarms = len(alarms)
    n_nodes = len(nodes)
    time_span = (max(timestamps) - min(timestamps)).total_seconds() if len(timestamps) >= 2 else 0

    # Factor 1: More alarms in group = higher confidence (up to 0.3)
    alarm_count_score = min(n_alarms * 0.05, 0.3)

    # Factor 2: Single node = higher confidence (same root cause) (up to 0.2)
    node_score = 0.2 if n_nodes == 1 else 0.1

    # Factor 3: Tight time window = higher confidence (up to 0.2)
    if time_span <= 60:
        time_score = 0.2
    elif time_span <= 300:
        time_score = 0.15
    elif time_span <= 600:
        time_score = 0.1
    else:
        time_score = 0.05

    # Factor 4: Base confidence (0.3)
    base_confidence = 0.3
    # Deduct for nodes that might be in maintenance
    maintenance_deduction = _check_maintenance_penalty(nodes)

    confidence = min(base_confidence + alarm_count_score + node_score + time_score - maintenance_deduction, 0.99)
    confidence = max(confidence, 0.1)

    # Determine suggested root cause
    suggested_root_cause = _suggest_root_cause(alarms)

    # Determine dominant severity for the group
    severity_counts = defaultdict(int)
    for a in alarms:
        severity_counts[a.get("severity", "P4")] += 1
    dominant_severity = max(severity_counts, key=severity_counts.get)

    return {
        "group_id": group_id,
        "confidence": round(confidence, 2),
        "alarm_count": n_alarms,
        "alarms": [
            {
                "alarm_id": a.get("alarm_id", ""),
                "node_name": a.get("node_name", ""),
                "severity": a.get("severity", "P4"),
                "timestamp": a.get("timestamp", ""),
                "alarm_type": a.get("alarm_type", ""),
            }
            for a in alarms
        ],
        "nodes": nodes,
        "dominant_severity": dominant_severity,
        "time_range": {
            "start": time_start,
            "end": time_end,
        },
        "suggested_root_cause": suggested_root_cause,
    }


def _suggest_root_cause(alarms: List[Dict[str, Any]]) -> str:
    """
    Suggest a root cause based on correlated alarm patterns.
    Uses alarm type frequency and known telecom failure patterns.
    """
    if not alarms:
        return "Unknown"

    # Count alarm types
    type_counts = defaultdict(int)
    for alarm in alarms:
        alarm_type = alarm.get("alarm_type", "").lower()
        alarm_text = alarm.get("alarm_text", "").lower()
        type_counts[alarm_type] += 1

        # Also check text for common patterns
        if "bgp" in alarm_text or "bgp" in alarm_type:
            type_counts["bgp"] += 1
        if "packet loss" in alarm_text:
            type_counts["packet_loss"] += 1
        if "interface" in alarm_text:
            type_counts["interface"] += 1
        if "power" in alarm_text:
            type_counts["power"] += 1

    # Find dominant type
    dominant = max(type_counts, key=type_counts.get) if type_counts else ""

    # Map to root cause descriptions
    root_cause_map = {
        "bgp": "BGP peering issue across multiple sessions",
        "packet_loss": "Network congestion or link degradation affecting multiple interfaces",
        "interface": "Interface hardware or configuration issue on core network node",
        "power": "Power supply or facility issue affecting network equipment",
        "cpu": "Resource exhaustion on network node due to traffic spike",
        "memory": "Memory leak or resource exhaustion on network node",
        "dns": "DNS infrastructure issue affecting name resolution",
        "link": "Physical layer or transport link degradation",
    }

    if dominant in root_cause_map:
        return root_cause_map[dominant]
    if "bgp" in type_counts:
        return root_cause_map["bgp"]
    if "packet_loss" in type_counts:
        return root_cause_map["packet_loss"]

    return f"Multiple correlated alarms detected - investigate {dominant or 'primary'} failure"


def _check_maintenance_penalty(nodes: List[str]) -> float:
    """
    Check if any nodes in the group are in maintenance window.
    Returns a confidence deduction if maintenance is active.
    """
    try:
        from backend.database import is_in_maintenance_window
        for node in nodes:
            if is_in_maintenance_window(node):
                logger.info(f"Maintenance penalty applied for node {node}")
                return 0.15
    except (ImportError, Exception):
        pass
    return 0.0


def _parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """
    Parse an ISO 8601 timestamp string to datetime.
    Handles formats with and without 'Z' suffix and timezone offsets.
    """
    if not timestamp_str:
        return None

    try:
        # Handle 'Z' suffix
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        try:
            # Try parsing with different format
            return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except (ValueError, TypeError):
            try:
                return datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError):
                logger.warning(f"Could not parse timestamp: {timestamp_str}")
                return None


def find_related_alarms(
    alarm_id: str,
    correlation_groups: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Find which correlation group a specific alarm belongs to.
    Returns the correlation group or None.
    """
    for group in correlation_groups:
        for alarm in group.get("alarms", []):
            if alarm.get("alarm_id") == alarm_id:
                return group
    return None