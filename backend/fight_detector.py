"""
MITRE FiGHT TTP Detector for TeleNOC AI

Detects MITRE FiGHT (5G Hierarchy of Threats) techniques from
alarm text using keyword matching plus optional LLM enrichment.

Entry points:
  detect_fight_ttp(alarm_text)         → matched pattern dict or None
  enrich_with_fight(alarm_text, alarm_id, current_severity) → full enrichment dict
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── FiGHT technique definitions ───────────────────────────────────────────────

FIGHT_PATTERNS: List[Dict[str, Any]] = [
    {
        "fight_id": "FGT1002",
        "technique_name": "SS7 Location Tracking",
        "tactic": "Discovery",
        "upgrade_severity": True,
        "keywords": [
            "ss7", "map", "sigtran", "send routing info", "sri-sm",
            "location request", "hlr query", "subscriber location",
            "map ati", "any-time interrogation", "psi", "provide subscriber info",
        ],
        "explanation": (
            "SS7 MAP signaling is being abused to query subscriber location. "
            "An attacker with SS7 access can silently track any mobile subscriber "
            "by sending MAP SendRoutingInfo or ATI (Any-Time Interrogation) queries "
            "to the Home Location Register."
        ),
        "immediate_fix": (
            "1. Block external SS7 MAP SRI-SM/ATI queries at the signaling firewall. "
            "2. Alert on unknown GTT addresses sending location queries. "
            "3. Implement SMS Home Routing to shield subscriber data. "
            "4. Engage SS7 security team immediately."
        ),
        "long_term_fix": (
            "Deploy GSMA FS.11/FS.19-compliant SS7 firewall with Category 2 filtering. "
            "Enable SMS Home Routing (SHR). "
            "Migrate signaling to Diameter/SBA with TLS. "
            "Conduct regular SS7 penetration tests."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1002",
    },
    {
        "fight_id": "FGT1003",
        "technique_name": "SIM Swap / Subscriber Identity Fraud",
        "tactic": "Initial Access",
        "upgrade_severity": True,
        "keywords": [
            "sim swap", "msisdn change", "hlr update", "subscriber identity",
            "imsi transfer", "unauthorized sim", "sim hijack", "imsi catcher",
            "imsi catch", "stingray", "fake base station", "rogue base station",
        ],
        "explanation": (
            "SIM swap fraud or IMSI catcher activity detected. An attacker is "
            "manipulating the HLR/HSS to redirect a subscriber's identity to a "
            "SIM they control, enabling account takeover and call/SMS interception."
        ),
        "immediate_fix": (
            "1. Freeze all pending SIM swap requests on the affected MSISDN range. "
            "2. Require in-store biometric verification for SIM changes. "
            "3. Alert subscriber via alternate contact method. "
            "4. Check HLR logs for anomalous update sequences."
        ),
        "long_term_fix": (
            "Implement multi-factor authentication for HLR/HSS updates. "
            "Deploy IMSI catcher detection (passive RF monitoring). "
            "Enforce SS7 MAP UpdateLocation filtering. "
            "Integrate real-time fraud management system."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1003",
    },
    {
        "fight_id": "FGT1498",
        "technique_name": "Network Function Denial of Service",
        "tactic": "Impact",
        "upgrade_severity": True,
        "keywords": [
            "nrf", "amf", "smf", "udm", "ausf", "pcf", "network function down",
            "nf unavailable", "sba overload", "amf flood", "5g core unreachable",
            "registration storm", "service-based architecture", "sba",
            "n2 interface", "n11 interface", "amf overload",
        ],
        "explanation": (
            "A 5G core Network Function (NF) is under Denial of Service attack. "
            "Flood of registration or service requests is overwhelming the AMF or NRF, "
            "preventing legitimate subscriber access across the entire affected sector."
        ),
        "immediate_fix": (
            "1. Enable AMF/NRF overload control and rate limiting immediately. "
            "2. Identify and block source IPs of malicious registration requests. "
            "3. Activate secondary AMF instance for load redistribution. "
            "4. Engage 5G core vendor NOC for emergency support."
        ),
        "long_term_fix": (
            "Deploy 5G SBA firewall with NF-level rate limiting (3GPP TS 23.502). "
            "Implement mutual TLS (mTLS) on all SBI interfaces. "
            "Configure NRF with NF registration anomaly detection. "
            "Test AMF overload handling per 3GPP TS 23.501 clause 5.19."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1498",
    },
    {
        "fight_id": "FGT1570",
        "technique_name": "Roaming / Inter-PLMN Exploitation",
        "tactic": "Lateral Movement",
        "upgrade_severity": False,
        "keywords": [
            "roaming", "gtp tunnel", "inter-plmn", "visited network",
            "home network bypass", "ipx", "gprs tunneling", "gtp-c",
            "gtp-u", "inter-operator", "irx", "roaming partner",
        ],
        "explanation": (
            "Suspicious inter-PLMN or GTP tunneling activity detected. "
            "An attacker may be exploiting roaming interfaces to pivot laterally "
            "between network operators or bypass home-network security controls."
        ),
        "immediate_fix": (
            "1. Audit GTP-C messages from roaming partners for anomalies. "
            "2. Block unexpected Update PDP Context or Create Session requests. "
            "3. Verify IPX/GRX partner allowlists are current. "
            "4. Engage IPX provider to trace origin of anomalous traffic."
        ),
        "long_term_fix": (
            "Deploy GTP firewall per GSMA IR.88 recommendations. "
            "Implement GTP-C message rate limiting per partner. "
            "Enforce roaming traffic whitelisting at border nodes. "
            "Participate in GSMA Fraud and Security Group (FASG) intelligence sharing."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1570",
    },
    {
        "fight_id": "FGT1071",
        "technique_name": "C2 via Encrypted Control Plane Signaling",
        "tactic": "Command and Control",
        "upgrade_severity": True,
        "keywords": [
            "encrypted signaling", "http/2 abuse", "control plane anomaly",
            "nf communication anomaly", "scp", "sbi anomaly",
            "tls anomaly", "https anomaly on sbi", "abnormal scp traffic",
        ],
        "explanation": (
            "Anomalous encrypted signaling detected on 5G control plane interfaces. "
            "An attacker may be using encrypted SBI (Service-Based Interface) channels "
            "to exfiltrate data or issue covert commands through the 5G core."
        ),
        "immediate_fix": (
            "1. Enable deep packet inspection on SBI interfaces (SCP/NRF). "
            "2. Alert on unusual NF-to-NF communication patterns. "
            "3. Revoke and reissue TLS certificates for affected NFs. "
            "4. Isolate anomalous NF container for forensic analysis."
        ),
        "long_term_fix": (
            "Implement zero-trust architecture for all SBI communications. "
            "Deploy SBI-aware firewall with anomaly detection. "
            "Enforce NF certificate pinning. "
            "Enable SEPP (Security Edge Protection Proxy) for inter-PLMN SBI traffic."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1071",
    },
    {
        "fight_id": "FGT1592",
        "technique_name": "Network Reconnaissance via Diameter",
        "tactic": "Discovery",
        "upgrade_severity": False,
        "keywords": [
            "diameter", "s6a", "s6d", "s13", "abnormal diameter",
            "diameter error", "epc probing", "hss query flood",
            "cla", "ula", "air", "diameter flood", "dra",
        ],
        "explanation": (
            "Diameter protocol probing or reconnaissance detected on EPC interfaces. "
            "An attacker with Diameter access is attempting to enumerate subscribers, "
            "query HSS for authentication vectors, or map network topology."
        ),
        "immediate_fix": (
            "1. Block Diameter queries from unknown realms at the DRA. "
            "2. Rate-limit Diameter AIR/ULR per peer to prevent flood. "
            "3. Alert on Cancel-Location (CLR) requests from non-HSS sources. "
            "4. Review Diameter peer allowlist for unauthorized entries."
        ),
        "long_term_fix": (
            "Deploy Diameter firewall per GSMA FS.19 Category 1/2/3 controls. "
            "Enable Diameter realm-based routing with strict peering policy. "
            "Implement Diameter load balancer anomaly detection. "
            "Migrate LTE authentication to 5G SA with SUCI privacy."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1592",
    },
    {
        "fight_id": "FGT1485",
        "technique_name": "RAN Jamming / Interference",
        "tactic": "Impact",
        "upgrade_severity": True,
        "keywords": [
            "radio interference", "jamming", "ran degradation",
            "abnormal rf", "signal noise", "cell tower interference",
            "enodeb", "gnodeb", "gnodeb anomaly", "enodeb anomaly",
            "rach failure", "excessive interference", "rssi abnormal",
            "sinr degraded", "cqi low", "bler high",
        ],
        "explanation": (
            "Radio frequency jamming or interference detected on RAN nodes. "
            "A physical jamming attack can disrupt cell coverage for thousands "
            "of subscribers. BLER and SINR degradation across all bands "
            "is a strong indicator of intentional interference."
        ),
        "immediate_fix": (
            "1. Alert field operations for physical site inspection immediately. "
            "2. Activate neighbouring cells with extended coverage if available. "
            "3. Enable dynamic frequency hopping to avoid jammed bands. "
            "4. Engage national telecom authority if jamming is confirmed."
        ),
        "long_term_fix": (
            "Deploy RF monitoring sensors with jammer geolocation capability. "
            "Coordinate with national spectrum regulator for enforcement. "
            "Implement adaptive beamforming (Massive MIMO) to mitigate interference. "
            "Establish mutual aid agreements with other operators."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1485",
    },
    {
        "fight_id": "FGT1078",
        "technique_name": "Unauthorized Access via Valid Credentials",
        "tactic": "Defense Evasion",
        "upgrade_severity": True,
        "keywords": [
            "unauthorized login", "admin access anomaly",
            "privilege escalation", "credential abuse",
            "ems login", "nms unauthorized", "oss access",
            "abnormal admin", "brute force", "account takeover",
            "root login", "privileged access violation",
        ],
        "explanation": (
            "Unauthorized access using valid credentials detected on network management "
            "systems. An attacker may have compromised admin credentials and is accessing "
            "EMS/NMS/OSS at unusual hours or from unrecognized locations."
        ),
        "immediate_fix": (
            "1. Immediately lock the compromised admin account. "
            "2. Force password reset for all admin accounts. "
            "3. Revoke active sessions on EMS/NMS/OSS. "
            "4. Preserve audit logs for forensic investigation."
        ),
        "long_term_fix": (
            "Enforce MFA for all privileged account access. "
            "Implement PAM (Privileged Access Management) solution. "
            "Enable anomaly-based login detection (time, location, device). "
            "Conduct quarterly access privilege review and rotation."
        ),
        "reference": "https://fight.mitre.org/techniques/FGT1078",
    },
]


# ── Keyword detection ─────────────────────────────────────────────────────────

def detect_fight_ttp(alarm_text: str) -> Optional[Dict[str, Any]]:
    """
    Scan alarm_text for MITRE FiGHT technique keywords.
    Returns the first matched pattern dict, or None if no match.
    """
    text_lower = alarm_text.lower()
    for pattern in FIGHT_PATTERNS:
        for kw in pattern["keywords"]:
            if kw in text_lower:
                return pattern
    return None


# ── LLM enrichment (optional) ─────────────────────────────────────────────────

def _llm_enrich(alarm_text: str, pattern: Dict[str, Any]) -> Dict[str, str]:
    """
    Call LLMService.generate_response() for contextual explanation.
    Falls back to hardcoded text if LLM is unavailable or errors.
    """
    try:
        from services.llm_service import LLMService
        svc = LLMService()
        prompt = (
            f"You are a telecom security analyst. An alarm has triggered a MITRE FiGHT match.\n\n"
            f"Technique: {pattern['fight_id']} — {pattern['technique_name']} ({pattern['tactic']})\n"
            f"Alarm text: {alarm_text[:300]}\n\n"
            f"In 2-3 sentences, explain why this alarm matches this FiGHT technique "
            f"and what the immediate risk is to the network."
        )
        response = svc.generate_response(prompt)
        if response and len(response.strip()) > 20:
            return {
                "explanation": response.strip(),
                "immediate_fix": pattern["immediate_fix"],
                "long_term_fix": pattern["long_term_fix"],
            }
    except Exception as exc:
        logger.debug("LLM enrichment unavailable, using fallback: %s", exc)

    return {
        "explanation": pattern["explanation"],
        "immediate_fix": pattern["immediate_fix"],
        "long_term_fix": pattern["long_term_fix"],
    }


# ── Main enrichment function ──────────────────────────────────────────────────

_SEVERITY_UPGRADE = {"P4": "P2", "P3": "P1", "P2": "P1", "P1": "P1"}


def enrich_with_fight(
    alarm_text: str,
    alarm_id: str,
    current_severity: str,
) -> Dict[str, Any]:
    """
    Full FiGHT enrichment for an alarm.

    Returns:
        {
            "suspicious": bool,
            "fight_analysis": {
                "fight_id": str,
                "technique_name": str,
                "tactic": str,
                "explanation": str,
                "immediate_fix": str,
                "long_term_fix": str,
                "severity_upgraded": bool,
                "original_severity": str,
                "upgraded_severity": str,
                "reference": str,
            },
            "upgraded_severity": str,   # same as current_severity if not upgraded
        }
    """
    pattern = detect_fight_ttp(alarm_text)

    if pattern is None:
        return {
            "suspicious": False,
            "fight_analysis": None,
            "upgraded_severity": current_severity,
        }

    enriched_text = _llm_enrich(alarm_text, pattern)

    should_upgrade = pattern.get("upgrade_severity", False)
    upgraded = _SEVERITY_UPGRADE.get(current_severity, current_severity) if should_upgrade else current_severity

    logger.info(
        "FiGHT detection: alarm=%s technique=%s tactic=%s severity=%s→%s",
        alarm_id, pattern["fight_id"], pattern["tactic"],
        current_severity, upgraded,
    )

    return {
        "suspicious": True,
        "fight_analysis": {
            "fight_id": pattern["fight_id"],
            "technique_name": pattern["technique_name"],
            "tactic": pattern["tactic"],
            "explanation": enriched_text["explanation"],
            "immediate_fix": enriched_text["immediate_fix"],
            "long_term_fix": enriched_text["long_term_fix"],
            "severity_upgraded": (upgraded != current_severity),
            "original_severity": current_severity,
            "upgraded_severity": upgraded,
            "reference": pattern["reference"],
        },
        "upgraded_severity": upgraded,
    }
