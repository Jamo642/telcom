"""
Evaluation Service: Compute performance metrics
"""

import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class EvaluationService:
    """Compute system performance metrics"""
    
    def __init__(self):
        self.metrics_history = []
    
    def evaluate_retrieval(self, retrieved_docs: list, top_k: int = 5) -> Dict[str, Any]:
        """
        Evaluate retrieval quality
        Args:
            retrieved_docs: List of retrieved documents with similarity scores
            top_k: How many results to consider
        Returns:
            Retrieval metrics
        """
        if not retrieved_docs:
            return {
                "retrieval_count": 0,
                "avg_similarity": 0.0,
                "max_similarity": 0.0,
                "min_similarity": 0.0,
                "quality_score": 0.0
            }
        
        similarities = [doc.get('similarity', 0) for doc in retrieved_docs[:top_k]]
        
        avg_sim = sum(similarities) / len(similarities) if similarities else 0
        max_sim = max(similarities) if similarities else 0
        min_sim = min(similarities) if similarities else 0
        
        # Quality score: average of similarities
        quality = avg_sim
        
        return {
            "retrieval_count": len(retrieved_docs),
            "avg_similarity": round(avg_sim, 3),
            "max_similarity": round(max_sim, 3),
            "min_similarity": round(min_sim, 3),
            "quality_score": round(quality, 3)
        }
    
    def evaluate_latency(self, start_time: float, end_time: float) -> Dict[str, Any]:
        """
        Evaluate latency
        Args:
            start_time: Unix timestamp when request started
            end_time: Unix timestamp when request ended
        Returns:
            Latency metrics in milliseconds
        """
        latency_ms = (end_time - start_time) * 1000
        
        return {
            "latency_ms": round(latency_ms, 2),
            "latency_sec": round(latency_ms / 1000, 3)
        }
    
    def evaluate_response_quality(self, structured_response: Dict) -> Dict[str, Any]:
        """
        Evaluate quality of structured response
        Args:
            structured_response: Structured output from LLM
        Returns:
            Quality metrics
        """
        quality_score = 0.0
        completeness = 0.0
        
        required_fields = ["root_cause", "evidence", "recommended_actions", "severity", "confidence_score"]
        present_fields = sum(1 for field in required_fields if field in structured_response)
        completeness = present_fields / len(required_fields)
        
        # Extract confidence score
        confidence = structured_response.get("confidence_score", 0.5)
        
        # Overall quality = average of completeness and confidence
        quality_score = (completeness + confidence) / 2
        
        return {
            "completeness_score": round(completeness, 3),
            "confidence_score": round(confidence, 3),
            "overall_quality": round(quality_score, 3),
            "has_root_cause": "root_cause" in structured_response,
            "has_evidence": "evidence" in structured_response and len(structured_response.get("evidence", [])) > 0,
            "has_actions": "recommended_actions" in structured_response and len(structured_response.get("recommended_actions", [])) > 0,
            "severity_valid": structured_response.get("severity", "") in ["Critical", "High", "Medium", "Low"]
        }
    
    def estimate_retrieval_accuracy(self, retrieved_docs: list, incident_description: str) -> float:
        """
        Estimate retrieval accuracy (rule-based heuristic)
        If top doc has similarity > 0.7, likely accurate
        Args:
            retrieved_docs: Retrieved documents
            incident_description: Original incident description
        Returns:
            Estimated accuracy (0-1)
        """
        if not retrieved_docs:
            return 0.0
        
        top_similarity = retrieved_docs[0].get('similarity', 0)
        
        # Heuristic: if top similarity > 0.7, accuracy ~85%, otherwise ~50%
        if top_similarity > 0.7:
            accuracy = 0.85
        elif top_similarity > 0.5:
            accuracy = 0.65
        else:
            accuracy = 0.40
        
        return round(accuracy, 3)
    
    def create_metrics_report(
        self,
        retrieval_metrics: Dict,
        latency_metrics: Dict,
        quality_metrics: Dict,
        retrieval_accuracy: float
    ) -> Dict[str, Any]:
        """
        Create comprehensive metrics report
        Args:
            retrieval_metrics: From evaluate_retrieval()
            latency_metrics: From evaluate_latency()
            quality_metrics: From evaluate_response_quality()
            retrieval_accuracy: From estimate_retrieval_accuracy()
        Returns:
            Comprehensive metrics report
        """
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "retrieval": retrieval_metrics,
            "latency": latency_metrics,
            "response_quality": quality_metrics,
            "retrieval_accuracy": retrieval_accuracy,
            "overall_score": round(
                (quality_metrics.get("overall_quality", 0) + retrieval_accuracy) / 2,
                3
            )
        }
        
        self.metrics_history.append(report)
        return report
    
    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics from history"""
        if not self.metrics_history:
            return {}
        
        latencies = [m["latency"]["latency_ms"] for m in self.metrics_history]
        qualities = [m["response_quality"]["overall_quality"] for m in self.metrics_history]
        accuracies = [m["retrieval_accuracy"] for m in self.metrics_history]
        
        return {
            "request_count": len(self.metrics_history),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
            "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if len(latencies) > 1 else latencies[0],
            "avg_quality": round(sum(qualities) / len(qualities), 3),
            "avg_retrieval_accuracy": round(sum(accuracies) / len(accuracies), 3),
            "avg_overall_score": round(sum([m["overall_score"] for m in self.metrics_history]) / len(self.metrics_history), 3)
        }
    
    def save_metrics(self, filepath: str) -> None:
        """Save metrics history to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.metrics_history, f, indent=2)
        logger.info(f"Metrics saved to {filepath}")


# Singleton instance
_evaluation_service = None


def get_evaluation_service() -> EvaluationService:
    """Get or create evaluation service singleton"""
    global _evaluation_service
    if _evaluation_service is None:
        _evaluation_service = EvaluationService()
    return _evaluation_service
