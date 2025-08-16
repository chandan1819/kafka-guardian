#!/bin/bash
# Health check script for Kafka Guardian Docker container

set -e

# Configuration
HEALTH_CHECK_URL="http://localhost:8080/health"
METRICS_URL="http://localhost:8080/metrics"
TIMEOUT=10
MAX_RETRIES=3

# Function to log messages
log() {
    echo "[HEALTHCHECK] $(date +'%Y-%m-%d %H:%M:%S') $*"
}

# Function to check HTTP endpoint
check_http_endpoint() {
    local url=$1
    local timeout=${2:-$TIMEOUT}
    
    if command -v curl >/dev/null 2>&1; then
        curl -f -s --max-time "$timeout" "$url" >/dev/null 2>&1
    elif command -v wget >/dev/null 2>&1; then
        wget -q --timeout="$timeout" --tries=1 -O /dev/null "$url" >/dev/null 2>&1
    else
        # Fallback using nc
        local host=$(echo "$url" | sed 's|http://||' | cut -d':' -f1)
        local port=$(echo "$url" | sed 's|http://||' | cut -d':' -f2 | cut -d'/' -f1)
        nc -z "$host" "$port" 2>/dev/null
    fi
}

# Function to check process
check_process() {
    pgrep -f "kafka-guardian" >/dev/null 2>&1
}

# Function to check log files for errors
check_logs() {
    local log_file="/var/log/kafka-guardian/application.log"
    
    if [[ -f "$log_file" ]]; then
        # Check for recent critical errors (last 5 minutes)
        local recent_errors=$(find "$log_file" -mmin -5 -exec grep -c "CRITICAL\|FATAL" {} \; 2>/dev/null || echo "0")
        
        if [[ "$recent_errors" -gt 0 ]]; then
            log "Found $recent_errors critical errors in recent logs"
            return 1
        fi
    fi
    
    return 0
}

# Function to check memory usage
check_memory() {
    local memory_threshold=90  # 90% memory usage threshold
    
    if command -v free >/dev/null 2>&1; then
        local memory_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
        
        if [[ "$memory_usage" -gt "$memory_threshold" ]]; then
            log "High memory usage: ${memory_usage}%"
            return 1
        fi
    fi
    
    return 0
}

# Function to check disk space
check_disk() {
    local disk_threshold=95  # 95% disk usage threshold
    local log_dir="/var/log/kafka-guardian"
    
    if [[ -d "$log_dir" ]] && command -v df >/dev/null 2>&1; then
        local disk_usage=$(df "$log_dir" | tail -1 | awk '{print $5}' | sed 's/%//')
        
        if [[ "$disk_usage" -gt "$disk_threshold" ]]; then
            log "High disk usage: ${disk_usage}%"
            return 1
        fi
    fi
    
    return 0
}

# Main health check function
perform_health_check() {
    local checks_passed=0
    local total_checks=0
    
    # Check 1: Process is running
    total_checks=$((total_checks + 1))
    if check_process; then
        log "✓ Process check passed"
        checks_passed=$((checks_passed + 1))
    else
        log "✗ Process check failed - Kafka Guardian process not found"
    fi
    
    # Check 2: Health endpoint responds
    total_checks=$((total_checks + 1))
    if check_http_endpoint "$HEALTH_CHECK_URL"; then
        log "✓ Health endpoint check passed"
        checks_passed=$((checks_passed + 1))
    else
        log "✗ Health endpoint check failed - $HEALTH_CHECK_URL not responding"
    fi
    
    # Check 3: Metrics endpoint responds
    total_checks=$((total_checks + 1))
    if check_http_endpoint "$METRICS_URL"; then
        log "✓ Metrics endpoint check passed"
        checks_passed=$((checks_passed + 1))
    else
        log "✗ Metrics endpoint check failed - $METRICS_URL not responding"
    fi
    
    # Check 4: No critical errors in logs
    total_checks=$((total_checks + 1))
    if check_logs; then
        log "✓ Log check passed"
        checks_passed=$((checks_passed + 1))
    else
        log "✗ Log check failed - Critical errors found in logs"
    fi
    
    # Check 5: Memory usage is reasonable
    total_checks=$((total_checks + 1))
    if check_memory; then
        log "✓ Memory check passed"
        checks_passed=$((checks_passed + 1))
    else
        log "✗ Memory check failed - High memory usage detected"
    fi
    
    # Check 6: Disk space is available
    total_checks=$((total_checks + 1))
    if check_disk; then
        log "✓ Disk check passed"
        checks_passed=$((checks_passed + 1))
    else
        log "✗ Disk check failed - High disk usage detected"
    fi
    
    # Determine overall health
    local success_rate=$((checks_passed * 100 / total_checks))
    log "Health check summary: $checks_passed/$total_checks checks passed ($success_rate%)"
    
    # Require at least 80% of checks to pass
    if [[ "$success_rate" -ge 80 ]]; then
        log "✓ Overall health check PASSED"
        return 0
    else
        log "✗ Overall health check FAILED"
        return 1
    fi
}

# Function to perform health check with retries
health_check_with_retries() {
    local attempt=1
    
    while [[ $attempt -le $MAX_RETRIES ]]; do
        log "Health check attempt $attempt/$MAX_RETRIES"
        
        if perform_health_check; then
            return 0
        fi
        
        if [[ $attempt -lt $MAX_RETRIES ]]; then
            log "Health check failed, retrying in 5 seconds..."
            sleep 5
        fi
        
        attempt=$((attempt + 1))
    done
    
    log "All health check attempts failed"
    return 1
}

# Main execution
main() {
    case "${1:-check}" in
        "check")
            health_check_with_retries
            ;;
        "quick")
            # Quick check - just process and health endpoint
            if check_process && check_http_endpoint "$HEALTH_CHECK_URL"; then
                log "✓ Quick health check PASSED"
                exit 0
            else
                log "✗ Quick health check FAILED"
                exit 1
            fi
            ;;
        "verbose")
            # Verbose check with detailed output
            perform_health_check
            ;;
        *)
            echo "Usage: $0 [check|quick|verbose]"
            echo "  check   - Full health check with retries (default)"
            echo "  quick   - Quick health check (process + endpoint)"
            echo "  verbose - Detailed health check output"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"