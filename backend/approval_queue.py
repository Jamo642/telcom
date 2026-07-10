"""
Human-in-the-Loop Approval Queue for TeleNOC AI

Agent actions are split into two categories:
  AUTO_APPROVE     — safe, read-only, or low-risk: agent executes immediately
  REQUIRES_APPROVAL — high-risk: agent submits here; engineer approves/rejects

P1 safety override: if a REQUIRES_APPROVAL item has been waiting longer than
its urgency_minutes with no decision, tick() auto-approves it so critical
incidents are never silently dropped.
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Action policy ─────────────────────────────────────────────────────────────

AUTO_APPROVE: List[str] = [
    "DIAGNOSE",
    "CORRELATE",
    "FIGHT_CHECK",
    "WATCH",
    "NOTIFY",
    "SUMMARIZE",
]

REQUIRES_APPROVAL: List[str] = [
    "ESCALATE_P1",
    "RESOLVE_P1",
    "BLOCK_TRAFFIC",
    "CONFIG_CHANGE",
    "SUPPRESS_ALARM",
]

# Default P1 safety-override window (minutes)
DEFAULT_URGENCY_MINUTES = 15


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(ts: Optional[datetime] = None) -> str:
    value = ts or _utc_now()
    return value.isoformat().replace("+00:00", "Z")


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    # Deserialise stored JSON context
    raw = d.get("context_json") or "{}"
    try:
        d["context"] = json.loads(raw)
    except Exception:
        d["context"] = {}
    # Compute waiting_seconds for convenience
    submitted = d.get("submitted_at") or ""
    try:
        sub_dt = datetime.fromisoformat(submitted.replace("Z", "+00:00"))
        d["waiting_seconds"] = round((_utc_now() - sub_dt).total_seconds(), 1)
    except Exception:
        d["waiting_seconds"] = 0
    return d


# ── ApprovalQueue ─────────────────────────────────────────────────────────────

class ApprovalQueue:
    """
    SQLite-backed approval queue for agent high-risk actions.

    Usage:
        q = ApprovalQueue(db_path)
        if q.requires_approval("ESCALATE_P1"):
            item = q.submit("ESCALATE_P1", alarm_id="ALM-041", reason="FiGHT P1", ...)
            # engineer calls q.approve(item["id"], "alice") later
        q.tick()  # call periodically to auto-approve timed-out P1 items
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db")
        self._init_table()

    # ── Internal ─────────────────────────────────────────────────────────────

    @contextmanager
    def _db(self):
        db_dir = os.path.dirname(self.db_path) or "."
        os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_table(self) -> None:
        with self._db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS approval_queue (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    action          TEXT    NOT NULL,
                    alarm_id        TEXT,
                    node_name       TEXT,
                    reason          TEXT    NOT NULL,
                    urgency_minutes INTEGER DEFAULT 15,
                    context_json    TEXT,
                    agent_confidence REAL   DEFAULT 0.0,
                    status          TEXT    NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending','approved','rejected',
                                         'auto_approved','cancelled')),
                    submitted_at    TEXT    NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    decided_at      TEXT,
                    decided_by      TEXT,
                    rejection_reason TEXT,
                    auto_override   INTEGER DEFAULT 0,
                    created_at      TEXT    NOT NULL
                        DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS idx_approval_status
                    ON approval_queue(status);
                CREATE INDEX IF NOT EXISTS idx_approval_alarm
                    ON approval_queue(alarm_id);
            """)

    # ── Public API ────────────────────────────────────────────────────────────

    def requires_approval(self, action: str) -> bool:
        """Return True if this action must go through the approval queue."""
        return action.upper() in REQUIRES_APPROVAL

    def submit(
        self,
        action: str,
        reason: str,
        *,
        alarm_id: str = "",
        node_name: str = "",
        context: Optional[Dict[str, Any]] = None,
        urgency_minutes: int = DEFAULT_URGENCY_MINUTES,
        agent_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Submit an action for human approval.
        Returns the created approval item dict.
        """
        context_json = json.dumps(context or {}, ensure_ascii=True)
        now = _utc_iso()
        with self._db() as conn:
            cursor = conn.execute(
                """INSERT INTO approval_queue
                   (action, alarm_id, node_name, reason, urgency_minutes,
                    context_json, agent_confidence, submitted_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (action.upper(), alarm_id, node_name, reason,
                 urgency_minutes, context_json, agent_confidence, now),
            )
            row_id = cursor.lastrowid

        logger.info(
            "Approval requested: id=%s action=%s alarm=%s reason=%s",
            row_id, action, alarm_id, reason,
        )
        return self.get_by_id(row_id)  # type: ignore[return-value]

    def get_pending(self) -> List[Dict[str, Any]]:
        """Return all items currently awaiting a decision, oldest first."""
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE status='pending' "
                "ORDER BY submitted_at ASC"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM approval_queue WHERE id=?", (item_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def approve(self, item_id: int, approved_by: str = "engineer") -> Dict[str, Any]:
        """Mark a pending item as approved."""
        return self._decide(item_id, "approved", approved_by, None, auto=False)

    def reject(
        self,
        item_id: int,
        rejected_by: str = "engineer",
        rejection_reason: str = "",
    ) -> Dict[str, Any]:
        """Mark a pending item as rejected."""
        return self._decide(item_id, "rejected", rejected_by, rejection_reason, auto=False)

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Full audit log, newest first."""
        safe_limit = max(1, min(limit, 500))
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_queue ORDER BY created_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def tick(self) -> int:
        """
        Auto-approve any pending items that have exceeded urgency_minutes.
        Returns the number of items auto-approved.
        Called on every /approvals/pending and /diagnose request.
        """
        now = _utc_now()
        with self._db() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE status='pending'"
            ).fetchall()

        overridden = 0
        for row in rows:
            try:
                submitted = datetime.fromisoformat(
                    (row["submitted_at"] or "").replace("Z", "+00:00")
                )
                deadline = submitted + timedelta(minutes=row["urgency_minutes"] or 15)
                if now >= deadline:
                    self._decide(row["id"], "auto_approved", "SYSTEM_TIMEOUT", None, auto=True)
                    logger.warning(
                        "Auto-approved id=%s action=%s after %sm timeout",
                        row["id"], row["action"], row["urgency_minutes"],
                    )
                    overridden += 1
            except Exception as exc:
                logger.debug("tick error on id=%s: %s", row["id"], exc)

        return overridden

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _decide(
        self,
        item_id: int,
        new_status: str,
        decided_by: str,
        rejection_reason: Optional[str],
        *,
        auto: bool,
    ) -> Dict[str, Any]:
        now = _utc_iso()
        with self._db() as conn:
            conn.execute(
                """UPDATE approval_queue
                   SET status=?, decided_at=?, decided_by=?,
                       rejection_reason=?, auto_override=?
                   WHERE id=? AND status='pending'""",
                (new_status, now, decided_by, rejection_reason or "", 1 if auto else 0, item_id),
            )
        item = self.get_by_id(item_id)
        if item is None:
            raise KeyError(f"Approval item {item_id} not found")
        return item


# ── Module-level singleton ────────────────────────────────────────────────────

_singleton: Optional[ApprovalQueue] = None


def get_approval_queue(db_path: Optional[str] = None) -> ApprovalQueue:
    global _singleton
    if _singleton is None:
        _singleton = ApprovalQueue(db_path=db_path)
    return _singleton
