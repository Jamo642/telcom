"""
Streamlit Frontend for Telecom AI Incident Copilot
"""

import streamlit as st
import requests
import json
import time
from datetime import datetime
from typing import Dict, Any
import pandas as pd

# Configure page
st.set_page_config(
    page_title="Telecom AI Incident Copilot",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .severity-critical { color: #d32f2f; font-weight: bold; }
    .severity-high { color: #f57c00; font-weight: bold; }
    .severity-medium { color: #fbc02d; font-weight: bold; }
    .severity-low { color: #388e3c; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Constants
import os
BACKEND_URL = os.getenv('BACKEND_URL', 'http://backend:8000')
SIDEBAR_DEMO_INCIDENTS = [
    {
        "name": "High packet loss on Node B12",
        "description": "Users report degraded service quality with high packet loss on Node B12 in the eastern region. RTT increased from 15ms to 45ms. Impact: approximately 5000 users affected."
    },
    {
        "name": "BGP Route Convergence Delay",
        "description": "BGP is taking 180 seconds to converge after a link failure in Region A. Network topology change causing delayed prefix advertisements. This exceeds our SLA of 60 seconds."
    },
    {
        "name": "DNS Resolution Timeout",
        "description": "DNS queries are timing out in 40% of requests. Users unable to resolve domain names properly. Service degradation reported in multiple regions."
    },
    {
        "name": "Disk Space Critical on Router",
        "description": "Router-03 disk usage at 95%. System may crash if additional logs are written. Need immediate action to clear space and prevent service interruption."
    },
    {
        "name": "High CPU on BNG",
        "description": "Broadband Network Gateway (BNG-East) CPU utilization spiking to 85-95% during peak hours. Causing connection timeouts and call failures."
    }
]


def check_backend_health():
    """Check if backend is available"""
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def initialize_vector_db():
    """Initialize vector database with data"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/initialize",
            json={
                "incidents_csv_path": "/data/incidents/incidents.csv",
                "logs_dir_path": "/data/logs",
                "manuals_dir_path": "/data/manuals"
            },
            timeout=60
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def analyze_incident(incident_description: str) -> Dict[str, Any]:
    """Call backend to analyze incident"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/analyze-incident",
            json={
                "incident_description": incident_description,
                "top_k_retrieval": 5,
                "temperature": 0.7
            },
            timeout=120
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Backend error: {response.status_code}"}
    
    except requests.Timeout:
        return {"error": "Request timed out. Backend may be processing large incident."}
    except Exception as e:
        return {"error": str(e)}


def get_system_stats():
    """Get system statistics"""
    try:
        response = requests.get(f"{BACKEND_URL}/stats", timeout=5)
        return response.json()
    except:
        return {}


def format_severity(severity: str) -> str:
    """Format severity level with styling"""
    severity_class = f"severity-{severity.lower()}"
    return f'<span class="{severity_class}">{severity}</span>'


def display_analysis_result(result: Dict[str, Any]):
    """Display incident analysis result"""
    
    if "error" in result:
        st.error(f"❌ Error: {result['error']}")
        return
    
    # Extract data
    incident_id = result.get("incident_id", "N/A")
    analysis = result.get("analysis", {})
    metrics = result.get("metrics", {})
    retrieved_context = result.get("retrieved_context", [])
    
    st.success("✅ Analysis Complete!")
    
    # 1. INCIDENT REPORT SECTION
    st.markdown("---")
    st.markdown("## 📋 Incident Report")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Incident ID", incident_id[-8:])
    with col2:
        severity = analysis.get("severity", "Unknown")
        severity_color = "🔴" if severity == "Critical" else "🟠" if severity == "High" else "🟡" if severity == "Medium" else "🟢"
        st.metric("Severity", f"{severity_color} {severity}")
    with col3:
        confidence = analysis.get("confidence_score", 0)
        st.metric("Confidence", f"{confidence:.0%}")
    
    # Root Cause Analysis
    st.subheader("Root Cause Analysis")
    root_cause = analysis.get("root_cause", "Unable to determine")
    st.write(root_cause)
    
    # Evidence
    if "evidence" in analysis:
        st.subheader("Evidence")
        evidence_list = analysis.get("evidence", [])
        if isinstance(evidence_list, list):
            for i, evidence in enumerate(evidence_list, 1):
                st.write(f"• {evidence}")
        else:
            st.write(evidence_list)
    
    # Recommended Actions
    st.subheader("Recommended Actions")
    actions = analysis.get("recommended_actions", [])
    if isinstance(actions, list):
        for action in actions:
            if isinstance(action, dict):
                step = action.get("step", "")
                action_text = action.get("action", "")
                rationale = action.get("rationale", "")
                st.write(f"**Step {step}:** {action_text}")
                st.caption(f"Rationale: {rationale}")
            else:
                st.write(f"• {action}")
    
    # Similar Incidents
    if "similar_incidents" in analysis:
        similar = analysis.get("similar_incidents", [])
        if similar:
            st.subheader("Similar Past Incidents")
            for incident in similar:
                st.write(f"• {incident}")
    
    # 2. RETRIEVED CONTEXT SECTION
    st.markdown("---")
    st.markdown("## 📚 Retrieved Context (Evidence Documents)")
    
    if retrieved_context:
        for i, context in enumerate(retrieved_context, 1):
            with st.expander(f"Document {i} - {context.get('source', 'Unknown')} (Similarity: {context.get('similarity', 0):.2%})"):
                st.code(context.get('document', 'N/A'), language="text")
    
    # 3. METRICS SECTION
    st.markdown("---")
    st.markdown("## 📊 Performance Metrics")
    
    if metrics:
        col1, col2, col3, col4 = st.columns(4)
        
        latency = metrics.get("latency", {})
        with col1:
            st.metric("Latency", f"{latency.get('latency_ms', 0):.0f}ms")
        
        retrieval = metrics.get("retrieval", {})
        with col2:
            st.metric("Retrieval Accuracy", f"{metrics.get('retrieval_accuracy', 0):.0%}")
        
        quality = metrics.get("response_quality", {})
        with col3:
            st.metric("Response Quality", f"{quality.get('overall_quality', 0):.0%}")
        
        with col4:
            st.metric("Overall Score", f"{metrics.get('overall_score', 0):.0%}")
        
        # Detailed metrics
        with st.expander("📈 Detailed Metrics"):
            st.write("**Retrieval Metrics:**")
            st.json(retrieval)
            st.write("**Response Quality:**")
            st.json(quality)


def main():
    """Main Streamlit app"""
    
    # Header
    st.markdown("# 📡 Telecom AI Incident Copilot")
    st.markdown("*Enterprise AI system for network incident diagnosis and resolution*")
    
    # Sidebar
    with st.sidebar:
        st.markdown("## ⚙️ System Status")
        
        backend_healthy = check_backend_health()
        status_icon = "🟢" if backend_healthy else "🔴"
        st.write(f"{status_icon} Backend: {'Connected' if backend_healthy else 'Disconnected'}")
        
        # System stats
        stats = get_system_stats()
        if "collection" in stats:
            doc_count = stats["collection"].get("document_count", 0)
            st.write(f"📚 Documents Indexed: {doc_count}")
        
        st.markdown("---")
        st.markdown("## 🔧 Demo Incidents")
        
        demo_choice = st.selectbox(
            "Select a demo incident:",
            [inc["name"] for inc in SIDEBAR_DEMO_INCIDENTS],
            key="demo_select"
        )
        
        if st.button("📤 Load Demo"):
            st.session_state.demo_loaded = True
            st.session_state.demo_text = next(
                inc["description"] for inc in SIDEBAR_DEMO_INCIDENTS 
                if inc["name"] == demo_choice
            )
        
        st.markdown("---")
        st.markdown("## ℹ️ About")
        st.write("""
This system demonstrates OPEA principles for enterprise AI:
- **Modular Architecture**: Independent microservices
- **RAG Pipeline**: Semantic retrieval + LLM reasoning
- **Local Inference**: No cloud APIs required
- **Performance Metrics**: Full observability
        """)
    
    # Main content
    if not backend_healthy:
        st.error("❌ Backend is not responding. Please ensure all services are running.")
        st.info("Start services with: `docker-compose -f docker/docker-compose.yml up`")
        return
    
    # Check if vector DB is initialized
    stats = get_system_stats()
    doc_count = stats.get("collection", {}).get("document_count", 0)
    
    if doc_count == 0:
        st.warning("⚠️ Vector database not initialized. Initializing now...")
        with st.spinner("Initializing vector database..."):
            init_result = initialize_vector_db()
            if "error" in init_result:
                st.error(f"Initialization error: {init_result['error']}")
                return
            st.success(f"✅ Initialized with {init_result.get('document_count', 0)} documents")
            st.rerun()
    
    # Main input section
    st.markdown("## 🚨 Incident Analysis")
    st.write("Describe your network incident and let AI analyze it:")
    
    # Get incident description from session state or input
    if hasattr(st.session_state, "demo_loaded") and st.session_state.demo_loaded:
        incident_text = st.text_area(
            "Incident Description",
            value=st.session_state.demo_text,
            height=100,
            key="incident_input"
        )
        st.session_state.demo_loaded = False
    else:
        incident_text = st.text_area(
            "Incident Description",
            height=100,
            placeholder="Example: High packet loss detected on Node B12. Users report degraded service...",
            key="incident_input"
        )
    
    # Analysis button
    col1, col2 = st.columns([3, 1])
    with col1:
        analyze_button = st.button("🔍 Analyze Incident", use_container_width=True, type="primary")
    
    with col2:
        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    
    # Perform analysis
    if analyze_button and incident_text.strip():
        with st.spinner("🔄 Analyzing incident..."):
            result = analyze_incident(incident_text)
        
        display_analysis_result(result)
    
    elif analyze_button and not incident_text.strip():
        st.warning("⚠️ Please enter an incident description")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <center>
    <small>Telecom AI Incident Copilot v1.0 | OPEA-aligned Enterprise AI System</small>
    </center>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
