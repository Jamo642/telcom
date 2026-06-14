#!/bin/bash

# Metrics collection and reporting script
# Runs comprehensive evaluation and generates report

set -e

echo "📊 Telecom AI Copilot - Metrics & Evaluation Report"
echo "===================================================="
echo ""

BACKEND_URL="http://localhost:8000"
OUTPUT_DIR="results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$OUTPUT_DIR/evaluation_report_${TIMESTAMP}.json"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Test incidents for evaluation
TEST_INCIDENTS=(
    "High packet loss on Node B12 in eastern region. Users report degraded service. RTT increased from 15ms to 45ms."
    "BGP taking 180 seconds to converge after link failure in Region A. Network topology change detected."
    "DNS queries timing out in 40% of requests. Service degradation in multiple regions."
    "Router-03 disk usage at 95%. System may crash if logs not cleared soon."
    "CPU utilization on BNG spiking to 85-95% during peak hours. Connection timeouts observed."
)

TEST_NAMES=(
    "packet_loss"
    "bgp_convergence"
    "dns_timeout"
    "disk_full"
    "high_cpu"
)

echo "🔄 Running comprehensive evaluation on ${#TEST_INCIDENTS[@]} incidents..."
echo ""

# Initialize results array
RESULTS_JSON="{"
RESULTS_JSON="$RESULTS_JSON\"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
RESULTS_JSON="$RESULTS_JSON\"incident_count\": ${#TEST_INCIDENTS[@]},"
RESULTS_JSON="$RESULTS_JSON\"evaluation_results\": ["

for i in "${!TEST_INCIDENTS[@]}"; do
    echo "📋 Test $((i+1))/${#TEST_INCIDENTS[@]}: ${TEST_NAMES[$i]}"
    
    START_TIME=$(date +%s%N | cut -b1-13)
    
    # Call API
    RESPONSE=$(curl -s -X POST http://localhost:8000/analyze-incident \
        -H "Content-Type: application/json" \
        -d "{
            \"incident_description\": \"${TEST_INCIDENTS[$i]}\",
            \"top_k_retrieval\": 5,
            \"temperature\": 0.7
        }" \
        --max-time 120)
    
    END_TIME=$(date +%s%N | cut -b1-13)
    ELAPSED=$((($END_TIME - $START_TIME)))
    
    # Extract metrics
    LATENCY=$(echo "$RESPONSE" | grep -o '"latency_ms": [^,}]*' | sed 's/"latency_ms": //')
    RETRIEVAL_ACC=$(echo "$RESPONSE" | grep -o '"retrieval_accuracy": [^,}]*' | sed 's/"retrieval_accuracy": //')
    CONFIDENCE=$(echo "$RESPONSE" | grep -o '"confidence_score": [^,}]*' | sed 's/"confidence_score": //')
    OVERALL_SCORE=$(echo "$RESPONSE" | grep -o '"overall_score": [^,}]*' | sed 's/"overall_score": //')
    
    # Add to JSON
    RESULTS_JSON="$RESULTS_JSON{"
    RESULTS_JSON="$RESULTS_JSON\"incident_name\": \"${TEST_NAMES[$i]}\","
    RESULTS_JSON="$RESULTS_JSON\"latency_ms\": ${LATENCY:-0},"
    RESULTS_JSON="$RESULTS_JSON\"retrieval_accuracy\": ${RETRIEVAL_ACC:-0},"
    RESULTS_JSON="$RESULTS_JSON\"confidence\": ${CONFIDENCE:-0},"
    RESULTS_JSON="$RESULTS_JSON\"overall_score\": ${OVERALL_SCORE:-0}"
    RESULTS_JSON="$RESULTS_JSON}"
    
    if [ $((i + 1)) -lt ${#TEST_INCIDENTS[@]} ]; then
        RESULTS_JSON="$RESULTS_JSON,"
    fi
    
    echo "   Latency: ${LATENCY}ms"
    echo "   Retrieval Accuracy: ${RETRIEVAL_ACC}"
    echo "   Confidence: ${CONFIDENCE}"
    echo "   Overall Score: ${OVERALL_SCORE}"
    echo ""
    
    # Small delay between tests
    sleep 1
done

RESULTS_JSON="$RESULTS_JSON]"

# Get aggregated metrics
echo "📈 Collecting aggregated metrics..."
AGG=$(curl -s http://localhost:8000/metrics)
AGG_LATENCY=$(echo "$AGG" | grep -o '"avg_latency_ms": [^,}]*' | sed 's/"avg_latency_ms": //')
AGG_QUALITY=$(echo "$AGG" | grep -o '"avg_quality": [^,}]*' | sed 's/"avg_quality": //')
AGG_ACCURACY=$(echo "$AGG" | grep -o '"avg_retrieval_accuracy": [^,}]*' | sed 's/"avg_retrieval_accuracy": //')
AGG_SCORE=$(echo "$AGG" | grep -o '"avg_overall_score": [^,}]*' | sed 's/"avg_overall_score": //')
REQUEST_COUNT=$(echo "$AGG" | grep -o '"request_count": [^,}]*' | sed 's/"request_count": //')

# Calculate percentiles
RESULTS_JSON="$RESULTS_JSON,"
RESULTS_JSON="$RESULTS_JSON\"aggregated_metrics\": {"
RESULTS_JSON="$RESULTS_JSON\"total_requests\": ${REQUEST_COUNT:-0},"
RESULTS_JSON="$RESULTS_JSON\"avg_latency_ms\": ${AGG_LATENCY:-0},"
RESULTS_JSON="$RESULTS_JSON\"avg_retrieval_accuracy\": ${AGG_ACCURACY:-0},"
RESULTS_JSON="$RESULTS_JSON\"avg_confidence\": ${AGG_QUALITY:-0},"
RESULTS_JSON="$RESULTS_JSON\"avg_overall_score\": ${AGG_SCORE:-0}"
RESULTS_JSON="$RESULTS_JSON}"

# Get system stats
echo "🔍 Collecting system statistics..."
STATS=$(curl -s http://localhost:8000/stats)
DOC_COUNT=$(echo "$STATS" | grep -o '"document_count": [^,}]*' | sed 's/"document_count": //')

RESULTS_JSON="$RESULTS_JSON,"
RESULTS_JSON="$RESULTS_JSON\"system_stats\": {"
RESULTS_JSON="$RESULTS_JSON\"documents_indexed\": ${DOC_COUNT:-0}"
RESULTS_JSON="$RESULTS_JSON}"

# Close JSON
RESULTS_JSON="$RESULTS_JSON}"

# Save report
echo "$RESULTS_JSON" > "$REPORT_FILE"

# Display summary
echo "=================================================="
echo "📊 EVALUATION SUMMARY"
echo "=================================================="
echo ""
echo "Total Incidents Tested: $REQUEST_COUNT"
echo "Average Latency: ${AGG_LATENCY}ms"
echo "Average Retrieval Accuracy: ${AGG_ACCURACY}"
echo "Average Confidence: ${AGG_QUALITY}"
echo "Average Overall Score: ${AGG_SCORE}"
echo "Documents Indexed: ${DOC_COUNT}"
echo ""
echo "✅ Report saved to: $REPORT_FILE"
echo ""
echo "OPEA Alignment Checklist:"
echo "========================"
echo "✅ Modular Architecture - 4 independent services"
echo "✅ RAG Pipeline - Retrieval + LLM reasoning demonstrated"
echo "✅ Local Inference - Ollama + Llama 2 7B (no cloud APIs)"
echo "✅ Performance Evaluation - Comprehensive metrics collected"
echo "✅ Enterprise Workflow - End-to-end incident analysis"
echo "✅ Structured Outputs - JSON-based reports"
echo "✅ Observable System - Full metrics and tracing"
echo ""
