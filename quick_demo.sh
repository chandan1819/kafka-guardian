#!/bin/bash

# Quick Controlled Demo Script - No Long Running Processes
# Perfect for live team demonstrations

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

# Function to start just the Kafka cluster
start_kafka_only() {
    print_step "Starting Kafka cluster for demo..."
    
    # Start the cluster
    docker-compose -f docker-compose.test.yml up -d
    
    print_info "Waiting for services to start..."
    sleep 15
    
    # Quick health check
    local ready=0
    for i in {1..6}; do
        if docker exec test-kafka1 kafka-broker-api-versions --bootstrap-server localhost:9092 &>/dev/null; then
            ready=$((ready + 1))
        fi
        if docker exec test-kafka2 kafka-broker-api-versions --bootstrap-server localhost:9093 &>/dev/null; then
            ready=$((ready + 1))
        fi
        if [ $ready -eq 2 ]; then
            break
        fi
        echo -n "."
        sleep 5
    done
    
    echo ""
    if [ $ready -eq 2 ]; then
        print_success "Kafka cluster is ready for demo!"
    else
        print_info "Services may still be starting..."
    fi
}

# Function to run monitoring for a specific duration
run_monitoring_demo() {
    local duration=${1:-60}  # Default 60 seconds
    
    print_step "Running monitoring demo for $duration seconds..."
    print_info "Watch the logs in another terminal: tail -f logs/application.log"
    print_info "Press Ctrl+C to stop early"
    
    # Run monitoring for specified duration (macOS compatible)
    python3 -c "
import subprocess, signal, time, sys
import os

def timeout_handler(signum, frame):
    print('\n⏰ Monitoring demo time completed!')
    sys.exit(0)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm($duration)

try:
    subprocess.run([sys.executable, '-m', 'src.kafka_self_healing.main', '--config', 'config_local_test.yaml'])
except KeyboardInterrupt:
    print('\n⏹️  Monitoring demo stopped by user')
except:
    pass
" || true
    
    print_success "Monitoring demo completed"
}

# Function to demonstrate failure and recovery
demo_failure_recovery() {
    print_step "Demonstrating failure detection and recovery..."
    
    echo "Current status:"
    docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"
    
    echo ""
    print_info "Stopping Kafka Broker 1 (simulating failure)..."
    docker stop test-kafka1
    
    echo "Status after failure:"
    docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"
    
    echo ""
    print_info "In production, the monitoring system would detect this and attempt recovery."
    print_info "For demo, let's manually restart the service..."
    
    read -p "Press Enter to restart the failed broker..."
    
    docker start test-kafka1
    sleep 5
    
    echo "Recovery complete:"
    docker ps --filter "name=test-kafka" --format "table {{.Names}}\t{{.Status}}"
    
    print_success "Failure and recovery demonstration completed!"
}

# Function to show system status
show_status() {
    print_step "Current System Status"
    
    echo ""
    echo "Docker containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | head -5
    
    echo ""
    echo "Service endpoints:"
    echo "• Kafka Broker 1: localhost:9092"
    echo "• Kafka Broker 2: localhost:9093"
    echo "• Zookeeper: localhost:2181"
    echo "• MailHog UI: http://localhost:8025"
    
    echo ""
    echo "Test connectivity:"
    nc -zv localhost 9092 && echo "✅ Kafka Broker 1 OK" || echo "❌ Kafka Broker 1 FAIL"
    nc -zv localhost 9093 && echo "✅ Kafka Broker 2 OK" || echo "❌ Kafka Broker 2 FAIL"
    nc -zv localhost 2181 && echo "✅ Zookeeper OK" || echo "❌ Zookeeper FAIL"
}

# Function to cleanup
cleanup() {
    print_step "Cleaning up demo environment..."
    docker-compose -f docker-compose.test.yml down -v
    print_success "Demo cleanup complete"
}

# Function to show help
show_help() {
    echo "Quick Demo Script - Controlled Kafka Guardian Demo"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  setup           - Start Kafka cluster only (no continuous monitoring)"
    echo "  monitor [SEC]   - Run monitoring for specified seconds (default: 60)"
    echo "  failure         - Demonstrate failure detection and recovery"
    echo "  status          - Show current system status"
    echo "  stop            - Stop and cleanup everything"
    echo "  full            - Complete demo (setup + monitor + failure + cleanup)"
    echo "  help            - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 setup                    # Just start Kafka cluster"
    echo "  $0 monitor 30               # Run monitoring for 30 seconds"
    echo "  $0 failure                  # Demo failure and recovery"
    echo "  $0 full                     # Complete 5-minute demo"
    echo ""
    echo "Demo Flow:"
    echo "  1. $0 setup      # Start cluster (2 min)"
    echo "  2. $0 monitor 30 # Show monitoring (30 sec)"
    echo "  3. $0 failure    # Demo failure/recovery (2 min)"
    echo "  4. $0 stop       # Cleanup (30 sec)"
}

# Function for complete demo
full_demo() {
    echo -e "${CYAN}"
    echo "================================================================"
    echo "  🚀 Kafka Guardian - Complete 5-Minute Demo"
    echo "================================================================"
    echo -e "${NC}"
    
    start_kafka_only
    
    echo ""
    print_info "Demo Phase 1: System Setup - COMPLETE ✅"
    print_info "Demo Phase 2: Monitoring (30 seconds)..."
    
    run_monitoring_demo 30
    
    echo ""
    print_info "Demo Phase 2: Monitoring - COMPLETE ✅"
    print_info "Demo Phase 3: Failure & Recovery..."
    
    demo_failure_recovery
    
    echo ""
    print_info "Demo Phase 3: Failure & Recovery - COMPLETE ✅"
    print_info "Demo Phase 4: Cleanup..."
    
    cleanup
    
    echo ""
    print_success "🎉 Complete demo finished! Total time: ~5 minutes"
    echo ""
    echo "Next steps:"
    echo "• Check logs: ls -la logs/"
    echo "• Review config: cat config_local_test.yaml"
    echo "• Read docs: LIVE_DEMO_GUIDE.md"
}

# Main execution
main() {
    local command=${1:-help}
    
    case $command in
        "setup")
            start_kafka_only
            show_status
            ;;
        "monitor")
            local duration=${2:-60}
            run_monitoring_demo $duration
            ;;
        "failure")
            demo_failure_recovery
            ;;
        "status")
            show_status
            ;;
        "stop")
            cleanup
            ;;
        "full")
            full_demo
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            echo "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Handle Ctrl+C gracefully
trap cleanup EXIT

# Run main function
main "$@"