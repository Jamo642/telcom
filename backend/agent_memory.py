"""
Short-term memory for the TeleNOC autonomous agent.

This module keeps fast in-memory state for reasoning loops and mirrors
thought/action history to SQLite for audit persistence.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional


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


@dataclass
class MemoryEvent:
    timestamp: str
    level: str
    alarm_id: str
    node_name: str
    event_type: str
    thought: str
    action: str
    result: Dict[str, Any]


class AgentMemory:
    """
    In-memory + SQLite-backed short-term memory for autonomous execution.

    Memory is intentionally reset on process restart, while SQLite audit rows
    remain available for investigation and reporting.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        max_recent_alarms: int = 100,
        max_action_history: int = 1000,
    ):
        self.db_path = db_path or _default_db_path()
        self.recent_alarms: Deque[Dict[str, Any]] = deque(maxlen=max_recent_alarms)
        self.watchlist: Dict[str, Dict[str, Any]] = {}
        self.open_incidents: Dict[str, Dict[str, Any]] = {}
        self.action_history: Deque[MemoryEvent] = deque(maxlen=max_action_history)
        self.fight_detections: Deque[Dict[str, Any]] = deque(maxlen=max_action_history)
        self._lock = asyncio.Lock()
        self._init_storage()

    @contextmanager
    def _db(self):
        db_dir = os.path.dirname(self.db_path) or "."
        os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_storage(self) -> None:
        with self._db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    level TEXT NOT NULL,
                    alarm_id TEXT,
                    node_name TEXT,
                    event_type TEXT NOT NULL,
                    thought TEXT,
                    action TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );

                CREATE INDEX IF NOT EXISTS idx_agent_audit_ts ON agent_audit_log(ts);
                CREATE INDEX IF NOT EXISTS idx_agent_audit_alarm ON agent_audit_log(alarm_id);
                CREATE INDEX IF NOT EXISTS idx_agent_audit_event_type ON agent_audit_log(event_type);
                """
            )

    async def remember_alarm(self, alarm: Dict[str, Any]) -> None:
        async with self._lock:
            self.recent_alarms.append(
                {
                    "alarm_id": alarm.get("alarm_id", ""),
                    "node_name": alarm.get("node_name", ""),
                    "severity": alarm.get("severity", ""),
                    "alarm_type": alarm.get("alarm_type", ""),
                    "alarm_text": alarm.get("alarm_text", ""),
                    "timestamp": alarm.get("timestamp") or _utc_iso(),
                }
            )

    async def remember(
        self,
        alarm_id: str,
        thought: str,
        action: str,
        result: Dict[str, Any],
        *,
        node_name: str = "",
        event_type: str = "action",
        level: str = "INFO",
    ) -> None:
        event = MemoryEvent(
            timestamp=_utc_iso(),
            level=level,
            alarm_id=alarm_id,
            node_name=node_name,
            event_type=event_type,
            thought=thought,
            action=action,
            result=result,
        )

        async with self._lock:
            self.action_history.append(event)
            with self._db() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_audit_log
                    (ts, level, alarm_id, node_name, event_type, thought, action, result_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.timestamp,
                        event.level,
                        event.alarm_id,
                        event.node_name,
                        event.event_type,
                        event.thought,
                        event.action,
                        json.dumps(event.result, ensure_ascii=True),
                    ),
                )

    async def remember_open_incident(self, alarm_id: str, incident: Dict[str, Any]) -> None:
        async with self._lock:
            self.open_incidents[alarm_id] = {
                **incident,
                "updated_at": _utc_iso(),
            }

    async def resolve_incident(self, alarm_id: str, resolution: str = "resolved") -> None:
        async with self._lock:
            incident = self.open_incidents.pop(alarm_id, None)
            if incident is not None:
                await self.remember(
                    alarm_id=alarm_id,
                    node_name=incident.get("node_name", ""),
                    thought="Incident marked as resolved",
                    action="resolve",
                    result={"status": resolution},
                    event_type="observation",
                )

    async def add_watch(self, node_name: str, reason: str, ttl_minutes: int = 120) -> None:
        expires_at = _utc_now() + timedelta(minutes=ttl_minutes)
        async with self._lock:
            self.watchlist[node_name] = {
                "node_name": node_name,
                "reason": reason,
                "added_at": _utc_iso(),
                "expires_at": _utc_iso(expires_at),
            }

    async def remember_fight_detection(self, detection: Dict[str, Any]) -> None:
        async with self._lock:
            enriched = {
                **detection,
                "detected_at": detection.get("detected_at") or _utc_iso(),
            }
            self.fight_detections.append(enriched)

    async def recall(self, node_name: Optional[str] = None, last_n: int = 10) -> Dict[str, Any]:
        async with self._lock:
            recent_alarms = list(self.recent_alarms)
            history = list(self.action_history)

            if node_name:
                recent_alarms = [a for a in recent_alarms if a.get("node_name") == node_name]
                history = [e for e in history if e.node_name == node_name]

            recent_alarms = recent_alarms[-last_n:]
            history_dicts = [asdict(event) for event in history[-last_n:]]

            return {
                "recent_alarms": recent_alarms,
                "watchlist": self.watchlist,
                "open_incidents": self.open_incidents,
                "action_history": history_dicts,
                "fight_detections": list(self.fight_detections)[-last_n:],
            }

    async def forget_old(self, older_than_hours: int = 24) -> int:
        cutoff = _utc_now() - timedelta(hours=older_than_hours)
        removed = 0

        async with self._lock:
            for node_name, watch in list(self.watchlist.items()):
                expires = watch.get("expires_at")
                if not expires:
                    continue
                try:
                    if _parse_iso(expires) < _utc_now():
                        del self.watchlist[node_name]
                        removed += 1
                except Exception:
                    del self.watchlist[node_name]
                    removed += 1

            self.fight_detections = deque(
                [
                    d
                    for d in self.fight_detections
                    if _parse_iso(d.get("detected_at", _utc_iso())) >= cutoff
                ],
                maxlen=self.fight_detections.maxlen,
            )

            with self._db() as conn:
                deleted = conn.execute(
                    "DELETE FROM agent_audit_log WHERE ts < ?",
                    (_utc_iso(cutoff),),
                ).rowcount
                removed += int(deleted or 0)

        return removed

    async def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(limit, 500))
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT ts, level, alarm_id, node_name, event_type, thought, action, result_json
                FROM agent_audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        logs: List[Dict[str, Any]] = []
        for row in rows:
            result_raw = row["result_json"] or "{}"
            try:
                parsed_result = json.loads(result_raw)
            except Exception:
                parsed_result = {"raw": result_raw}

            logs.append(
                {
                    "timestamp": row["ts"],
                    "level": row["level"],
                    "alarm_id": row["alarm_id"],
                    "node_name": row["node_name"],
                    "event_type": row["event_type"],
                    "thought": row["thought"],
                    "action": row["action"],
                    "result": parsed_result,
                }
            )

        return logs

    async def get_shift_metrics(self) -> Dict[str, Any]:
        async with self._lock:
            processed = len(self.action_history)
            p1_count = sum(1 for a in self.recent_alarms if (a.get("severity") or "").upper() == "P1")
            threats = len(self.fight_detections)
            open_count = len(self.open_incidents)

        return {
            "alarms_processed": processed,
            "p1_detected": p1_count,
            "fight_threats": threats,
            "open_incidents": open_count,
            "watchlist_nodes": len(self.watchlist),
        }


_memory_singleton: Optional[AgentMemory] = None


def get_agent_memory(db_path: Optional[str] = None) -> AgentMemory:
    global _memory_singleton
    if _memory_singleton is None:
        _memory_singleton = AgentMemory(db_path=db_path)
    return _memory_singleton
