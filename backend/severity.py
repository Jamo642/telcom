"""
Severity Classifier for TeleNOC AI

Classifies telecom alarm severity as P1 (Critical), P2 (Major), P3 (Minor), or P4 (Warning).
Uses Groq API (Llama3-70B) for intelligent classification with fallback to rule-based logic.
Implements P1 confirmation: requires 2 similar alarms within 5 minutes before classifying P1.

Environment variables:
  - NVIDIA_API_KEY: NVIDIA API key (primary AI provider)
  - GROQ_API_KEY: API key for Groq (fallback)
  - HF_API_KEY: HuggingFace API key (secondary fallback)
  - LLM_PROVIDER: Override default provider (nvidia|groq|huggingface|ollama)
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Severity definitions
SEVERITY_ORDER = {
    "P1": 1,  # Critical - Service impacting, immediate response needed
    "P2": 2,  # Major - Significant impact, urgent response needed
    "P3": 3,  # Minor - Some impact, standard response
    "P4": 4,  # Warning - Minimal impact, monitoring
}

SEVERITY_SLA = {
    "P1": "15 minutes",
    "P2": "30 minutes",
    "P3": "2 hours",
    "P4": "8 hours",
}

SEVERITY_ESCALATE_TO = {
    "P1": "NOC Lead",
    "P2": "NOC Supervisor",
    "P3": "Network Engineer",
    "P4": "Junior Engineer",
}

# Confidence threshold for auto-processing
CONFIDENCE_AUTO_THRESHOLD = 0.75
# Number of similar alarms needed for P1 confirmation
P1_CONFIRMATION_COUNT = 2
# Time window for P1 confirmation (seconds)
P1_CONFIRMATION_WINDOW = 300  # 5 minutes


def classify_severity(
    alarm_text: str,
    alarm_type: str = "",
    node_name: str = "",
    recent_alarms: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Main entry point: classify alarm severity.
    
    Args:
        alarm_text: Raw alarm description text
        alarm_type: Type of alarm (BGP, packet_loss, interface, etc.)
        node_name: Name of the affected network node
        recent_alarms: List of recent alarms for P1 confirmation check
    
    Returns:
        Dict with keys: severity, confidence, root_cause, recommended_action,
                       relevant_runbook, escalate_to, respond_within, needs_review
    """
    logger.info(f"Classifying severity for alarm: {alarm_text[:100]}...")

    # Step 1: Try LLM-based classification (Groq or HuggingFace)
    result = _llm_classify(alarm_text, alarm_type, node_name)

    # Step 2: If LLM fails or returns low confidence, use rule-based fallback
    if result.get("error") or result.get("confidence", 0) < 0.5:
        logger.info("LLM classification unreliable, using rule-based fallback")
        result = _rule_based_classify(alarm_text, alarm_type, node_name)

    # Step 3: P1 confirmation check
    if result["severity"] == "P1":
        if not _confirm_p1(alarm_text, node_name, recent_alarms):
            logger.info(f"P1 downgraded: insufficient confirmation for {alarm_text[:50]}")
            result["severity"] = "P2"
            result["confidence"] = min(result["confidence"], 0.7)
            result["p1_confirmed"] = False
        else:
            result["p1_confirmed"] = True

    # Step 4: Set escalation metadata
    result["escalate_to"] = SEVERITY_ESCALATE_TO.get(result["severity"], "Network Engineer")
    result["respond_within"] = SEVERITY_SLA.get(result["severity"], "4 hours")
    result["needs_review"] = result["confidence"] < CONFIDENCE_AUTO_THRESHOLD

    return result


def _llm_classify(alarm_text: str, alarm_type: str, node_name: str) -> Dict[str, Any]:
    """
    Classify severity using available LLM API.
    Priority: NVIDIA → Groq → HuggingFace → Ollama (via llm_service.py).
    Falls back to rule-based if all fail.
    Returns structured classification result.
    """
    # Priority 1: Try NVIDIA API (primary AI provider for judges)
    nvidia_api_key = os.environ.get("NVIDIA_API_KEY")
    if nvidia_api_key:
        try:
            return _nvidia_classify(alarm_text, alarm_type, node_name, nvidia_api_key)
        except Exception as e:
            logger.warning(f"NVIDIA API failed: {e}")

    # Priority 2: Try Groq
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if groq_api_key:
        try:
            return _groq_classify(alarm_text, alarm_type, node_name, groq_api_key)
        except Exception as e:
            logger.warning(f"Groq API failed: {e}")

    # Priority 3: Try HuggingFace
    hf_api_key = os.environ.get("HF_API_KEY")
    if hf_api_key:
        try:
            return _hf_classify(alarm_text, alarm_type, node_name, hf_api_key)
        except Exception as e:
            logger.warning(f"HuggingFace API failed: {e}")

    # Priority 4: Try Ollama via llm_service (local fallback)
    try:
        from services.llm_service import get_llm_service
        llm = get_llm_service()
        if llm.is_available():
            result = llm.structured_reasoning(
                incident=alarm_text,
                context=f"NODE: {node_name}\nTYPE: {alarm_type}",
                temperature=0.1,
                provider="ollama",
            )
            if result.get("structured_response"):
                sr = result["structured_response"]
                return {
                    "severity": sr.get("severity", "P3"),
                    "confidence": sr.get("confidence_score", 0.6),
                    "root_cause": sr.get("root_cause", "Unknown"),
                    "recommended_action": sr.get("recommended_actions", [{}])[0].get("action", "Investigate") if isinstance(sr.get("recommended_actions"), list) else "Investigate",
                    "relevant_runbook": "NOC-SOP-GEN-001",
                }
    except Exception as e:
        logger.warning(f"Ollama classification failed: {e}")

    # No API available
    return {"error": "No LLM API available", "confidence": 0}


def _nvidia_classify(
    alarm_text: str, alarm_type: str, node_name: str, api_key: str
) -> Dict[str, Any]:
    """
    Call NVIDIA API for severity classification.
    Uses Llama3-70B via NVIDIA's integrated API endpoint.
    """
    import httpx

    prompt = f"""You are a telecom NOC severity classification expert. Analyze this alarm and respond with a JSON object only.

ALARM:
{alarm_text}

NODE: {node_name}
TYPE: {alarm_type}

Classify severity as one of:
- P1 (Critical): Service-impacting outage, multiple users affected, immediate response needed
- P2 (Major): Significant degradation, partial service loss, urgent response needed
- P3 (Minor): Some degradation, non-critical, standard response time
- P4 (Warning): Informational, minimal impact, monitoring only

Respond with ONLY this JSON structure (no other text):
{{
    "severity": "P1|P2|P3|P4",
    "confidence": 0.0-1.0,
    "root_cause": "brief root cause description",
    "recommended_action": "first action to take",
    "relevant_runbook": "NOC-SOP-XXX-XXX"
}}"""

    response = httpx.post(
        "https://integrate.api.nvidia.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "meta/llama3-70b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 300,
            "top_p": 0.9,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    content = data["choices"][0]["message"]["content"]
    return _parse_llm_response(content)


def _groq_classify(
    alarm_text: str, alarm_type: str, node_name: str, api_key: str
) -> Dict[str, Any]:
    """
    Call Groq API with Llama3-70B for severity classification.
    Returns structured JSON with severity, confidence, root cause.
    """
    import httpx

    prompt = f"""You are a telecom NOC severity classification expert. Analyze this alarm and respond with a JSON object only.

ALARM:
{alarm_text}

NODE: {node_name}
TYPE: {alarm_type}

Classify severity as one of:
- P1 (Critical): Service-impacting outage, multiple users affected, immediate response needed
- P2 (Major): Significant degradation, partial service loss, urgent response needed
- P3 (Minor): Some degradation, non-critical, standard response time
- P4 (Warning): Informational, minimal impact, monitoring only

Respond with ONLY this JSON structure (no other text):
{{
    "severity": "P1|P2|P3|P4",
    "confidence": 0.0-1.0,
    "root_cause": "brief root cause description",
    "recommended_action": "first action to take",
    "relevant_runbook": "NOC-SOP-XXX-XXX"
}}"""

    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama3-70b-8192",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 300,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    # Parse JSON from response
    content = data["choices"][0]["message"]["content"]
    return _parse_llm_response(content)


def _hf_classify(
    alarm_text: str, alarm_type: str, node_name: str, api_key: str
) -> Dict[str, Any]:
    """
    Call HuggingFace Inference API (Mistral-7B) for severity classification.
    Fallback when Groq is unavailable.
    """
    import httpx

    prompt = f"""<s>[INST] You are a telecom NOC severity classifier. Analyze this alarm and return ONLY valid JSON.

ALARM: {alarm_text}
NODE: {node_name}
TYPE: {alarm_type}

Severity rules:
- P1 = Service outage, critical impact
- P2 = Major degradation
- P3 = Minor degradation  
- P4 = Informational

Return JSON:
{{"severity": "P1-P4", "confidence": 0.0-1.0, "root_cause": "...", "recommended_action": "...", "relevant_runbook": "..."}} [/INST]"""

    response = httpx.post(
        "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 250,
                "temperature": 0.1,
                "return_full_text": False,
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    content = data[0]["generated_text"] if isinstance(data, list) else str(data)
    return _parse_llm_response(content)


def _parse_llm_response(content: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response, with regex fallback for malformed responses.
    """
    # Try direct JSON parse
    try:
        result = json.loads(content)
        # Validate required fields
        if "severity" not in result:
            raise ValueError("Missing severity field")
        if result["severity"] not in SEVERITY_ORDER:
            raise ValueError(f"Invalid severity: {result['severity']}")
        result.setdefault("confidence", 0.5)
        result.setdefault("root_cause", "Unknown")
        result.setdefault("recommended_action", "Investigate alarm")
        result.setdefault("relevant_runbook", "NOC-SOP-GEN-001")
        return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to extract JSON from text using regex
    import re
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            if "severity" in result and result["severity"] in SEVERITY_ORDER:
                result.setdefault("confidence", 0.5)
                result.setdefault("root_cause", "Unknown")
                result.setdefault("recommended_action", "Investigate alarm")
                result.setdefault("relevant_runbook", "NOC-SOP-GEN-001")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    return {"error": "Failed to parse LLM response", "confidence": 0}


def _rule_based_classify(alarm_text: str, alarm_type: str, node_name: str) -> Dict[str, Any]:
    """
    Rule-based severity classification fallback.
    Uses keyword matching and alarm type patterns.
    """
    alarm_lower = alarm_text.lower()
    alarm_type_lower = alarm_type.lower()

    # P1 indicators: Critical impact patterns
    p1_patterns = [
        "bgp", "session drop", "neighbor down", "outage", "down",
        "packet loss > 20", ">20%", "20 percent", "complete failure",
        "power failure", "power outage", "node unreachable",
        "service impact", "all users", "sla breach",
    ]
    
    # P2 indicators: Major degradation patterns
    p2_patterns = [
        "packet loss > 10", ">10%", "10 percent", "high cpu",
        "high memory", "memory > 90", "cpu > 90", "interface error",
        "crc error", "congestion", "delay", "high latency",
        "dns timeout", "routing loop", "flapping",
    ]

    # P3 indicators: Minor issues
    p3_patterns = [
        "warning", "high utilization", "utilization > 80",
        "threshold crossed", "degraded", "error rate",
        "retransmission", "tcp reset", "small packet loss",
        "buffer overflow", "queue full",
    ]

    # Count pattern matches
    p1_score = sum(1 for p in p1_patterns if p in alarm_lower or p in alarm_type_lower)
    p2_score = sum(1 for p in p2_patterns if p in alarm_lower or p in alarm_type_lower)
    p3_score = sum(1 for p in p3_patterns if p in alarm_lower or p in alarm_type_lower)

    # Determine severity based on highest scoring category
    if p1_score > p2_score and p1_score > p3_score:
        severity = "P1"
        confidence = min(0.5 + p1_score * 0.1, 0.85)
    elif p2_score > p3_score:
        severity = "P2"
        confidence = min(0.5 + p2_score * 0.1, 0.80)
    elif p3_score > 0:
        severity = "P3"
        confidence = min(0.5 + p3_score * 0.08, 0.75)
    else:
        severity = "P4"
        confidence = 0.5

    # Determine root cause and action based on alarm type
    root_cause, action, runbook = _get_rule_based_details(alarm_lower, alarm_type_lower)

    return {
        "severity": severity,
        "confidence": round(confidence, 2),
        "root_cause": root_cause,
        "recommended_action": action,
        "relevant_runbook": runbook,
    }


def _get_rule_based_details(
    alarm_lower: str, alarm_type_lower: str
) -> Tuple[str, str, str]:
    """
    Get rule-based root cause, action, and runbook for common alarm types.
    """
    if "bgp" in alarm_lower or "bgp" in alarm_type_lower:
        return (
            "BGP session failure detected - likely peering or link issue",
            "Check BGP neighbor status and verify TCP port 179 connectivity",
            "NOC-SOP-BGP-003",
        )
    if "packet loss" in alarm_lower or "packet_loss" in alarm_type_lower:
        return (
            "Packet loss detected - possible congestion or link degradation",
            "Run MTR/traceroute to identify lossy hop and check interface errors",
            "NOC-SOP-LOSS-002",
        )
    if "interface" in alarm_lower or "interface" in alarm_type_lower:
        return (
            "Interface errors detected - possible hardware fault or duplex mismatch",
            "Check interface counters, reset interface, verify cabling",
            "NOC-SOP-INT-001",
        )
    if "power" in alarm_lower or "power" in alarm_type_lower:
        return (
            "Power supply anomaly detected on network node",
            "Verify power redundancy, check UPS status, dispatch field engineer",
            "NOC-SOP-PWR-001",
        )
    if "cpu" in alarm_lower or "cpu" in alarm_type_lower or "memory" in alarm_lower:
        return (
            "Resource utilization threshold exceeded on network node",
            "Check running processes, identify resource-intensive tasks, consider scaling",
            "NOC-SOP-RES-002",
        )
    if "dns" in alarm_lower or "dns" in alarm_type_lower:
        return (
            "DNS resolution failure detected",
            "Check DNS server health, verify forwarder configuration, clear cache",
            "NOC-SOP-DNS-001",
        )
    if "link" in alarm_lower or "degrad" in alarm_lower:
        return (
            "Link degradation trend detected - potential pre-outage condition",
            "Analyze interface statistics over last 24h, schedule maintenance",
            "NOC-SOP-LINK-002",
        )
    return (
        "Unknown alarm condition requiring investigation",
        "Acknowledge alarm and begin standard troubleshooting procedure",
        "NOC-SOP-GEN-001",
    )


def _confirm_p1(
    alarm_text: str,
    node_name: str,
    recent_alarms: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    P1 confirmation logic: require 2 similar alarms within 5 minutes
    before classifying an alarm as P1. Prevents false P1 classifications
    from transient or isolated events.
    
    Args:
        alarm_text: Current alarm description
        node_name: Affected node name
        recent_alarms: List of recent alarms with 'alarm_text' and 'timestamp' keys
    
    Returns:
        True if P1 is confirmed (enough similar alarms in window), False otherwise
    """
    if not recent_alarms or len(recent_alarms) < P1_CONFIRMATION_COUNT - 1:
        # Need at least (P1_CONFIRMATION_COUNT - 1) previous alarms to compare
        logger.info(f"P1 confirmation: insufficient recent alarms ({len(recent_alarms or [])})")
        return False

    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=P1_CONFIRMATION_WINDOW)
    
    # Count similar alarms from same node within the time window
    similar_count = 0
    for alarm in recent_alarms:
        try:
            alarm_time = datetime.fromisoformat(alarm.get("timestamp", "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            alarm_time = now  # If no timestamp, treat as current

        if alarm_time < cutoff:
            continue  # Outside the confirmation window
        
        # Check if alarm is from same node or has similar text
        same_node = alarm.get("node_name", "").lower() == node_name.lower()
        if same_node:
            similar_count += 1

    logger.info(
        f"P1 confirmation: found {similar_count} similar alarms within "
        f"{P1_CONFIRMATION_WINDOW}s window (need {P1_CONFIRMATION_COUNT})"
    )
    return similar_count >= P1_CONFIRMATION_COUNT


def needs_human_review(result: Dict[str, Any]) -> bool:
    """
    Check if the classification result requires human review.
    Returns True if confidence is below threshold or P1 is unconfirmed.
    """
    if result.get("confidence", 1.0) < CONFIDENCE_AUTO_THRESHOLD:
        return True
    if result.get("severity") == "P1" and not result.get("p1_confirmed", True):
        return True
    return False