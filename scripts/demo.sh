#!/bin/bash

# Demo Script for Telecom AI Incident Copilot
# This script demonstrates the full workflow with 3 pre-configured incidents

set -e

echo "🎬 Telecom AI Incident Copilot - Demo Script"
echo "=============================================="
echo ""

BACKEND_URL="http://localhost:8000"
DEMO_INCIDENTS=(
    "High packet loss on Node B12 in the eastern region. Users report degraded service quality with RTT increased from 15ms to 45ms. Impact: approximately 5000 users affected."
    "BGP is taking 180 seconds to converge after a link failure in Region A. Network topology change causing delayed prefix advertisements. This exceeds our SLA of 60 seconds."
    "DNS queries are timing out in 40% of requests. Users unable to resolve domain names properly. Service degradation reported in multiple regions."
)

DEMO_NAMES=(
    "Packet Loss on Node B12"
    "BGP Route Convergence Delay"
    "DNS Resolution Timeout"
)

# Check backend health
echo "🔍 Checking backend health..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ Backend not responding. Please start services first:"
    echo "   docker-compose -f docker/docker-compose.yml up"
    exit 1
fi

echo "✅ Backend is healthy"
echo ""

# Check if database is initialized
echo "📊 Checking database initialization..."
STATS=$(curl -s http://localhost:8000/stats)
DOC_COUNT=$(echo "$STATS" | grep -o '"document_count": [0-9]*' | grep -o '[0-9]*')

if [ "$DOC_COUNT" = "0" ] || [ -z "$DOC_COUNT" ]; then
    echo "📥 Initializing database (this may take a minute)..."
    curl -s -X POST http://localhost:8000/initialize \
        -H "Content-Type: application/json" \
        -d '{
            "incidents_csv_path": "/data/incidents/incidents.csv",
            "logs_dir_path": "/data/logs",
            "manuals_dir_path": "/data/manuals"
        }' > /dev/null
    sleep 2
    echo "✅ Database initialized"
else
    echo "✅ Database has $DOC_COUNT documents"
fi

echo ""
echo "🚀 Running Demo Analysis"
echo "========================"
echo ""

# Run demo incidents
for i in 0 1 2; do
    echo "📋 Demo $((i+1))/3: ${DEMO_NAMES[$i]}"
    echo "---"
    echo "Incident: ${DEMO_INCIDENTS[$i]}"
    echo ""
    
    echo "⏳ Analyzing (this may take 10-15 seconds)..."
    START_TIME=$(date +%s%N | cut -b1-13)
    
    # Call API
    RESPONSE=$(curl -s -X POST http://localhost:8000/analyze-incident \
        -H "Content-Type: application/json" \
        -d "{
            \"incident_description\": \"${DEMO_INCIDENTS[$i]}\",
            \"top_k_retrieval\": 5,
            \"temperature\": 0.7
        }" \
        --max-time 120)
    
    END_TIME=$(date +%s%N | cut -b1-13)
    ELAPSED=$((($END_TIME - $START_TIME) / 1000))
    
    # Extract results
    ROOT_CAUSE=$(echo "$RESPONSE" | grep -o '"root_cause": "[^"]*' | sed 's/"root_cause": "//' | head -c 100)
    SEVERITY=$(echo "$RESPONSE" | grep -o '"severity": "[^"]*' | sed 's/"severity": "//')
    CONFIDENCE=$(echo "$RESPONSE" | grep -o '"confidence_score": [^,}]*' | sed 's/"confidence_score": //')
    LATENCY=$(echo "$RESPONSE" | grep -o '"latency_ms": [^,}]*' | sed 's/"latency_ms": //')
    ACCURACY=$(echo "$RESPONSE" | grep -o '"retrieval_accuracy": [^,}]*' | sed 's/"retrieval_accuracy": //')
    
    echo "✅ Analysis Complete"
    echo ""
    echo "📊 Results:"
    echo "  Root Cause: $ROOT_CAUSE..."
    echo "  Severity: $SEVERITY"
    echo "  Confidence: $CONFIDENCE"
    echo ""
    echo "📈 Metrics:"
    echo "  Latency: ${LATENCY}ms"
    echo "  Retrieval Accuracy: ${ACCURACY}"
    echo "  Total Time: ${ELAPSED}ms"
    echo ""
    echo ""
    
    if [ $i -lt 2 ]; then
        echo "⏳ Waiting 3 seconds before next demo..."
        sleep 3
    fi
done

echo "🎉 Demo Complete!"
echo ""
echo "Summary:"
echo "--------"
echo "✅ System demonstrated full workflow:"
echo "   1. Incident input"
echo "   2. Semantic retrieval from vector DB"
echo "   3. LLM-based reasoning"
echo "   4. Structured report generation"
echo "   5. Performance metrics"
echo ""
echo "🌐 Access the web UI at: http://localhost:8501"
echo "📚 API Docs available at: http://localhost:8000/docs"
echo ""
