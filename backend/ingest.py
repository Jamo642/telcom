"""
Document and Alarm Log Ingestion for TeleNOC AI

Handles ingestion of telecom alarm logs, network documents, and runbooks into:
- ChromaDB vector store for semantic search
- SQLite database for incident tracking
- OPEA RAG pipeline for context retrieval

Supports batch loading from JSON, CSV, and text files.
"""

import os
import json
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_DATA_DIR = "/data"
DEFAULT_ALARMS_FILE = "/data/sample_alarms.json"


def ingest_alarm_logs(
    filepath: str = DEFAULT_ALARMS_FILE,
    db_path: str = "/data/telenoc.db",
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
    }


def ingest_documents_to_vector_db(
    document_dir: str = DEFAULT_DATA_DIR,
    collection_name: str = "telecom_knowledge_base",
) -> Dict[str, Any]:
    """
    Ingest telecom documents (runbooks, manuals, SOPs) into ChromaDB.
    
    Supported file types: .md, .txt, .csv, .json
    Each document is chunked and embedded for semantic search.
    """
    logger.info(f"Ingesting documents from {document_dir} into ChromaDB")

    doc_dir = Path(document_dir)
    if not doc_dir.exists():
        return {"status": "error", "error": f"Directory not found: {document_dir}"}

    # Collect all documents
    documents = []
    metadatas = []
    ids = []

    # Recursively find all supported files
    for filepath in doc_dir.rglob("*"):
        if filepath.suffix not in (".md", ".txt", ".csv", ".json"):
            continue
        if filepath.name == "sample_alarms.json":
            continue  # Skip alarm data, handled separately

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                continue

            doc_id = f"{filepath.stem}_{filepath.stat().st_mtime_ns}"
            metadata = {
                "source": str(filepath.relative_to(doc_dir)),
                "type": filepath.suffix[1:],
                "ingested_at": datetime.utcnow().isoformat(),
            }

            # For long documents, chunk into sections
            if len(content) > 1000:
                sections = _chunk_document(content, filepath.suffix)
                for i, section in enumerate(sections):
                    section_id = f"{doc_id}_section_{i}"
                    section_meta = {**metadata, "section": i}
                    documents.append(section)
                    metadatas.append(section_meta)
                    ids.append(section_id)
            else:
                documents.append(content)
                metadatas.append(metadata)
                ids.append(doc_id)

        except Exception as e:
            logger.warning(f"Error reading {filepath}: {e}")
            continue

    if not documents:
        return {"status": "success", "documents_ingested": 0, "message": "No documents found"}

    # Use OPEA embedding service if available, otherwise use local embedding
    try:
        from services.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()
        logger.info(f"Computing embeddings for {len(documents)} documents...")
        embeddings = embedding_service.embed_batch(documents)
        embeddings = [emb.tolist() for emb in embeddings]
    except (ImportError, Exception) as e:
        logger.warning(f"Embedding service unavailable: {e}")
        embeddings = None

    # Store to ChromaDB
    try:
        from services.retrieval_service import get_retrieval_service
        retrieval = get_retrieval_service(collection_name=collection_name)
        retrieval.add_documents(documents, metadatas, ids, embeddings=embeddings)
        count = len(documents)
        logger.info(f"Ingested {count} documents into {collection_name}")
        return {"status": "success", "documents_ingested": count}
    except (ImportError, Exception) as e:
        logger.error(f"Failed to store documents: {e}")
        return {"status": "error", "error": str(e), "documents_extracted": len(documents)}


def _chunk_document(content: str, file_type: str) -> List[str]:
    """
    Chunk a long document into smaller sections.
    Uses markdown headers, paragraphs, or fixed-size chunks.
    """
    chunks = []

    if file_type == ".md":
        # Split by markdown headers
        import re
        sections = re.split(r'\n(?=##?\s)', content)
        for section in sections:
            if section.strip():
                chunks.append(section.strip())
    else:
        # Split by paragraphs
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) < 500:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para
        if current_chunk:
            chunks.append(current_chunk)

    # Ensure minimum chunk size
    return [c for c in chunks if len(c) > 50]


def load_sample_alarms(
    filepath: str = DEFAULT_ALARMS_FILE,
    db_path: str = "/data/telenoc.db",
) -> Dict[str, Any]:
    """
    Quick loader for sample alarm data.
    Calls ingest_alarm_logs with default paths.
    """
    return ingest_alarm_logs(filepath=filepath, db_path=db_path)