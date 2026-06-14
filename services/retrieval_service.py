"""
Retrieval Service: Semantic search and ranking using ChromaDB
"""

import os
import numpy as np
import chromadb
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, persist_dir: str = "/data/chroma_db", collection_name: str = "telecom_incidents"):
        """
        Initialize retrieval service with ChromaDB
        Args:
            persist_dir: Directory to persist ChromaDB data
            collection_name: Name of the collection
        """
        logger.info(f"Initializing ChromaDB with persist_dir: {persist_dir}")
        
        # Create persist directory if not exists
        os.makedirs(persist_dir, exist_ok=True)
        
        # Initialize ChromaDB client with persistence (new API)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection_name = collection_name
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        logger.info(f"ChromaDB collection '{collection_name}' initialized")

    def add_documents(self, documents: List[str], metadatas: List[Dict], ids: List[str], embeddings: Optional[List[List[float]]] = None) -> None:
        """
        Add documents to the vector database
        Args:
            documents: List of text documents
            metadatas: List of metadata dicts (must match document count)
            ids: List of unique IDs (must match document count)
            embeddings: Optional pre-computed embeddings (if None, ChromaDB will compute them)
        """
        logger.info(f"Adding {len(documents)} documents to collection")
        
        add_kwargs = {
            "documents": documents,
            "metadatas": metadatas,
            "ids": ids
        }
        
        # If embeddings are provided, use them (prevents ChromaDB from downloading ONNX models)
        if embeddings is not None:
            add_kwargs["embeddings"] = embeddings
        
        self.collection.add(**add_kwargs)
        logger.info(f"Successfully added {len(documents)} documents")

    def search(self, query: str, top_k: int = 5, similarity_threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Semantic search for similar documents
        Args:
            query: Search query text
            top_k: Number of top results to return
            similarity_threshold: Minimum similarity score (0-1)
        Returns:
            List of results with document content, metadata, and similarity score
        """
        logger.info(f"Searching for: '{query}' (top_k={top_k})")
        
        # Import embedding service here to avoid circular imports
        from services.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()
        
        # Embed the query using the same model used during document ingestion
        query_embedding = embedding_service.embed_text(query).tolist()
        
        # Use query_embeddings instead of query_texts to ensure the same embedding model is used
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format results
        formatted_results = []
        if results and results['documents'] and len(results['documents']) > 0:
            for i, doc in enumerate(results['documents'][0]):
                similarity = results['distances'][0][i] if results['distances'] else 0
                # ChromaDB returns distances; convert to similarity (1 - distance for cosine)
                similarity_score = 1 - similarity
                
                if similarity_score >= similarity_threshold:
                    formatted_results.append({
                        'document': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'id': results['ids'][0][i] if results['ids'] else '',
                        'similarity': float(similarity_score)
                    })
        
        logger.info(f"Found {len(formatted_results)} relevant documents")
        return formatted_results

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        count = self.collection.count()
        return {
            'collection_name': self.collection_name,
            'document_count': count
        }

    def clear_collection(self) -> None:
        """Clear all documents from collection (for testing)"""
        logger.warning("Clearing entire collection")
        self.collection.delete(where={})

    def delete_collection(self) -> None:
        """Delete the entire collection"""
        logger.warning(f"Deleting collection: {self.collection_name}")
        self.client.delete_collection(name=self.collection_name)


# Singleton instance
_retrieval_service = None


def get_retrieval_service(persist_dir: str = "/data/chroma_db", collection_name: str = "telecom_incidents") -> RetrievalService:
    """Get or create retrieval service singleton"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(persist_dir, collection_name)
    return _retrieval_service
