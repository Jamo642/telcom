"""
backend/fight_engine.py

MITRE FiGHT detection, explanation, self-critique, remediation, and feedback.

Parts 3-8 of the FiGHT integration:
  - detect_fight_techniques()   — structured indicator matching (Part 3)
  - explain_fight_technique()   — RAG-grounded LLM explanation (Part 4)
  - _self_critique()            — false-positive guard (Part 5, internal)
  - remediate_fight_technique() — mutating, approval-gated (Part 6)
  - log_false_positive()        — feedback loop (Part 7)

All detection is done with plain code against fight_techniques.json.
ChromaDB is used only for explanation (semantic retrieval).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

CONFIDENCE_THRESHOLD = int(os.environ.get("FIGHT_CONFIDENCE_THRESHOLD", "50"))
FIGHT_JSON_PATH      = os.environ.get("FIGHT_JSON", "/data/fight_techniques.json")
FEEDBACK_PATH        = os.environ.get("FIGHT_FEEDBACK_PATH", "/data/fight_feedback.jsonl")
ALLOWLIST_PATH       = os.environ.get("FIGHT_ALLOWLIST_PATH", "/data/fight_allowlist.json")
CHROMA_DB_PATH       = os.environ.get("CHROMA_DB_PATH", "/data/chroma_db")

# ─── Technique database (loaded once at import) ────────────────────────────────

def _load_techniques() -> Dict[str, Any]:
    paths = [
        FIGHT_JSON_PATH,
        "data/fight_techniques.json",
        str(Path(__file__).parent.parent / "data" / "fight_techniques.json"),
    ]
    for p in paths:
        if Path(p).exists():
            with open(p) as f:
                data = json.load(f)
            logger.info("Loaded %d FiGHT techniques from %s", len(data), p)
            return data
    logger.warning("fight_techniques.json not found — FiGHT engine running empty")
    return {}


TECHNIQUES: Dict[str, Any] = _load_techniques()


# ─── Baseline allowlist (suppress known-good patterns per asset) ─────────────

def _load_allowlist() -> Dict[str, List[str]]:
    """Returns {asset_id: [suppressed_indicator, ...]}"""
    paths = [ALLOWLIST_PATH, "data/fight_allowlist.json",
             str(Path(__file__).parent.parent / "data" / "fight_allowlist.json")]
    for p in paths:
        if Path(p).exists():
            with open(p) as f:
                return json.load(f)
    # Default minimal allowlist
    return {
        "Router-KNB-04":  ["high bgp route update volume"],
        "Switch-NBI-07":  ["output queue drops during maintenance"],
        "BNG-East":       ["connection rate above 150 during peak hours"],
    }


ALLOWLIST: Dict[str, List[str]] = _load_allowlist()


# ─── Feedback store ───────────────────────────────────────────────────────────

def log_false_positive(
    technique_id: str,
    matched_indicators: List[str],
    asset: str,
    context: str = "",
) -> Dict[str, Any]:
    """
    Part 7 — log a false-positive report.
    Persists to JSONL file; suppresses identical (asset, technique) matches in-session.
    """
    record = {
        "timestamp":          _utc_iso(),
        "technique_id":       technique_id,
        "asset":              asset,
        "matched_indicators": matched_indicators,
        "context":            context[:500],
    }
    fp_path = Path(FEEDBACK_PATH)
    fp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(fp_path, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Update in-memory allowlist so we suppress within this session too
    key = f"{asset}::{technique_id}"
    ALLOWLIST.setdefault(key, []).extend(matched_indicators)

    logger.info("False-positive logged: %s on %s", technique_id, asset)
    return {"status": "logged", "record": record}


def _is_suppressed(asset: str, technique_id: str, indicators: List[str]) -> bool:
    """True if this (asset, technique, indicators) combo was previously FP'd."""
    # Check session-level allowlist
    key = f"{asset}::{technique_id}"
    suppressed = set(ALLOWLIST.get(key, []))
    if not suppressed:
        return False
    # Suppress if ALL matched indicators are in the suppression list
    return all(ind in suppressed for ind in indicators)


def _load_feedback_suppressions() -> set:
    """Load previously logged (asset::technique_id) pairs from JSONL."""
    suppressed = set()
    fp_path = Path(FEEDBACK_PATH)
    if not fp_path.exists():
        return suppressed
    with open(fp_path) as f:
        for line in f:
            try:
                rec = json.loads(line)
                suppressed.add(f"{rec['asset']}::{rec['technique_id']}")
            except Exception:
                continue
    return suppressed


# ─── Part 3 — Detection engine ────────────────────────────────────────────────

def _score_candidate(
    technique: Dict[str, Any],
    matched: List[str],
    has_precursor: bool,
    asset: str,
) -> int:
    """
    Compute confidence 0-100.
      +10 per matched indicator (up to 50)
      +10 per distinct indicator beyond 2 (specificity bonus, up to 20)
      +15 kill-chain consistency (precursor present when expected)
      +15 if no asset-level baseline deviation (allowlist not triggered)
    """
    indicator_score  = min(len(matched) * 10, 50)
    specificity      = min(max(len(matched) - 2, 0) * 10, 20)
    precursor_needed = bool(technique.get("precursor_technique_ids"))
    kill_chain_score = 15 if (not precursor_needed or has_precursor) else 0
    baseline_score   = 15 if not _is_suppressed(asset, technique["technique_id"], matched) else 0
    return indicator_score + specificity + kill_chain_score + baseline_score


def detect_fight_techniques(
    alerts: List[Dict[str, Any]],
    logs: List[str],
    asset: str = "",
    time_window_minutes: int = 60,
) -> Dict[str, Any]:
    """
    Part 3 — Read-only, auto-executable.

    Match alerts + logs against FiGHT indicator lists using plain code.
    Requires 2+ independent corroborating indicators before surfacing a candidate.
    Checks precursor_technique_ids for kill-chain consistency.
    Applies self-critique (Part 5) before returning.
    Filters below CONFIDENCE_THRESHOLD.

    Args:
        alerts: List of alert/incident dicts (alarm_text, node_name, alarm_type, etc.)
        logs:   List of raw log line strings
        asset:  Asset identifier for allowlist lookup (e.g. node name)
        time_window_minutes: Correlation window (unused for now — all evidence treated as same window)

    Returns dict with findings list and metadata.
    """
    if not TECHNIQUES:
        return {"error": "FiGHT technique database not loaded", "findings": []}

    # Build one big text corpus from alerts + logs
    corpus_parts = []
    for a in alerts:
        corpus_parts.append(" ".join([
            str(a.get("alarm_text", "")),
            str(a.get("alarm_name", "")),
            str(a.get("alarm_type", "")),
            str(a.get("node_name", "")),
            str(a.get("root_cause", "")),
        ]))
    corpus_parts.extend(logs)
    corpus = "\n".join(corpus_parts).lower()

    resolved_asset = asset or (alerts[0].get("node_name", "unknown") if alerts else "unknown")

    # Load persistent suppressions
    persistent_suppressed = _load_feedback_suppressions()

    # Stopwords for keyword extraction
    _STOP = {
        "a", "an", "the", "is", "in", "on", "at", "of", "or", "and", "to",
        "for", "from", "with", "by", "via", "that", "this", "into",
    }

    def _indicator_matches(indicator: str, corpus: str) -> bool:
        """
        Two-tier matching:
         1. Full phrase match (exact substring) — highest confidence
         2. Keyword match — all non-stop words from the indicator are present
            somewhere in the corpus (allows paraphrasing, e.g. 'SRI' matches 'SendRoutingInfo')
        """
        ind_lower = indicator.lower()
        if ind_lower in corpus:
            return True
        # Extract significant keywords (≥3 chars, not stopwords)
        keywords = [w.strip("().,;:/") for w in ind_lower.split()
                    if len(w.strip("().,;:/")) >= 3 and w.strip("().,;:/") not in _STOP]
        if not keywords:
            return False
        # Also expand compound tokens (e.g. "map-sri" → ["map", "sri"])
        expanded = []
        for kw in keywords:
            parts = [p for p in kw.replace("-", " ").replace("/", " ").split() if len(p) >= 3]
            expanded.extend(parts if parts else [kw])
        # Require at least 2 keywords (or 40% of total if >5), whichever is larger
        hits = sum(1 for kw in expanded if kw in corpus)
        threshold = max(2, round(len(expanded) * 0.4))
        return hits >= threshold

    candidates = []

    for tid, tech in TECHNIQUES.items():
        # Skip if persistently suppressed for this asset
        if f"{resolved_asset}::{tid}" in persistent_suppressed:
            logger.debug("FiGHT: %s suppressed for asset %s (feedback)", tid, resolved_asset)
            continue

        # Match indicators using two-tier matching
        matched = [ind for ind in tech["indicators"] if _indicator_matches(ind, corpus)]

        # Require 2+ independent corroborating indicators
        if len(matched) < 2:
            continue

        # Check for precursor evidence
        precursor_ids = tech.get("precursor_technique_ids", [])
        has_precursor = False
        if precursor_ids:
            for pre_id in precursor_ids:
                pre_tech = TECHNIQUES.get(pre_id, {})
                pre_indicators = pre_tech.get("indicators", [])
                if any(ind.lower() in corpus for ind in pre_indicators):
                    has_precursor = True
                    break

        score = _score_candidate(tech, matched, has_precursor, resolved_asset)

        candidates.append({
            "technique_id":           tid,
            "name":                   tech["name"],
            "tactic":                 tech["tactic"],
            "kill_chain_phase":       tech.get("kill_chain_phase", ""),
            "matched_indicators":     matched,
            "precursor_ids":          precursor_ids,
            "has_precursor_evidence": has_precursor,
            "precursor_note":         (
                "Kill-chain consistent — precursor activity detected" if has_precursor
                else ("Lacks expected precursor activity" if precursor_ids else "No precursor required")
            ),
            "confidence":             score,
            "confidence_tier":        _confidence_tier(score),
            "detection_guidance":     tech["detection_guidance"],
        })

    # Filter below threshold
    findings = [c for c in candidates if c["confidence"] >= CONFIDENCE_THRESHOLD]
    below_threshold = [c for c in candidates if c["confidence"] < CONFIDENCE_THRESHOLD]

    # Apply self-critique (Part 5) to each finding
    for finding in findings:
        critique = _self_critique(finding, corpus)
        finding["self_critique"]         = critique["benign_explanation"]
        finding["critique_verdict"]      = critique["verdict"]
        if critique["downgrade"]:
            finding["confidence"]        = max(finding["confidence"] - 20, 0)
            finding["confidence_tier"]   = _confidence_tier(finding["confidence"])
            finding["confidence_note"]   = "Downgraded: benign explanation equally plausible"

    # Sort by confidence desc
    findings.sort(key=lambda x: x["confidence"], reverse=True)

    logger.info(
        "FiGHT detection: %d candidates, %d above threshold %d, %d suppressed/weak",
        len(candidates), len(findings), CONFIDENCE_THRESHOLD, len(below_threshold)
    )

    return {
        "findings":         findings,
        "count":            len(findings),
        "suppressed_count": len(below_threshold),
        "asset":            resolved_asset,
        "threshold":        CONFIDENCE_THRESHOLD,
    }


def _confidence_tier(score: int) -> str:
    if score >= 80: return "HIGH"
    if score >= 60: return "MEDIUM"
    if score >= 40: return "LOW"
    return "NEGLIGIBLE"


# ─── Part 5 — Self-critique pass ──────────────────────────────────────────────

def _self_critique(finding: Dict[str, Any], corpus: str) -> Dict[str, Any]:
    """
    One LLM call that argues the counter-case.
    Uses OpenRouter free model. Falls back to heuristic if LLM unavailable.
    """
    # Heuristic first — fast, no API call needed for obvious cases
    benign_keywords = [
        "maintenance", "scheduled", "planned", "upgrade", "test",
        "lab", "simulation", "capacity", "normal operation", "expected"
    ]
    corpus_lower = corpus[:2000].lower()
    benign_hits = [kw for kw in benign_keywords if kw in corpus_lower]
    if len(benign_hits) >= 2:
        return {
            "benign_explanation": f"Maintenance/test context detected ({', '.join(benign_hits[:3])}). Activity may be scheduled operational work.",
            "verdict":  "benign_likely",
            "downgrade": True,
        }

    # LLM self-critique for non-obvious cases
    try:
        from services.llm_service import get_llm_service
        llm = get_llm_service()
        prompt = (
            f"A security analyst flagged this as potential MITRE FiGHT technique "
            f"{finding['technique_id']} ({finding['name']}) based on these indicators: "
            f"{', '.join(finding['matched_indicators'])}.\n\n"
            f"In ONE sentence only: what is the most plausible BENIGN explanation for this "
            f"evidence in a telecom NOC context? If none is plausible, reply: 'No benign explanation — "
            f"activity appears anomalous.' Output only the sentence."
        )
        resp = llm.generate_response(prompt, temperature=0.1, max_tokens=80)
        benign = resp.get("response", "").strip()
        if not benign or resp.get("error") or len(benign) < 10:
            raise ValueError("empty response")

        # Only downgrade if the response explicitly asserts routine/scheduled context
        # — do NOT downgrade on vague "could be normal" phrasing
        strong_benign = ["routine maintenance", "scheduled test", "planned upgrade",
                         "lab test", "capacity test", "normal roaming"]
        downgrade = any(t in benign.lower() for t in strong_benign)

        return {
            "benign_explanation": benign[:200],
            "verdict":  "benign_possible" if downgrade else "threat_likely",
            "downgrade": downgrade,
        }
    except Exception as e:
        logger.debug("Self-critique LLM call failed (%s), using heuristic verdict", e)
        return {
            "benign_explanation": "No obvious benign context identified in available evidence.",
            "verdict":  "threat_likely",
            "downgrade": False,
        }


# ─── Part 4 — RAG-grounded explanation ────────────────────────────────────────

def explain_fight_technique(technique_id: str) -> Dict[str, Any]:
    """
    Part 4 — Read-only, auto-executable.

    1. Query ChromaDB (source=mitre_fight, technique_id=X) for grounded text
    2. Feed retrieved text to LLM for NOC-operator-friendly explanation
    """
    tech = TECHNIQUES.get(technique_id)
    if not tech:
        return {"error": f"Technique {technique_id} not in local database"}

    # Step 1 — retrieve from ChromaDB
    grounded_text = ""
    try:
        import chromadb
        from services.embedding_service import get_embedding_service

        chroma_path = CHROMA_DB_PATH
        if not Path(chroma_path).exists():
            chroma_path = str(Path(__file__).parent.parent / "data" / "chroma_db")

        client = chromadb.PersistentClient(path=chroma_path)
        col    = client.get_collection("telecom_incidents")
        emb    = get_embedding_service()

        query  = f"MITRE FiGHT {technique_id} {tech['name']} detection mitigation"
        vec    = emb.embed_text(query).tolist()

        hits = col.query(
            query_embeddings=[vec],
            n_results=3,
            where={"source": "mitre_fight"},
            include=["documents", "metadatas", "distances"],
        )
        docs = hits.get("documents", [[]])[0]
        grounded_text = "\n\n".join(docs) if docs else ""
        logger.info("FiGHT explain: retrieved %d docs from ChromaDB for %s", len(docs), technique_id)
    except Exception as exc:
        logger.warning("ChromaDB retrieval failed for explain (%s), using JSON fallback", exc)
        # Fallback: build grounded text from the JSON directly
        grounded_text = (
            f"Technique: {tech['name']} ({technique_id})\n"
            f"Tactic: {tech['tactic']}\n"
            f"Description: {tech['description']}\n"
            f"Detection: {tech['detection_guidance']}\n"
            f"Mitigation: {tech['mitigation_guidance']}"
        )

    # Step 2 — LLM explanation grounded in retrieved text
    explanation = ""
    try:
        from services.llm_service import get_llm_service
        llm = get_llm_service()
        prompt = (
            f"You are a telecom security expert explaining a threat to a NOC operator.\n\n"
            f"Use ONLY the following retrieved text as your source. Do not add information "
            f"from training data.\n\n"
            f"RETRIEVED TEXT:\n{grounded_text}\n\n"
            f"Explain technique {technique_id} ({tech['name']}) in plain language: "
            f"what it is, how to detect it in the NOC, and the top 2 mitigation steps. "
            f"Keep it under 200 words. Use bullet points for detection and mitigation."
        )
        resp = llm.generate_response(prompt, temperature=0.2, max_tokens=350)
        explanation = resp.get("response", "").strip()
    except Exception as exc:
        logger.warning("LLM explanation failed (%s), returning raw grounded text", exc)
        explanation = grounded_text[:600]

    return {
        "technique_id":    technique_id,
        "name":            tech["name"],
        "tactic":          tech["tactic"],
        "kill_chain":      tech.get("kill_chain_phase", ""),
        "explanation":     explanation,
        "grounded_source": "chromadb_mitre_fight",
        "raw_indicators":  tech["indicators"],
    }


# ─── Part 6 — Gated remediation (MUTATING) ────────────────────────────────────

def remediate_fight_technique(
    technique_id: str,
    target: str,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """
    Part 6 — MUTATING. Never auto-executed.

    If confirmed=False: returns proposal + "approve? (yes/no)" — agent pauses here.
    If confirmed=True:  logs the remediation action and returns result.
    """
    tech = TECHNIQUES.get(technique_id)
    if not tech:
        return {"error": f"Technique {technique_id} not found"}

    mitigation = tech.get("mitigation_guidance", "No mitigation guidance available.")
    # Extract first two sentences as the proposed action
    sentences = [s.strip() for s in mitigation.split(".") if s.strip()]
    proposed_action = ". ".join(sentences[:2]) + "." if sentences else mitigation

    if not confirmed:
        return {
            "status":           "pending_confirmation",
            "requires_approval": True,
            "technique_id":     technique_id,
            "name":             tech["name"],
            "target":           target,
            "proposed_action":  proposed_action,
            "full_mitigation":  mitigation,
            "message":          (
                f"⚠️  REMEDIATION PROPOSED for {technique_id} ({tech['name']}) on {target}:\n"
                f"Action: {proposed_action}\n\n"
                f"This action will modify network configuration. Approve? (yes/no)"
            ),
        }

    # Confirmed — log and return
    record = {
        "timestamp":      _utc_iso(),
        "technique_id":   technique_id,
        "name":           tech["name"],
        "target":         target,
        "action_taken":   proposed_action,
        "approved_by":    "operator",
    }
    remediation_log = Path(FEEDBACK_PATH).parent / "fight_remediations.jsonl"
    remediation_log.parent.mkdir(parents=True, exist_ok=True)
    with open(remediation_log, "a") as f:
        f.write(json.dumps(record) + "\n")

    logger.info("Remediation approved and logged: %s on %s", technique_id, target)
    return {
        "status":         "executed",
        "technique_id":   technique_id,
        "target":         target,
        "action_taken":   proposed_action,
        "full_mitigation": mitigation,
        "logged_to":      str(remediation_log),
    }


# ─── Part 8 — Structured finding formatter ────────────────────────────────────

def format_finding(finding: Dict[str, Any], explanation: Optional[str] = None) -> str:
    """
    Part 8 — Return a formatted string for a surfaced FiGHT finding.
    """
    tid    = finding["technique_id"]
    name   = finding["name"]
    tactic = finding["tactic"]
    conf   = finding["confidence"]
    tier   = finding["confidence_tier"]
    indics = "\n".join(f"  • {i}" for i in finding["matched_indicators"])
    kc     = finding.get("precursor_note", "")
    critique = finding.get("self_critique", "N/A")
    critique_verdict = finding.get("critique_verdict", "")
    conf_note = finding.get("confidence_note", "")

    remediation_note = (
        f"\n**Remediation available** — use `remediate_fight_technique(\"{tid}\", \"<target>\")`"
        if finding.get("technique_id") in TECHNIQUES else ""
    )

    lines = [
        f"## 🔴 MITRE FiGHT Detection: {tid} — {name}",
        f"**Tactic:** {tactic}  |  **Kill-chain phase:** {finding.get('kill_chain_phase','')}",
        f"**Confidence:** {conf}/100 ({tier})" + (f"  _{conf_note}_" if conf_note else ""),
        "",
        "**Corroborating indicators:**",
        indics,
        "",
        f"**Kill-chain consistency:** {kc}",
        "",
        f"**Self-critique (benign counter-case):** {critique}",
        f"**Verdict:** {critique_verdict}",
    ]
    if explanation:
        lines += ["", "**RAG-grounded explanation & mitigation:**", explanation]
    lines += [remediation_note] if remediation_note else []
    return "\n".join(lines)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
