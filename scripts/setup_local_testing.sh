#!/bin/bash

# Kafka Self-Healing System - Local Testing Setup Script
# This script sets up the complete local testing environment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PYTHON_MIN_VERSION="3.8"
DOCKER_MIN_VERSION="20.0"
REQUIRED_MEMORY_GB=4
REQUIRED_DISK_GB=10

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

print_header() {
    echo -e "${BLUE}"
    echo "=================================================="
    echo "  Kafka Self-Healing System - Local Testing Setup"
    echo "=================================================="
    echo -e "${NC}"
}

# Function to check Python version
check_python() {
    print_status "Checking Python installation..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        print_success "Python $PYTHON_VERSION found"
        
        # Check if version is sufficient
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
            print_success "Python version is compatible"
        else
            print_error "Python 3.8+ is required, found $PYTHON_VERSION"
            print_status "Please install Python 3.8 or higher"
            exit 1
        fi
    else
        print_error "Python 3 is not installed"
        print_status "Please install Python 3.8 or higher"
        exit 1
    fi
}

# Function to check Docker installation
check_docker() {
    print_status "Checking Docker installation..."
    
    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version | cut -d' ' -f3 | cut -d',' -f1)
        print_success "Docker $DOCKER_VERSION found"
        
        # Check if Docker daemon is running
        if docker info &> /dev/null; then
            print_success "Docker daemon is running"
        else
            print_error "Docker daemon is not running"
            print_status "Please start Docker and try again"
            exit 1
        fi
    else
        print_error "Docker is not installed"
        print_status "Please install Docker and try again"
        exit 1
    fi
    
    # Check Docker Compose
    if command -v docker-compose &> /dev/null; then
        COMPOSE_VERSION=$(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1)
        print_success "Docker Compose $COMPOSE_VERSION found"
    else
        print_error "Docker Compose is not installed"
        print_status "Please install Docker Compose and try again"
        exit 1
    fi
}

# Function to check system resources
check_resources() {
    print_status "Checking system resources..."
    
    # Check available memory (macOS)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        MEMORY_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    else
        # Linux
        MEMORY_GB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
    fi
    
    if [ $MEMORY_GB -ge $REQUIRED_MEMORY_GB ]; then
        print_success "Memory: ${MEMORY_GB}GB available (${REQUIRED_MEMORY_GB}GB required)"
    else
        print_warning "Memory: ${MEMORY_GB}GB available (${REQUIRED_MEMORY_GB}GB recommended)"
    fi
    
    # Check available disk space
    DISK_GB=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
    if [ $DISK_GB -ge $REQUIRED_DISK_GB ]; then
        print_success "Disk space: ${DISK_GB}GB available (${REQUIRED_DISK_GB}GB required)"
    else
        print_warning "Disk space: ${DISK_GB}GB available (${REQUIRED_DISK_GB}GB recommended)"
    fi
}

# Function to setup Python environment
setup_python_env() {
    print_status "Setting up Python environment..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        print_status "Creating virtual environment..."
        python3 -m venv venv
        print_success "Virtual environment created"
    else
        print_success "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    print_success "Virtual environment activated"
    
    # Upgrade pip
    print_status "Upgrading pip..."
    pip install --upgrade pip
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        print_status "Installing Python dependencies..."
        pip install -r requirements.txt
        print_success "Python dependencies installed"
    fi
    
    # Install additional testing dependencies
    print_status "Installing testing dependencies..."
    pip install pytest pytest-cov pytest-html pytest-xdist psutil requests click docker pyyaml
    print_success "Testing dependencies installed"
}

# Function to setup directories
setup_directories() {
    print_status "Setting up directories..."
    
    # Create necessary directories
    mkdir -p test_logs
    mkdir -p test_reports
    mkdir -p .kiro/snapshots
    mkdir -p .kiro/backups
    
    print_success "Directories created"
}

# Function to validate configuration files
validate_configs() {
    print_status "Validating configuration files..."
    
    # Check if required files exist
    REQUIRED_FILES=(
        "docker-compose.test.yml"
        "examples/config_testing.yaml"
        ".kiro/settings/local-testing.yaml"
    )
    
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$file" ]; then
            print_success "Found: $file"
        else
            print_warning "Missing: $file"
        fi
    done
}

# Function to test Docker setup
test_docker_setup() {
    print_status "Testing Docker setup..."
    
    # Test Docker Compose file
    if [ -f "docker-compose.test.yml" ]; then
        print_status "Validating Docker Compose configuration..."
        if docker-compose -f docker-compose.test.yml config &> /dev/null; then
            print_success "Docker Compose configuration is valid"
        else
            print_error "Docker Compose configuration has errors"
            docker-compose -f docker-compose.test.yml config
            exit 1
        fi
    else
        print_error "docker-compose.test.yml not found"
        exit 1
    fi
}

# Function to create sample configuration
create_sample_config() {
    print_status "Creating sample local testing configuration..."
    
    if [ ! -f ".kiro/settings/local-testing.yaml" ]; then
        cat > .kiro/settings/local-testing.yaml << 'EOF'
# Local Testing Configuration
local_testing:
  default_profile: "development"
  auto_snapshot_before_tests: true
  
  snapshots:
    retention_days: 7
    max_snapshots: 10
    storage_path: ".kiro/snapshots"
    
  resources:
    max_memory_gb: 4
    max_disk_gb: 10
    
  profiles:
    development:
      kafka_brokers: 1
      zookeeper_nodes: 1
      log_level: "DEBUG"
    
    testing:
      kafka_brokers: 2
      zookeeper_nodes: 1
      log_level: "INFO"
      failure_simulation: true
EOF
        print_success "Sample configuration created"
    else
        print_success "Configuration already exists"
    fi
}

# Function to run quick test
run_quick_test() {
    print_status "Running quick validation test..."
    
    # Test Python imports
    if python3 -c "import yaml, docker, pytest; print('All imports successful')" 2>/dev/null; then
        print_success "Python dependencies are working"
    else
        print_error "Python dependency test failed"
        return 1
    fi
    
    # Test Docker connectivity
    if docker ps &> /dev/null; then
        print_success "Docker connectivity test passed"
    else
        print_error "Docker connectivity test failed"
        return 1
    fi
    
    print_success "Quick validation test completed"
}

# Function to display next steps
show_next_steps() {
    echo -e "${GREEN}"
    echo "=================================================="
    echo "  Setup Complete! Next Steps:"
    echo "=================================================="
    echo -e "${NC}"
    echo "1. Activate the virtual environment:"
    echo "   source venv/bin/activate"
    echo ""
    echo "2. Start the test environment:"
    echo "   make docker-up"
    echo ""
    echo "3. Run tests:"
    echo "   make test-unit          # Unit tests only"
    echo "   make test-e2e           # End-to-end tests"
    echo "   make test-all           # Complete test suite"
    echo ""
    echo "4. Clean up when done:"
    echo "   make docker-down"
    echo "   make clean"
    echo ""
    echo "5. For help:"
    echo "   make help"
    echo ""
    echo -e "${BLUE}Happy testing! 🚀${NC}"
}

# Main execution
main() {
    print_header
    
    # Check prerequisites
    check_python
    check_docker
    check_resources
    
    # Setup environment
    setup_python_env
    setup_directories
    validate_configs
    create_sample_config
    test_docker_setup
    
    # Run validation
    if run_quick_test; then
        show_next_steps
    else
        print_error "Setup validation failed. Please check the errors above."
        exit 1
    fi
}

# Run main function
main "$@"