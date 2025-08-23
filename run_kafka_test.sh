#!/bin/bash

# Complete Kafka Self-Healing Test Setup and Runner
# This script handles everything needed to test the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
COMPOSE_FILE="docker-compose.test.yml"
CONFIG_FILE="config_local_test.yaml"
LOG_DIR="logs"

print_header() {
    echo -e "${CYAN}"
    echo "================================================================"
    echo "  🚀 Kafka Self-Healing System - Local Test Environment"
    echo "================================================================"
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
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

print_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

# Function to check Docker
check_docker() {
    print_step "Checking Docker installation..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        echo "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running"
        echo ""
        echo "Please start Docker Desktop:"
        echo "1. Open Docker Desktop application"
        echo "2. Wait for it to start completely"
        echo "3. Run this script again"
        echo ""
        echo "You can also try: open -a Docker"
        exit 1
    fi
    
    print_success "Docker is running"
}

# Function to setup directories
setup_directories() {
    print_step "Setting up directories..."
    mkdir -p $LOG_DIR
    mkdir -p test_reports
    print_success "Directories created"
}

# Function to start Kafka cluster
start_kafka_cluster() {
    print_step "Starting Kafka cluster..."
    
    # Stop any existing containers
    docker-compose -f $COMPOSE_FILE down -v &> /dev/null || true
    
    # Start the cluster
    docker-compose -f $COMPOSE_FILE up -d
    
    print_info "Waiting for services to start..."
    sleep 15
    
    # Check service health
    local services_ready=0
    local max_attempts=12
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        services_ready=0
        
        # Check Zookeeper
        if docker exec test-zookeeper bash -c "echo 'ruok' | nc localhost 2181" 2>/dev/null | grep -q "imok"; then
            services_ready=$((services_ready + 1))
        fi
        
        # Check Kafka brokers
        if docker exec test-kafka1 kafka-broker-api-versions --bootstrap-server localhost:9092 &>/dev/null; then
            services_ready=$((services_ready + 1))
        fi
        
        if docker exec test-kafka2 kafka-broker-api-versions --bootstrap-server localhost:9093 &>/dev/null; then
            services_ready=$((services_ready + 1))
        fi
        
        if [ $services_ready -eq 3 ]; then
            break
        fi
        
        echo -n "."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo ""
    
    if [ $services_ready -eq 3 ]; then
        print_success "Kafka cluster is ready!"
        print_info "Services available:"
        echo "  • Zookeeper: localhost:2181"
        echo "  • Kafka Broker 1: localhost:9092"
        echo "  • Kafka Broker 2: localhost:9093"
        echo "  • MailHog UI: http://localhost:8025"
    else
        print_warning "Some services may not be fully ready yet"
        print_info "You can check status with: docker-compose -f $COMPOSE_FILE ps"
    fi
}

# Function to test the self-healing application
test_application() {
    print_step "Testing Kafka Self-Healing Application..."
    
    # Test configuration validation
    print_info "Validating configuration..."
    if python3 -c "
import yaml
import sys
try:
    with open('$CONFIG_FILE', 'r') as f:
        config = yaml.safe_load(f)
    print('✅ Configuration is valid')
except Exception as e:
    print(f'❌ Configuration error: {e}')
    sys.exit(1)
"; then
        print_success "Configuration validated"
    else
        print_error "Configuration validation failed"
        return 1
    fi
    
    # Test Python imports
    print_info "Testing Python imports..."
    if python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    from kafka_self_healing.main import KafkaSelfHealingApp
    from kafka_self_healing.config import ConfigurationManager
    print('✅ All imports successful')
except ImportError as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
"; then
        print_success "Python imports working"
    else
        print_error "Python import test failed"
        return 1
    fi
    
    # Run a quick connectivity test
    print_info "Testing Kafka connectivity..."
    if python3 -c "
import socket
import sys

def test_connection(host, port, service):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            print(f'✅ {service} connection successful')
            return True
        else:
            print(f'❌ {service} connection failed')
            return False
    except Exception as e:
        print(f'❌ {service} connection error: {e}')
        return False

success = True
success &= test_connection('localhost', 2181, 'Zookeeper')
success &= test_connection('localhost', 9092, 'Kafka Broker 1')
success &= test_connection('localhost', 9093, 'Kafka Broker 2')

sys.exit(0 if success else 1)
"; then
        print_success "Kafka connectivity test passed"
    else
        print_warning "Some connectivity tests failed - services may still be starting"
    fi
}

# Function to run the self-healing system
run_self_healing_system() {
    print_step "Starting Kafka Self-Healing System..."
    
    print_info "Running with configuration: $CONFIG_FILE"
    print_info "Logs will be written to: $LOG_DIR/"
    print_info "Press Ctrl+C to stop the system"
    echo ""
    
    # Run the system
    python3 -m src.kafka_self_healing.main --config $CONFIG_FILE
}

# Function to show status
show_status() {
    print_step "System Status"
    
    echo "Docker containers:"
    docker-compose -f $COMPOSE_FILE ps
    
    echo ""
    echo "Service endpoints:"
    echo "• Kafka Broker 1: localhost:9092"
    echo "• Kafka Broker 2: localhost:9093"
    echo "• Zookeeper: localhost:2181"
    echo "• MailHog UI: http://localhost:8025"
    
    echo ""
    echo "Log files:"
    if [ -d "$LOG_DIR" ]; then
        ls -la $LOG_DIR/
    else
        echo "No log files yet"
    fi
}

# Function to cleanup
cleanup() {
    print_step "Cleaning up..."
    docker-compose -f $COMPOSE_FILE down -v
    print_success "Cleanup complete"
}

# Function to show help
show_help() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start     - Start Kafka cluster and run self-healing system"
    echo "  setup     - Setup and start Kafka cluster only"
    echo "  test      - Run application tests"
    echo "  status    - Show system status"
    echo "  stop      - Stop and cleanup"
    echo "  help      - Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 start    # Complete setup and run"
    echo "  $0 setup    # Just start Kafka cluster"
    echo "  $0 test     # Test the application"
    echo "  $0 stop     # Stop everything"
}

# Main execution
main() {
    local command=${1:-start}
    
    case $command in
        "start")
            print_header
            check_docker
            setup_directories
            start_kafka_cluster
            test_application
            echo ""
            print_info "Starting self-healing system in 5 seconds..."
            print_info "Press Ctrl+C anytime to stop"
            sleep 5
            run_self_healing_system
            ;;
        "setup")
            print_header
            check_docker
            setup_directories
            start_kafka_cluster
            test_application
            echo ""
            print_success "Setup complete! You can now run:"
            echo "python3 -m src.kafka_self_healing.main --config $CONFIG_FILE"
            ;;
        "test")
            check_docker
            test_application
            ;;
        "status")
            show_status
            ;;
        "stop")
            cleanup
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Handle Ctrl+C gracefully
trap cleanup EXIT

# Run main function
main "$@"