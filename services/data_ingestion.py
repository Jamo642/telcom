"""
Data Ingestion Service: Load and index telecom datasets into ChromaDB
"""

import os
import csv
import logging
from typing import List, Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class DataIngestionService:
    """Load and ingest telecom data into vector database"""
    
    @staticmethod
    def load_incidents_csv(filepath: str) -> List[Tuple[str, Dict, str]]:
        """
        Load incidents from CSV file
        Returns list of (document_text, metadata_dict, unique_id)
        """
        logger.info(f"Loading incidents from: {filepath}")
        incidents = []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                incident_id = row.get('incident_id', f'inc_{i}')
                
                # Create full document text
                doc_text = f"""
Incident: {row.get('incident_name', '')}
Description: {row.get('description', '')}
Root Cause: {row.get('root_cause', '')}
Severity: {row.get('severity', '')}
Resolution Steps: {row.get('resolution_steps', '')}
                """.strip()
                
                metadata = {
                    'incident_id': incident_id,
                    'incident_name': row.get('incident_name', ''),
                    'severity': row.get('severity', 'Unknown'),
                    'timestamp': row.get('timestamp', ''),
                    'source': 'incidents'
                }
                
                incidents.append((doc_text, metadata, incident_id))
        
        logger.info(f"Loaded {len(incidents)} incidents")
        return incidents
    
    @staticmethod
    def load_logs(log_dir: str) -> List[Tuple[str, Dict, str]]:
        """Load log files from directory"""
        logger.info(f"Loading logs from: {log_dir}")
        logs = []
        
        log_path = Path(log_dir)
        if not log_path.exists():
            logger.warning(f"Log directory not found: {log_dir}")
            return logs
        
        for i, log_file in enumerate(log_path.glob("*.log")):
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            metadata = {
                'log_file': log_file.name,
                'source': 'logs'
            }
            
            log_id = f"log_{log_file.stem}_{i}"
            logs.append((content, metadata, log_id))
        
        logger.info(f"Loaded {len(logs)} log files")
        return logs
    
    @staticmethod
    def load_manuals(manual_dir: str) -> List[Tuple[str, Dict, str]]:
        """Load troubleshooting manuals from directory"""
        logger.info(f"Loading manuals from: {manual_dir}")
        manuals = []
        
        manual_path = Path(manual_dir)
        if not manual_path.exists():
            logger.warning(f"Manual directory not found: {manual_dir}")
            return manuals
        
        for i, manual_file in enumerate(manual_path.glob("*.md")):
            with open(manual_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split into sections for better retrieval
            sections = content.split("---")
            
            for j, section in enumerate(sections):
                if section.strip():
                    metadata = {
                        'manual_file': manual_file.name,
                        'source': 'manuals',
                        'section': j
                    }
                    
                    manual_id = f"manual_{manual_file.stem}_section_{j}"
                    manuals.append((section.strip(), metadata, manual_id))
        
        logger.info(f"Loaded {len(manuals)} manual sections")
        return manuals
    
    @staticmethod
    def prepare_documents_for_ingestion(
        incidents_csv: str,
        logs_dir: str,
        manuals_dir: str
    ) -> Tuple[List[str], List[Dict], List[str]]:
        """
        Load all documents and prepare for ingestion
        Returns: (documents_list, metadatas_list, ids_list)
        """
        all_documents = []
        all_metadatas = []
        all_ids = []
        
        # Load incidents
        incidents = DataIngestionService.load_incidents_csv(incidents_csv)
        for doc, meta, doc_id in incidents:
            all_documents.append(doc)
            all_metadatas.append(meta)
            all_ids.append(doc_id)
        
        # Load logs
        logs = DataIngestionService.load_logs(logs_dir)
        for doc, meta, doc_id in logs:
            all_documents.append(doc)
            all_metadatas.append(meta)
            all_ids.append(doc_id)
        
        # Load manuals
        manuals = DataIngestionService.load_manuals(manuals_dir)
        for doc, meta, doc_id in manuals:
            all_documents.append(doc)
            all_metadatas.append(meta)
            all_ids.append(doc_id)
        
        logger.info(f"Total documents prepared for ingestion: {len(all_documents)}")
        return all_documents, all_metadatas, all_ids
