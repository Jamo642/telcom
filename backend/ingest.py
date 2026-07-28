"""
Document and Alarm Log Ingestion for TeleNOC AI

Handles ingestion of telecom alarm logs, network documents, and runbooks into:
- OPEA dataprep for document preparation and indexing
- SQLite database for incident tracking
- OPEA RAG pipeline for context retrieval

Supports batch loading from JSON, CSV, and text files.
"""

import os
import json
import logging
import tempfile
from urllib import error, request
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_DATA_DIR = "/data"
DEFAULT_ALARMS_FILE = "/data/sample_alarms.json"
DATAPREP_ENDPOINT = os.environ.get("DATAPREP_ENDPOINT", "http://dataprep:6007/v1/dataprep")


def _upload_file_to_dataprep(filepath: str, collection_name: str = "telecom_knowledge_base") -> Dict[str, Any]:
    """Upload a file to the OPEA dataprep service using multipart/form-data."""
    boundary = "----TeleNOCBoundary7MA4YWxkTrZu0gW"
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as file_handle:
        file_data = file_handle.read()

    parts = []
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(
        (
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    payload = b"".join(parts)
    http_request = request.Request(
        DATAPREP_ENDPOINT,
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=120) as response:
            content = response.read().decode("utf-8")
            try:
                result = json.loads(content)
            except Exception:
                result = {"raw": content}
            result.setdefault("status", "success")
            result["collection_name"] = collection_name
            return result
    except error.HTTPError as exc:
        return {"status": "error", "error": exc.reason, "code": exc.code}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def ingest_alarm_logs(
    filepath: str = DEFAULT_ALARMS_FILE,
    db_path: str = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db"),
    batch_size: int = 10,
) -> Dict[str, Any]:
    """
    Ingest alarm logs from a JSON file into the system.
    Processes each alarm through the diagnosis pipeline and stores results.
    
    Args:
        filepath: Path to JSON file containing alarm logs
        db_path: Path to SQLite database
        batch_size: Number of alarms to process before yielding
    
    Returns:
        Dict with ingestion statistics
    """
    logger.info(f"Ingesting alarm logs from {filepath}")

    if not os.path.exists(filepath):
        return {
            "status": "error",
            "error": f"File not found: {filepath}",
            "ingested": 0,
        }

    # OPEA dataprep handles the raw alarm file ingestion for downstream RAG use.
    dataprep_result = _upload_file_to_dataprep(filepath, collection_name="telecom_alarms")
    if dataprep_result.get("status") == "error":
        logger.warning("OPEA dataprep upload failed for alarm logs: %s", dataprep_result)

    # Load alarms
    try:
        with open(filepath, "r") as f:
            content = f.read().strip()
            if content.startswith("["):
                alarms = json.loads(content)
            else:
                # Try line-by-line JSON (JSONL format)
                alarms = [json.loads(line) for line in content.split("\n") if line.strip()]
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "error": f"Invalid JSON: {e}",
            "ingested": 0,
        }

    logger.info(f"Loaded {len(alarms)} alarms from file")

    # Initialize database
    try:
        from backend.database import init_db
        init_db(db_path)
    except ImportError:
        logger.warning("Database module not available, skipping DB init")

    # Process each alarm
    ingested = 0
    errors = 0
    results = []

    for alarm in alarms:
        try:
            from backend.agent import diagnose_alarm

            # Get recent alarms for context
            recent_alarms = results[-5:] if results else None

            result = diagnose_alarm(
                alarm=alarm,
                recent_alarms=recent_alarms,
                db_path=db_path,
            )
            results.append(result)
            ingested += 1

            # Process in batches
            if len(results) >= batch_size:
                logger.info(f"Processed {ingested}/{len(alarms)} alarms")
                results = []

        except Exception as e:
            logger.error(f"Error processing alarm {alarm.get('alarm_id', 'unknown')}: {e}")
            errors += 1

    logger.info(f"Ingestion complete: {ingested} ingested, {errors} errors")
    return {
        "status": "success",
        "ingested": ingested,
        "errors": errors,
        "total_in_file": len(alarms),
        "dataprep": dataprep_result,
    }


def ingest_documents_to_vector_db(
    document_dir: str = DEFAULT_DATA_DIR,
    collection_name: str = "telecom_knowledge_base",
) -> Dict[str, Any]:
    """
    Ingest telecom documents (runbooks, manuals, SOPs) through OPEA dataprep.
    
    Supported file types: .md, .txt, .csv, .json
    Each document is uploaded to OPEA dataprep for downstream embedding and retrieval.
    """
    logger.info(f"Ingesting documents from {document_dir} through OPEA dataprep")

    doc_dir = Path(document_dir)
    if not doc_dir.exists():
        return {"status": "error", "error": f"Directory not found: {document_dir}"}

    uploaded = 0
    errors = 0
    dataprep_results = []

    # Recursively find all supported files and send each one to OPEA dataprep.
    for filepath in doc_dir.rglob("*"):
        if filepath.suffix not in (".md", ".txt", ".csv", ".json"):
            continue
        if filepath.name == "sample_alarms.json":
            continue  # Skip alarm data, handled separately

        try:
            result = _upload_file_to_dataprep(str(filepath), collection_name=collection_name)
            dataprep_results.append({"file": str(filepath), "result": result})
            if result.get("status") == "error":
                errors += 1
            else:
                uploaded += 1
        except Exception as e:
            logger.warning(f"Error reading {filepath}: {e}")
            errors += 1

    if not uploaded and not dataprep_results:
        return {"status": "success", "documents_ingested": 0, "message": "No documents found"}

    logger.info(f"Uploaded {uploaded} documents through OPEA dataprep")
    return {
        "status": "success",
        "documents_ingested": uploaded,
        "errors": errors,
        "collection_name": collection_name,
        "dataprep": dataprep_results,
    }


def load_sample_alarms(
    filepath: str = DEFAULT_ALARMS_FILE,
    db_path: str = os.environ.get("TELENOC_DB_PATH", "/data/telenoc.db"),
) -> Dict[str, Any]:
    """
    Quick loader for sample alarm data.
    Calls ingest_alarm_logs with default paths.
    """
    return ingest_alarm_logs(filepath=filepath, db_path=db_path)