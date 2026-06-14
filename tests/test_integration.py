"""
Integration tests for Telecom AI Incident Copilot
"""

import pytest
import requests
import json
from typing import Dict, Any

BACKEND_URL = "http://localhost:8000"


class TestBackendHealth:
    """Test backend connectivity"""
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = requests.get(f"{BACKEND_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_stats_endpoint(self):
        """Test stats endpoint"""
        response = requests.get(f"{BACKEND_URL}/stats")
        assert response.status_code == 200


class TestIncidentAnalysis:
    """Test incident analysis workflow"""
    
    @classmethod
    def setup_class(cls):
        """Initialize database before tests"""
        response = requests.post(
            f"{BACKEND_URL}/initialize",
            json={
                "incidents_csv_path": "/data/incidents/incidents.csv",
                "logs_dir_path": "/data/logs",
                "manuals_dir_path": "/data/manuals"
            }
        )
        assert response.status_code == 200
    
    def test_analyze_packet_loss_incident(self):
        """Test analyzing packet loss incident"""
        incident = "High packet loss detected on Node B12. Users report degraded service quality."
        
        response = requests.post(
            f"{BACKEND_URL}/analyze-incident",
            json={
                "incident_description": incident,
                "top_k_retrieval": 5,
                "temperature": 0.7
            },
            timeout=120
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "incident_id" in data
        assert "analysis" in data
        assert "metrics" in data
        assert "retrieved_context" in data
        
        # Verify analysis structure
        analysis = data["analysis"]
        assert "root_cause" in analysis
        assert "severity" in analysis
        assert "recommended_actions" in analysis
        
        # Verify metrics
        metrics = data["metrics"]
        assert "latency" in metrics
        assert "retrieval" in metrics
        assert "response_quality" in metrics
    
    def test_analyze_bgp_incident(self):
        """Test analyzing BGP incident"""
        incident = "BGP is taking 180 seconds to converge after link failure. Network topology change in Region A."
        
        response = requests.post(
            f"{BACKEND_URL}/analyze-incident",
            json={"incident_description": incident}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "analysis" in data
        assert len(data["retrieved_context"]) > 0
    
    def test_analyze_dns_incident(self):
        """Test analyzing DNS incident"""
        incident = "DNS queries timing out in 40% of requests. Users unable to resolve domain names."
        
        response = requests.post(
            f"{BACKEND_URL}/analyze-incident",
            json={"incident_description": incident}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        analysis = data["analysis"]
        assert analysis.get("severity") in ["Critical", "High", "Medium", "Low", None]


class TestRetrieval:
    """Test retrieval functionality"""
    
    def test_retrieval_returns_relevant_documents(self):
        """Test that retrieval returns relevant documents"""
        incident = "Packet loss on interface"
        
        response = requests.post(
            f"{BACKEND_URL}/analyze-incident",
            json={"incident_description": incident}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Should retrieve relevant documents
        retrieved = data["retrieved_context"]
        assert len(retrieved) > 0
        
        # Retrieved documents should have similarity scores
        for doc in retrieved:
            assert "similarity" in doc
            assert 0 <= doc["similarity"] <= 1


class TestMetrics:
    """Test metrics collection"""
    
    def test_metrics_endpoint(self):
        """Test metrics aggregation endpoint"""
        # First, run some analyses
        for i in range(3):
            requests.post(
                f"{BACKEND_URL}/analyze-incident",
                json={
                    "incident_description": f"Test incident {i}",
                    "temperature": 0.7
                },
                timeout=120
            )
        
        # Get aggregated metrics
        response = requests.get(f"{BACKEND_URL}/metrics")
        assert response.status_code == 200
        
        data = response.json()
        metrics = data.get("metrics", {})
        
        # Should have aggregated metrics
        assert "request_count" in metrics
        assert "avg_latency_ms" in metrics
        assert "avg_quality" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
