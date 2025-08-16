#!/bin/bash

# Kafka Self-Healing System Test Runner
# This script runs the complete test suite including unit tests, integration tests, and e2e tests

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOCKER_COMPOSE_FILE="docker-compose.test.yml"
TEST_TIMEOUT=300  # 5 minutes
BENCHMARK_TIMEOUT=600  # 10 minutes

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "docker-compose is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi
    
    print_success "Docker environment is ready"
}

# Function to setup test environment
setup_test_env() {
    print_status "Setting up test environment..."
    
    # Create test directories
    mkdir -p test_logs
    mkdir -p test_reports
    
    # Install test dependencies
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
    fi
    
    # Install additional test dependencies
    pip install pytest pytest-cov pytest-html pytest-xdist psutil requests
    
    print_success "Test environment setup complete"
}

# Function to run unit tests
run_unit_tests() {
    print_status "Running unit tests..."
    
    pytest tests/ \
        --ignore=tests/test_e2e.py \
        --cov=src/kafka_self_healing \
        --cov-report=html:test_reports/coverage_html \
        --cov-report=xml:test_reports/coverage.xml \
        --cov-report=term-missing \
        --html=test_reports/unit_tests.html \
        --self-contained-html \
        --junitxml=test_reports/unit_tests.xml \
        -v
    
    if [ $? -eq 0 ]; then
        print_success "Unit tests passed"
    else
        print_error "Unit tests failed"
        return 1
    fi
}

# Function to start test cluster
start_test_cluster() {
    print_status "Starting test cluster..."
    
    # Stop any existing containers
    docker-compose -f $DOCKER_COMPOSE_FILE down -v &> /dev/null || true
    
    # Start the cluster
    docker-compose -f $DOCKER_COMPOSE_FILE up -d
    
    # Wait for cluster to be ready
    print_status "Waiting for cluster to be ready..."
    local timeout=120
    local elapsed=0
    
    while [ $elapsed -lt $timeout ]; do
        if docker exec test-zookeeper bash -c "echo 'ruok' | nc localhost 2181" | grep -q "imok" 2>/dev/null; then
            if docker exec test-kafka1 kafka-broker-api-versions --bootstrap-server localhost:9092 &>/dev/null; then
                if docker exec test-kafka2 kafka-broker-api-versions --bootstrap-server localhost:9093 &>/dev/null; then
                    print_success "Test cluster is ready"
                    return 0
                fi
            fi
        fi
        
        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    
    print_error "Test cluster failed to start within timeout"
    docker-compose -f $DOCKER_COMPOSE_FILE logs
    return 1
}

# Function to stop test cluster
stop_test_cluster() {
    print_status "Stopping test cluster..."
    docker-compose -f $DOCKER_COMPOSE_FILE down -v
    print_success "Test cluster stopped"
}

# Function to run end-to-end tests
run_e2e_tests() {
    print_status "Running end-to-end tests..."
    
    timeout $TEST_TIMEOUT pytest tests/test_e2e.py \
        --html=test_reports/e2e_tests.html \
        --self-contained-html \
        --junitxml=test_reports/e2e_tests.xml \
        -v -s
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "End-to-end tests passed"
    elif [ $exit_code -eq 124 ]; then
        print_error "End-to-end tests timed out"
        return 1
    else
        print_error "End-to-end tests failed"
        return 1
    fi
}

# Function to run performance benchmarks
run_benchmarks() {
    print_status "Running performance benchmarks..."
    
    # Create a test configuration for benchmarking
    cat > test_benchmark_config.yaml << EOF
cluster:
  kafka_brokers:
    - node_id: kafka1
      host: localhost
      port: 9092
      jmx_port: 9999
    - node_id: kafka2
      host: localhost
      port: 9093
      jmx_port: 9998
  zookeeper_nodes:
    - node_id: zk1
      host: localhost
      port: 2181

monitoring:
  interval_seconds: 5
  timeout_seconds: 10
  methods: ["socket", "jmx"]

recovery:
  max_attempts: 2
  initial_delay_seconds: 1
  backoff_multiplier: 2.0
  max_delay_seconds: 10
  actions: ["restart_service"]

notifications:
  smtp:
    host: localhost
    port: 1025
    from_email: test@example.com
    to_emails: ["admin@example.com"]

logging:
  level: INFO
  file: test_logs/benchmark.log
EOF
    
    timeout $BENCHMARK_TIMEOUT python tests/benchmark.py \
        --config test_benchmark_config.yaml \
        --output test_reports/benchmark_results.json \
        --report test_reports/benchmark_report.txt
    
    local exit_code=$?
    
    # Clean up config file
    rm -f test_benchmark_config.yaml
    
    if [ $exit_code -eq 0 ]; then
        print_success "Performance benchmarks completed"
        if [ -f "test_reports/benchmark_report.txt" ]; then
            echo ""
            cat test_reports/benchmark_report.txt
        fi
    elif [ $exit_code -eq 124 ]; then
        print_warning "Performance benchmarks timed out"
    else
        print_warning "Performance benchmarks failed (non-critical)"
    fi
}

# Function to generate test summary
generate_test_summary() {
    print_status "Generating test summary..."
    
    local summary_file="test_reports/test_summary.txt"
    
    cat > $summary_file << EOF
KAFKA SELF-HEALING SYSTEM TEST SUMMARY
======================================

Test Run Date: $(date)
Test Environment: $(uname -a)
Python Version: $(python --version)

TEST RESULTS:
EOF
    
    # Check unit test results
    if [ -f "test_reports/unit_tests.xml" ]; then
        local unit_tests=$(grep -o 'tests="[0-9]*"' test_reports/unit_tests.xml | cut -d'"' -f2)
        local unit_failures=$(grep -o 'failures="[0-9]*"' test_reports/unit_tests.xml | cut -d'"' -f2)
        local unit_errors=$(grep -o 'errors="[0-9]*"' test_reports/unit_tests.xml | cut -d'"' -f2)
        
        echo "Unit Tests: $unit_tests total, $unit_failures failures, $unit_errors errors" >> $summary_file
    fi
    
    # Check e2e test results
    if [ -f "test_reports/e2e_tests.xml" ]; then
        local e2e_tests=$(grep -o 'tests="[0-9]*"' test_reports/e2e_tests.xml | cut -d'"' -f2)
        local e2e_failures=$(grep -o 'failures="[0-9]*"' test_reports/e2e_tests.xml | cut -d'"' -f2)
        local e2e_errors=$(grep -o 'errors="[0-9]*"' test_reports/e2e_tests.xml | cut -d'"' -f2)
        
        echo "E2E Tests: $e2e_tests total, $e2e_failures failures, $e2e_errors errors" >> $summary_file
    fi
    
    # Add coverage information
    if [ -f "test_reports/coverage.xml" ]; then
        local coverage=$(grep -o 'line-rate="[0-9.]*"' test_reports/coverage.xml | head -1 | cut -d'"' -f2)
        local coverage_percent=$(echo "$coverage * 100" | bc -l | cut -d'.' -f1)
        echo "Code Coverage: ${coverage_percent}%" >> $summary_file
    fi
    
    echo "" >> $summary_file
    echo "ARTIFACTS:" >> $summary_file
    echo "- Unit Test Report: test_reports/unit_tests.html" >> $summary_file
    echo "- E2E Test Report: test_reports/e2e_tests.html" >> $summary_file
    echo "- Coverage Report: test_reports/coverage_html/index.html" >> $summary_file
    echo "- Benchmark Results: test_reports/benchmark_results.json" >> $summary_file
    echo "- Benchmark Report: test_reports/benchmark_report.txt" >> $summary_file
    
    print_success "Test summary generated: $summary_file"
    echo ""
    cat $summary_file
}

# Function to cleanup
cleanup() {
    print_status "Cleaning up..."
    stop_test_cluster
    rm -f test_benchmark_config.yaml
}

# Main execution
main() {
    local run_unit=true
    local run_e2e=true
    local run_bench=false
    local cleanup_on_exit=true
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --unit-only)
                run_e2e=false
                run_bench=false
                shift
                ;;
            --e2e-only)
                run_unit=false
                run_bench=false
                shift
                ;;
            --with-benchmarks)
                run_bench=true
                shift
                ;;
            --no-cleanup)
                cleanup_on_exit=false
                shift
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --unit-only       Run only unit tests"
                echo "  --e2e-only        Run only end-to-end tests"
                echo "  --with-benchmarks Include performance benchmarks"
                echo "  --no-cleanup      Don't cleanup test environment"
                echo "  --help            Show this help message"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Set up cleanup trap
    if [ "$cleanup_on_exit" = true ]; then
        trap cleanup EXIT
    fi
    
    print_status "Starting Kafka Self-Healing System test suite..."
    
    # Check prerequisites
    check_docker
    setup_test_env
    
    local overall_success=true
    
    # Run unit tests
    if [ "$run_unit" = true ]; then
        if ! run_unit_tests; then
            overall_success=false
        fi
    fi
    
    # Run end-to-end tests
    if [ "$run_e2e" = true ]; then
        if ! start_test_cluster; then
            overall_success=false
        else
            if ! run_e2e_tests; then
                overall_success=false
            fi
        fi
    fi
    
    # Run benchmarks
    if [ "$run_bench" = true ] && [ "$run_e2e" = true ]; then
        run_benchmarks  # Non-critical, doesn't affect overall success
    fi
    
    # Generate summary
    generate_test_summary
    
    # Final result
    if [ "$overall_success" = true ]; then
        print_success "All tests completed successfully!"
        exit 0
    else
        print_error "Some tests failed!"
        exit 1
    fi
}

# Run main function with all arguments
main "$@"