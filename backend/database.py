"""
SQLite Database Schema and Queries for TeleNOC AI

Manages incidents, escalations, maintenance windows, and transient alarm tracking.
All timestamps stored as ISO 8601 strings in UTC.
"""

import sqlite3
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Default database path
DB_PATH = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db")


@contextmanager
def get_db(db_path: str = DB_PATH):
    """
    Context manager for database connections.
    Ensures connection is properly closed after use.
    """
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH):
    """
    Initialize database schema. Creates tables if they don't exist.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    with get_db(db_path) as conn:
        conn.executescript("""
            -- Incidents table: stores all diagnosed alarm incidents
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id TEXT NOT NULL UNIQUE,
                alarm_name TEXT,
                node_name TEXT,
                alarm_type TEXT,
                severity TEXT NOT NULL CHECK(severity IN ('P1','P2','P3','P4')),
                confidence REAL DEFAULT 0.0,
                root_cause TEXT,
                recommended_action TEXT,
                relevant_runbook TEXT,
                escalate_to TEXT,
                respond_within TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','resolved','closed','escalated')),
                mttr_started_at TEXT,
                mttr_resolved_at TEXT,
                mttr_seconds REAL,
                correlated_group_id TEXT,
                raw_alarm_text TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );

            -- Escalations table: tracks SLA-based escalations
            CREATE TABLE IF NOT EXISTS escalations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                alarm_id TEXT NOT NULL,
                escalated_to TEXT NOT NULL,
                escalated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                sla_deadline TEXT NOT NULL,
                acknowledged_at TEXT,
                resolved_at TEXT,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','acknowledged','resolved','missed')),
                FOREIGN KEY (incident_id) REFERENCES incidents(id)
            );

            -- Maintenance windows: planned maintenance to suppress false alarms
            CREATE TABLE IF NOT EXISTS maintenance_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                reason TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );

            -- Transient alarms: tracks self-clearing alarms for filtering
            CREATE TABLE IF NOT EXISTS transient_alarms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id TEXT NOT NULL,
                node_name TEXT NOT NULL,
                alarm_type TEXT,
                first_seen TEXT NOT NULL,
                cleared_at TEXT,
                duration_seconds REAL,
                is_transient INTEGER DEFAULT 0
            );

            -- Trend data: aggregated alarm counts per node for degradation detection
            CREATE TABLE IF NOT EXISTS trend_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_name TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                alarm_count INTEGER DEFAULT 0,
                p1_count INTEGER DEFAULT 0,
                p2_count INTEGER DEFAULT 0,
                severity_score REAL DEFAULT 0.0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );

            -- Confidence audit: logs low-confidence decisions for human review
            CREATE TABLE IF NOT EXISTS confidence_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alarm_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_incidents_alarm_id ON incidents(alarm_id);
            CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
            CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity);
            CREATE INDEX IF NOT EXISTS idx_incidents_node ON incidents(node_name);
            CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at);
            CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status);
            CREATE INDEX IF NOT EXISTS idx_maintenance_node ON maintenance_windows(node_name);
            CREATE INDEX IF NOT EXISTS idx_transient_alarm_id ON transient_alarms(alarm_id);
            CREATE INDEX IF NOT EXISTS idx_trend_node ON trend_data(node_name);
        """)
    logger.info("Database schema initialized successfully")


# ─── Incident CRUD ────────────────────────────────────────────────────────────

def log_incident(
    alarm_id: str,
    severity: str,
    confidence: float,
    root_cause: str = "",
    recommended_action: str = "",
    relevant_runbook: str = "",
    escalate_to: str = "",
    respond_within: str = "",
    node_name: str = "",
    alarm_type: str = "",
    alarm_name: str = "",
    raw_alarm_text: str = "",
    correlated_group_id: str = "",
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """
    Log an incident into the database.
    Returns the created incident as a dict.
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO incidents 
               (alarm_id, alarm_name, node_name, alarm_type, severity, confidence,
                root_cause, recommended_action, relevant_runbook, escalate_to,
                respond_within, mttr_started_at, raw_alarm_text, correlated_group_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alarm_id, alarm_name, node_name, alarm_type, severity, confidence,
                root_cause, recommended_action, relevant_runbook, escalate_to,
                respond_within, now, raw_alarm_text, correlated_group_id,
            ),
        )
        incident_id = cursor.lastrowid
        return get_incident_by_id(incident_id, db_path)


def get_incident_by_id(incident_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Get a single incident by its database ID."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return dict(row) if row else None


def get_incident_by_alarm_id(alarm_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Get an incident by its alarm_id."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM incidents WHERE alarm_id = ?", (alarm_id,)).fetchone()
        return dict(row) if row else None


def update_incident(
    incident_id: int,
    updates: Dict[str, Any],
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Update fields on an incident. Only provided fields are updated.
    Returns updated incident or None if not found.
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    updates["updated_at"] = now

    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [incident_id]

    with get_db(db_path) as conn:
        conn.execute(f"UPDATE incidents SET {set_clause} WHERE id = ?", values)
        return get_incident_by_id(incident_id, db_path)


def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    node_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    """List incidents with optional filters."""
    query = "SELECT * FROM incidents WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if node_name:
        query += " AND node_name = ?"
        params.append(node_name)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


# ─── Escalation CRUD ──────────────────────────────────────────────────────────

def create_escalation(
    incident_id: int,
    alarm_id: str,
    escalated_to: str,
    sla_deadline: str,
    reason: str = "",
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """Create a new escalation record."""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO escalations 
               (incident_id, alarm_id, escalated_to, sla_deadline, reason)
               VALUES (?, ?, ?, ?, ?)""",
            (incident_id, alarm_id, escalated_to, sla_deadline, reason),
        )
        row = conn.execute(
            "SELECT * FROM escalations WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_pending_escalations(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Get all pending escalations (not yet acknowledged or resolved)."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM escalations WHERE status = 'pending' ORDER BY sla_deadline ASC"
        ).fetchall()
        return [dict(row) for row in rows]


def acknowledge_escalation(escalation_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Mark an escalation as acknowledged."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE escalations SET status = 'acknowledged', acknowledged_at = ? WHERE id = ?",
            (now, escalation_id),
        )
        row = conn.execute("SELECT * FROM escalations WHERE id = ?", (escalation_id,)).fetchone()
        return dict(row) if row else None


# ─── Maintenance Windows ──────────────────────────────────────────────────────

def register_maintenance_window(
    node_name: str,
    start_time: str,
    end_time: str,
    reason: str = "",
    created_by: str = "system",
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """Register a planned maintenance window for a node."""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO maintenance_windows (node_name, start_time, end_time, reason, created_by)
               VALUES (?, ?, ?, ?, ?)""",
            (node_name, start_time, end_time, reason, created_by),
        )
        row = conn.execute(
            "SELECT * FROM maintenance_windows WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def is_in_maintenance_window(
    node_name: str,
    timestamp: Optional[str] = None,
    db_path: str = DB_PATH,
) -> bool:
    """
    Check if a node is currently in a planned maintenance window.
    Returns True if the node should be skipped for alarm processing.
    """
    if timestamp is None:
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db(db_path) as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM maintenance_windows 
               WHERE node_name = ? AND start_time <= ? AND end_time >= ?""",
            (node_name, timestamp, timestamp),
        ).fetchone()
        return row["cnt"] > 0


def get_active_maintenance_windows(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Get all currently active maintenance windows."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM maintenance_windows WHERE start_time <= ? AND end_time >= ? ORDER BY end_time ASC",
            (now, now),
        ).fetchall()
        return [dict(row) for row in rows]


# ─── Transient Alarms ─────────────────────────────────────────────────────────

def record_transient_alarm(
    alarm_id: str,
    node_name: str,
    alarm_type: str = "",
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """Record a transient alarm sighting."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO transient_alarms (alarm_id, node_name, alarm_type, first_seen)
               VALUES (?, ?, ?, ?)""",
            (alarm_id, node_name, alarm_type, now),
        )
        row = conn.execute(
            "SELECT * FROM transient_alarms WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def mark_transient_cleared(alarm_id: str, db_path: str = DB_PATH) -> None:
    """Mark a transient alarm as cleared and calculate its duration."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM transient_alarms WHERE alarm_id = ? AND cleared_at IS NULL ORDER BY first_seen DESC LIMIT 1",
            (alarm_id,),
        ).fetchone()
        if row:
            first_seen = datetime.fromisoformat(row["first_seen"].replace("Z", "+00:00"))
            cleared = datetime.fromisoformat(now.replace("Z", "+00:00"))
            duration = (cleared - first_seen).total_seconds()
            is_transient = 1 if duration < 60 else 0
            conn.execute(
                """UPDATE transient_alarms 
                   SET cleared_at = ?, duration_seconds = ?, is_transient = ?
                   WHERE id = ?""",
                (now, duration, is_transient, row["id"]),
            )


def is_transient_alarm(alarm_id: str, db_path: str = DB_PATH) -> bool:
    """Check if an alarm is known to be transient (self-cleared under 60s)."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT is_transient FROM transient_alarms WHERE alarm_id = ? AND is_transient = 1",
            (alarm_id,),
        ).fetchone()
        return row is not None


# ─── Trend Data ────────────────────────────────────────────────────────────────

def record_trend_data(
    node_name: str,
    window_start: str,
    window_end: str,
    alarm_count: int,
    p1_count: int = 0,
    p2_count: int = 0,
    severity_score: float = 0.0,
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """Record aggregated trend data for a node time window."""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO trend_data (node_name, window_start, window_end, alarm_count, p1_count, p2_count, severity_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (node_name, window_start, window_end, alarm_count, p1_count, p2_count, severity_score),
        )
        row = conn.execute(
            "SELECT * FROM trend_data WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_trend_data(
    node_name: Optional[str] = None,
    hours: int = 24,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    """Get trend data for the last N hours, optionally filtered by node."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db(db_path) as conn:
        if node_name:
            rows = conn.execute(
                "SELECT * FROM trend_data WHERE node_name = ? AND window_start >= ? ORDER BY window_start ASC",
                (node_name, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trend_data WHERE window_start >= ? ORDER BY window_start ASC",
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]


# ─── Confidence Audit ─────────────────────────────────────────────────────────

def log_confidence_audit(
    alarm_id: str,
    confidence: float,
    decision: str,
    reason: str = "",
    db_path: str = DB_PATH,
) -> Dict[str, Any]:
    """Log a low-confidence decision for human review."""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO confidence_audit (alarm_id, confidence, decision, reason)
               VALUES (?, ?, ?, ?)""",
            (alarm_id, confidence, decision, reason),
        )
        row = conn.execute(
            "SELECT * FROM confidence_audit WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)


def get_pending_review_items(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Get all confidence audit items pending human review."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM confidence_audit WHERE reviewed_at IS NULL ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]