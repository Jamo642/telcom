"""
Retrieval Service: OPEA retriever-redis REST client.
"""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from urllib import error, parse, request

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        retriever_host: Optional[str] = None,
        retriever_port: Optional[int] = None,
        embedding_endpoint: Optional[str] = None,
        collection_name: str = "telecom_incidents",
    ):
        """Initialize the OPEA retriever client."""
        self.retriever_host = retriever_host or os.environ.get("RETRIEVER_SERVICE_HOST", "retriever")
        self.retriever_port = int(retriever_port or os.environ.get("RETRIEVER_SERVICE_PORT", "7000"))
        self.embedding_endpoint = embedding_endpoint or os.environ.get("TEI_EMBEDDING_ENDPOINT", "http://embedding:6000")
        self.collection_name = collection_name
        self.base_url = f"http://{self.retriever_host}:{self.retriever_port}"
        logger.info("Initializing OPEA retriever at %s", self.base_url)

    def _health_url(self) -> str:
        return f"{self.base_url}/health"

    def _embedding_url(self) -> str:
        return self.embedding_endpoint.rstrip("/")

    def _post_json(self, url: str, payload: Dict[str, Any], timeout: int) -> Optional[Dict[str, Any]]:
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            logger.debug("HTTP error for %s: %s", url, exc)
        except Exception as exc:
            logger.debug("Request error for %s: %s", url, exc)
        return None

    def _post_multipart(self, url: str, file_path: str, field_name: str = "file", timeout: int = 120) -> Dict[str, Any]:
        boundary = "----TeleNOCBoundary7MA4YWxkTrZu0gW"
        filename = os.path.basename(file_path)
        mime_type = "application/octet-stream"
        with open(file_path, "rb") as file_handle:
            file_data = file_handle.read()
        parts = []
        parts.append(f"--{boundary}\r\n".encode("utf-8"))
        parts.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(file_data)
        parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        http_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=timeout) as response:
                content = response.read().decode("utf-8")
                try:
                    return json.loads(content)
                except Exception:
                    return {"status": response.status, "text": content}
        except error.HTTPError as exc:
            return {"status": exc.code, "error": exc.reason}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _get_query_embedding(self, text: str) -> Optional[List[float]]:
        """Fetch an embedding from the OPEA TEI service."""
        # OPEA embedding-tei provides the vector used by the OPEA retriever.
        payloads = [
            {"text": text},
            {"input": text},
            {"inputs": [text]},
        ]
        endpoints = ["/v1/embeddings", "/embeddings", "/v1/embed", "/embed"]

        for endpoint in endpoints:
            for payload in payloads:
                try:
                    data = self._post_json(f"{self._embedding_url()}{endpoint}", payload, timeout=30)
                    if not data:
                        continue
                    vector = self._extract_embedding_vector(data)
                    if vector:
                        return vector
                except Exception as exc:
                    logger.debug("Embedding call failed for %s: %s", endpoint, exc)
                    continue

        try:
            from services.embedding_service import get_embedding_service

            logger.warning("Falling back to local embedding service for query vector")
            embedding_service = get_embedding_service()
            return embedding_service.embed_text(text).tolist()
        except Exception as exc:
            logger.error("Embedding lookup failed: %s", exc)
            return None

    def _extract_embedding_vector(self, data: Any) -> Optional[List[float]]:
        if isinstance(data, dict):
            if isinstance(data.get("embedding"), list):
                return data["embedding"]
            if isinstance(data.get("data"), list) and data["data"]:
                first = data["data"][0]
                if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                    return first["embedding"]
                if isinstance(first, list):
                    return first
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, list):
                return first
            if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                return first["embedding"]
        return None

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict],
        ids: List[str],
        embeddings: Optional[List[List[float]]] = None,
    ) -> Dict[str, Any]:
        """Upload documents to the OPEA dataprep service as a multipart file."""
        logger.info("Uploading %s documents to OPEA dataprep", len(documents))
        records = []
        for index, document in enumerate(documents):
            record = {
                "id": ids[index] if index < len(ids) else f"doc_{index}",
                "document": document,
                "metadata": metadatas[index] if index < len(metadatas) else {},
            }
            if embeddings is not None and index < len(embeddings):
                record["embedding"] = embeddings[index]
            records.append(record)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp_file:
            for record in records:
                tmp_file.write(json.dumps(record) + "\n")
            tmp_path = tmp_file.name

        try:
            response = self._post_multipart(f"{self.base_url}/v1/dataprep", tmp_path, timeout=120)
            logger.info("OPEA dataprep accepted %s documents", len(documents))
            return response
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def search(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Search OPEA retriever-redis using the query text and its embedding."""
        logger.info("Searching OPEA retriever for query: %s", query)
        query_embedding = self._get_query_embedding(query)
        payload = {
            "text": query,
            "embedding": query_embedding or [],
            "search_params": {"k": top_k},
        }

        try:
            data = self._post_json(f"{self.base_url}/v1/retrieval", payload, timeout=60)
            if data is None:
                raise RuntimeError("No response from OPEA retriever")
        except Exception as exc:
            logger.error("OPEA retriever request failed: %s", exc)
            return []

        results = self._normalize_results(data, similarity_threshold)
        logger.info("Found %s relevant documents via OPEA retriever", len(results))
        return results

    def _normalize_results(
        self,
        data: Any,
        similarity_threshold: float,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            for key in ("results", "documents", "matches", "items", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
        elif isinstance(data, list):
            candidates.extend(data)

        formatted_results: List[Dict[str, Any]] = []
        for index, item in enumerate(candidates):
            if not isinstance(item, dict):
                continue
            score = item.get("score", item.get("similarity", item.get("distance", 0)))
            try:
                similarity = float(score)
            except (TypeError, ValueError):
                similarity = 0.0

            if "distance" in item and similarity <= 1.0:
                similarity = 1.0 - similarity

            if similarity < similarity_threshold:
                continue

            formatted_results.append(
                {
                    "document": item.get("document", item.get("text", item.get("content", ""))),
                    "metadata": item.get("metadata", {}),
                    "id": item.get("id", f"result_{index}"),
                    "similarity": float(similarity),
                }
            )
        return formatted_results

    def get_collection_stats(self) -> Dict[str, Any]:
        """Return OPEA service availability and configured target collection name."""
        try:
            http_request = request.Request(self._health_url(), method="GET")
            with request.urlopen(http_request, timeout=10) as response:
                healthy = response.status == 200
        except Exception:
            healthy = False
        return {
            "collection_name": self.collection_name,
            "service": "opea-retriever-redis",
            "healthy": healthy,
            "base_url": self.base_url,
        }

    def clear_collection(self) -> None:
        """OPEA retriever does not expose direct collection deletion here."""
        logger.warning("Clear collection is not implemented for OPEA retriever-redis")

    def delete_collection(self) -> None:
        """OPEA retriever does not expose direct collection deletion here."""
        logger.warning("Delete collection is not implemented for OPEA retriever-redis")


_retrieval_service = None


def get_retrieval_service(
    persist_dir: str = "/data/chroma_db",
    collection_name: str = "telecom_incidents",
) -> RetrievalService:
    """Get or create the OPEA retrieval service singleton."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(collection_name=collection_name)
    return _retrieval_service
