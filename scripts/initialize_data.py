"""
Initialize vector database with telecom data
Run this after services are started
"""

import sys
import os
import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
MAX_RETRIES = 30
RETRY_DELAY = 2


def wait_for_backend():
    """Wait for backend to be ready"""
    logger.info(f"Waiting for backend at {BACKEND_URL}...")
    
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(f"{BACKEND_URL}/health", timeout=5)
            if response.status_code == 200:
                logger.info("✅ Backend is ready")
                return True
        except:
            pass
        
        logger.info(f"Waiting... ({attempt + 1}/{MAX_RETRIES})")
        time.sleep(RETRY_DELAY)
    
    logger.error("❌ Backend did not become ready in time")
    return False


def initialize_database():
    """Initialize vector database"""
    logger.info("Initializing vector database...")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/initialize",
            json={
                "incidents_csv_path": "/data/incidents/incidents.csv",
                "logs_dir_path": "/data/logs",
                "manuals_dir_path": "/data/manuals"
            },
            timeout=120
        )
        
        result = response.json()
        
        if "error" in result:
            logger.error(f"Initialization error: {result['error']}")
            return False
        
        doc_count = result.get("document_count", 0)
        logger.info(f"✅ Database initialized with {doc_count} documents")
        return True
    
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        return False


def main():
    if not wait_for_backend():
        sys.exit(1)
    
    if not initialize_database():
        sys.exit(1)
    
    logger.info("✅ Initialization complete!")


if __name__ == "__main__":
    main()
