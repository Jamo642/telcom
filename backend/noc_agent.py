"""
NOC Agent Loop — tool-using agent for TeleNOC AI.

Flow per query:
  1. Send system prompt + user query + tool schemas to the LLM
  2. If LLM returns tool_calls → execute each against real data
  3. Feed tool results back as tool-role messages
  4. Repeat until LLM returns a plain text answer (no tool calls)
  5. Cap at MAX_ITERATIONS=5; return graceful message if hit

Mutating tools (MUTATING_TOOLS set in noc_tools.py) are never auto-executed —
they return a "requires_confirmation" response instead.

Every step is logged to stdout AND to the agent_audit_log SQLite table via
AgentMemory so you can watch the reasoning chain live.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 8

SYSTEM_PROMPT = """You are TeleNOC AI, an autonomous network operations centre (NOC) assistant.

You have access to the following tools:
- get_active_alerts       — query live NOC alerts/incidents from the database; returns a "count" field with the total
- get_logs                — read raw syslog lines for a specific network device
- lookup_incident         — get full details of a specific incident by alarm ID
- search_knowledge_base   — search past incidents and runbooks for similar cases
- detect_fight_techniques — analyse alerts/logs for MITRE FiGHT 5G/telecom attack techniques
- explain_fight_technique — get a detailed explanation of a specific MITRE FiGHT technique
- remediate_fight_technique — (REQUIRES EXPLICIT CONFIRMATION) propose remediation steps

Rules:
1. ALWAYS use tools to gather real data before answering. Do not guess.
2. If a question requires multiple data points, call tools in sequence.
3. After gathering enough data, synthesise a clear, concise answer for the NOC operator.
4. Cite specific alarm IDs, node names, and timestamps from the data.
5. If you cannot resolve the issue within the tool calls available, say so clearly and recommend escalation.
6. For 5G/telecom security concerns, use detect_fight_techniques on the relevant alerts.
7. IMPORTANT: Each tool call returns a "count" field. Use that number directly — do NOT call the same tool again with a different limit just to recount. One call is sufficient to answer "how many" questions.
8. Once you have the data you need, stop calling tools and give your final answer immediately.
9. When the operator says "confirmed=true" or "approve" or "execute approved remediation", call remediate_fight_technique with confirmed=true to log and execute it.
"""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _call_llm_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    api_key: str,
    model: str,
    fallbacks: List[str],
    base_url: str = "https://openrouter.ai/api/v1/chat/completions",
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Call an OpenAI-compatible chat/completions endpoint with tool schemas.
    Works with both OpenRouter and NVIDIA NIM (same wire format).
    Walks the fallback model list on error/429.
    """
    from urllib import request as url_request, error as url_error

    headers: Dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if base_url.startswith("https://openrouter.ai"):
        headers["HTTP-Referer"] = "https://github.com/telenoc-ai"
        headers["X-Title"] = "TeleNOC AI"
    if extra_headers:
        headers.update(extra_headers)

    models_to_try = [model] + [m for m in fallbacks if m != model]

    for m in models_to_try:
        payload = json.dumps({
            "model": m,
            "messages": messages,
            "tools": tools if tools else None,
            "tool_choice": "auto" if tools else None,
            "max_tokens": 1024,
            "temperature": 0.2,
        }).encode()

        req = url_request.Request(base_url, data=payload, headers=headers, method="POST")
        try:
            with url_request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            choices = data.get("choices") or []
            if not choices:
                logger.warning("Agent LLM: empty choices from %s", m)
                continue
            msg = choices[0]["message"]
            msg["_model"] = m
            return msg
        except url_error.HTTPError as exc:
            logger.warning("Agent LLM: %s returned HTTP %s, trying next", m, exc.code)
            continue
        except Exception as exc:
            logger.warning("Agent LLM: %s failed (%s), trying next", m, exc)
            continue

    return {"role": "assistant", "content": "ERROR: All LLM models failed.", "_model": "none"}


def _coerce_arguments(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLMs sometimes serialise list/dict arguments as JSON strings.
    Deserialise them back so the tool functions receive the right types.
    """
    coerced = {}
    for k, v in arguments.items():
        if isinstance(v, str):
            stripped = v.strip()
            if (stripped.startswith("[") and stripped.endswith("]")) or \
               (stripped.startswith("{") and stripped.endswith("}")):
                try:
                    v = json.loads(stripped)
                except json.JSONDecodeError:
                    pass
        coerced[k] = v
    return coerced


def _execute_tool(name: str, arguments: Dict[str, Any]) -> str:
    """Execute a named tool and return its result as a JSON string."""
    from backend.noc_tools import TOOL_IMPLEMENTATIONS, MUTATING_TOOLS

    if name in MUTATING_TOOLS:
        # Allow if the caller already set confirmed=True (explicit operator approval)
        coerced_args = _coerce_arguments(name, arguments)
        if not coerced_args.get("confirmed", False):
            result = {
                "requires_confirmation": True,
                "tool": name,
                "arguments": arguments,
                "message": f"Tool '{name}' mutates state. Explicit confirmation required.",
            }
            return json.dumps(result)
        # confirmed=True — fall through to execution
        arguments = coerced_args

    fn = TOOL_IMPLEMENTATIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        result = fn(**_coerce_arguments(name, arguments))
        return json.dumps(result, default=str)
    except TypeError as exc:
        return json.dumps({"error": f"Invalid arguments for {name}: {exc}"})
    except Exception as exc:
        logger.error("Tool %s raised: %s", name, exc)
        return json.dumps({"error": str(exc)})


def run_agent(
    user_query: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full agent loop for a user query.

    Returns:
        {
            "answer":    str,          # final LLM response
            "trace":     list[dict],   # every step: thought/tool/result
            "iterations": int,
            "model":     str,
            "session_id": str,
        }
    """
    from backend.noc_tools import TOOL_SCHEMAS

    # ── Resolve LLM endpoint ─────────────────────────────────────────────────
    # Priority: NVIDIA NIM (if key present) → OpenRouter (if key present)
    nvidia_key      = os.environ.get("NVIDIA_API_KEY", "")
    openrouter_key  = os.environ.get("OPENROUTER_API_KEY", "")

    if nvidia_key:
        api_key       = nvidia_key
        primary_model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
        fallbacks     = [
            "meta/llama-3.1-70b-instruct",
            "meta/llama-3.2-3b-instruct",
        ]
        base_url      = "https://integrate.api.nvidia.com/v1/chat/completions"
        logger.info("Agent using NVIDIA NIM endpoint, model=%s", primary_model)
    elif openrouter_key:
        api_key       = openrouter_key
        primary_model = os.environ.get(
            "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
        )
        fallbacks     = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "qwen/qwen3-coder:free",
            "meta-llama/llama-3.2-3b-instruct:free",
        ]
        base_url      = "https://openrouter.ai/api/v1/chat/completions"
        logger.info("Agent using OpenRouter endpoint, model=%s", primary_model)
    else:
        logger.error("No LLM API key configured (NVIDIA_API_KEY or OPENROUTER_API_KEY)")
        return {
            "answer":     "No LLM API key configured. Set NVIDIA_API_KEY or OPENROUTER_API_KEY in .env.",
            "trace":      [],
            "iterations": 0,
            "model":      "none",
            "session_id": session_id or "none",
        }

    session_id = session_id or f"agent-{int(time.time())}"
    trace: List[Dict[str, Any]] = []
    used_model = primary_model

    # ── Build initial message history ────────────────────────────────────────
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_query},
    ]

    logger.info("═══ Agent session %s started ═══", session_id)
    logger.info("Query: %s", user_query)

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info("── Iteration %d/%d ──", iteration, MAX_ITERATIONS)

        # ── Call LLM ─────────────────────────────────────────────────────────
        t0 = time.time()
        llm_msg = _call_llm_with_tools(
            messages, TOOL_SCHEMAS, api_key, primary_model, fallbacks, base_url
        )
        elapsed = round(time.time() - t0, 2)
        used_model = llm_msg.get("_model", primary_model)

        tool_calls = llm_msg.get("tool_calls") or []
        content    = llm_msg.get("content") or ""

        # ── No tool calls → final answer ─────────────────────────────────────
        if not tool_calls:
            logger.info("Agent final answer after %d iteration(s) [%.2fs]", iteration, elapsed)
            trace.append({
                "iteration": iteration,
                "type":      "final_answer",
                "content":   content,
                "model":     used_model,
                "elapsed_s": elapsed,
            })
            _persist_trace(session_id, user_query, trace)
            return {
                "answer":     content,
                "trace":      trace,
                "iterations": iteration,
                "model":      used_model,
                "session_id": session_id,
            }

        # ── Execute each tool call ────────────────────────────────────────────
        # Append the assistant's tool-call message to history
        messages.append({
            "role":       "assistant",
            "content":    content or None,
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            tool_id   = tc.get("id", f"call_{iteration}")
            fn_info   = tc.get("function", {})
            tool_name = fn_info.get("name", "unknown")
            try:
                args = json.loads(fn_info.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info(
                "[%s] → tool=%s  args=%s",
                session_id, tool_name, json.dumps(args, default=str)
            )

            result_str = _execute_tool(tool_name, args)

            # Truncate very long results — but do it cleanly at the JSON level
            # so the LLM always receives valid JSON (not a broken mid-string slice)
            if len(result_str) > 4000:
                try:
                    result_obj = json.loads(result_str)
                    # For list-based results, keep summary metadata + truncated list
                    for list_key in ("alerts", "logs", "results", "incidents"):
                        if list_key in result_obj and isinstance(result_obj[list_key], list):
                            items = result_obj[list_key]
                            result_obj[list_key] = items[:10]
                            result_obj["_truncated"] = True
                            result_obj["_total_returned"] = len(items)
                            result_obj["_shown"] = min(10, len(items))
                            break
                    result_str = json.dumps(result_obj, default=str)
                except (json.JSONDecodeError, Exception):
                    # Last resort: cut to safe length with note
                    result_str = result_str[:3800] + '", "_truncated": true}'

            logger.info(
                "[%s] ← tool=%s  result=%s",
                session_id, tool_name, result_str[:300]
            )

            trace.append({
                "iteration": iteration,
                "type":      "tool_call",
                "tool":      tool_name,
                "arguments": args,
                "result":    result_str[:500],
                "model":     used_model,
                "elapsed_s": elapsed,
            })

            # Feed tool result back into the conversation
            messages.append({
                "role":         "tool",
                "tool_call_id": tool_id,
                "content":      result_str,
            })

    # ── Cap reached — do one final synthesis call without tools ──────────────
    logger.warning("Agent cap (%d iterations) reached for session %s", MAX_ITERATIONS, session_id)
    messages.append({
        "role":    "user",
        "content": (
            "You have reached the maximum tool-call limit. "
            "Based on everything you have gathered so far, provide your best "
            "final answer to the original question. Be concise and cite any "
            "alarm IDs, counts, or node names you already retrieved."
        ),
    })
    t0 = time.time()
    final_msg = _call_llm_with_tools(
        messages, [], api_key, primary_model, fallbacks, base_url  # empty tools → forces text answer
    )
    elapsed = round(time.time() - t0, 2)
    cap_content = final_msg.get("content") or (
        "I wasn't able to fully resolve this within the allowed steps. "
        "Please review the trace and consider escalating to the on-call engineer."
    )
    used_model = final_msg.get("_model", used_model)
    trace.append({
        "iteration": MAX_ITERATIONS,
        "type":      "cap_reached",
        "content":   cap_content,
        "model":     used_model,
        "elapsed_s": elapsed,
    })
    _persist_trace(session_id, user_query, trace)
    return {
        "answer":     cap_content,
        "trace":      trace,
        "iterations": MAX_ITERATIONS,
        "model":      used_model,
        "session_id": session_id,
    }


def _persist_trace(session_id: str, query: str, trace: List[Dict[str, Any]]) -> None:
    """Write the completed trace to the agent_audit_log via AgentMemory."""
    try:
        import asyncio
        from backend.agent_memory import get_agent_memory

        mem = get_agent_memory()

        async def _write():
            for step in trace:
                await mem.remember(
                    alarm_id=session_id,
                    thought=f"[agent] {step.get('type')}",
                    action=step.get("tool", step.get("type", "")),
                    result=step,
                    event_type="agent_step",
                    level="INFO",
                )

        # Handle both async and sync call contexts
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_write())
        except RuntimeError:
            asyncio.run(_write())
    except Exception as exc:
        logger.warning("Trace persistence failed (non-fatal): %s", exc)
