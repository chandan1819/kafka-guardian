#!/bin/bash
set -e

# Docker entrypoint script for Kafka Guardian

# Default configuration
DEFAULT_CONFIG_PATH="/etc/kafka-guardian/config.yaml"
CONFIG_TEMPLATE_PATH="/etc/kafka-guardian/config.yaml.template"

# Function to log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

# Function to check if a service is available
wait_for_service() {
    local host=$1
    local port=$2
    local timeout=${3:-30}
    
    log "Waiting for $host:$port to be available..."
    
    for i in $(seq 1 $timeout); do
        if nc -z "$host" "$port" 2>/dev/null; then
            log "$host:$port is available"
            return 0
        fi
        sleep 1
    done
    
    log "Timeout waiting for $host:$port"
    return 1
}

# Function to substitute environment variables in config
substitute_env_vars() {
    local config_file=$1
    
    log "Substituting environment variables in $config_file"
    
    # Use envsubst to replace environment variables
    if command -v envsubst >/dev/null 2>&1; then
        envsubst < "$config_file" > "${config_file}.tmp" && mv "${config_file}.tmp" "$config_file"
    else
        # Fallback: simple sed-based substitution
        sed -i 's/\${SMTP_HOST:-localhost}/'"${SMTP_HOST:-localhost}"'/g' "$config_file"
        sed -i 's/\${SMTP_PORT:-587}/'"${SMTP_PORT:-587}"'/g' "$config_file"
        sed -i 's/\${SMTP_USERNAME}/'"${SMTP_USERNAME}"'/g' "$config_file"
        sed -i 's/\${SMTP_PASSWORD}/'"${SMTP_PASSWORD}"'/g' "$config_file"
    fi
}

# Function to validate configuration
validate_config() {
    local config_file=$1
    
    log "Validating configuration file: $config_file"
    
    if ! kafka-guardian-config --validate "$config_file"; then
        log "ERROR: Configuration validation failed"
        exit 1
    fi
    
    log "Configuration validation passed"
}

# Function to setup configuration
setup_config() {
    # If no config file exists, copy from template
    if [[ ! -f "$DEFAULT_CONFIG_PATH" && -f "$CONFIG_TEMPLATE_PATH" ]]; then
        log "Copying configuration template to $DEFAULT_CONFIG_PATH"
        cp "$CONFIG_TEMPLATE_PATH" "$DEFAULT_CONFIG_PATH"
    fi
    
    # Substitute environment variables
    if [[ -f "$DEFAULT_CONFIG_PATH" ]]; then
        substitute_env_vars "$DEFAULT_CONFIG_PATH"
        validate_config "$DEFAULT_CONFIG_PATH"
    else
        log "ERROR: No configuration file found at $DEFAULT_CONFIG_PATH"
        exit 1
    fi
}

# Function to wait for dependencies
wait_for_dependencies() {
    # Wait for Kafka brokers if specified
    if [[ -n "$KAFKA_BROKERS" ]]; then
        IFS=',' read -ra BROKERS <<< "$KAFKA_BROKERS"
        for broker in "${BROKERS[@]}"; do
            IFS=':' read -ra BROKER_PARTS <<< "$broker"
            host=${BROKER_PARTS[0]}
            port=${BROKER_PARTS[1]:-9092}
            wait_for_service "$host" "$port" 60
        done
    fi
    
    # Wait for Zookeeper if specified
    if [[ -n "$ZOOKEEPER_HOSTS" ]]; then
        IFS=',' read -ra ZK_HOSTS <<< "$ZOOKEEPER_HOSTS"
        for zk_host in "${ZK_HOSTS[@]}"; do
            IFS=':' read -ra ZK_PARTS <<< "$zk_host"
            host=${ZK_PARTS[0]}
            port=${ZK_PARTS[1]:-2181}
            wait_for_service "$host" "$port" 60
        done
    fi
}

# Function to setup logging
setup_logging() {
    # Create log directory if it doesn't exist
    local log_dir="/var/log/kafka-guardian"
    if [[ ! -d "$log_dir" ]]; then
        mkdir -p "$log_dir"
    fi
    
    # Set log level from environment
    if [[ -n "$KAFKA_GUARDIAN_LOG_LEVEL" ]]; then
        export LOG_LEVEL="$KAFKA_GUARDIAN_LOG_LEVEL"
    fi
}

# Function to handle shutdown signals
shutdown_handler() {
    log "Received shutdown signal, stopping Kafka Guardian..."
    
    # Send SIGTERM to the main process
    if [[ -n "$KAFKA_GUARDIAN_PID" ]]; then
        kill -TERM "$KAFKA_GUARDIAN_PID" 2>/dev/null || true
        
        # Wait for graceful shutdown
        local timeout=30
        for i in $(seq 1 $timeout); do
            if ! kill -0 "$KAFKA_GUARDIAN_PID" 2>/dev/null; then
                log "Kafka Guardian stopped gracefully"
                exit 0
            fi
            sleep 1
        done
        
        # Force kill if still running
        log "Force stopping Kafka Guardian"
        kill -KILL "$KAFKA_GUARDIAN_PID" 2>/dev/null || true
    fi
    
    exit 0
}

# Main execution
main() {
    log "Starting Kafka Guardian Docker container"
    
    # Setup signal handlers
    trap shutdown_handler SIGTERM SIGINT
    
    # Setup logging
    setup_logging
    
    # Setup configuration
    setup_config
    
    # Wait for dependencies if in wait mode
    if [[ "$WAIT_FOR_DEPENDENCIES" == "true" ]]; then
        wait_for_dependencies
    fi
    
    # Handle different commands
    case "$1" in
        "kafka-guardian")
            log "Starting Kafka Guardian service"
            
            # Start Kafka Guardian in background
            "$@" &
            KAFKA_GUARDIAN_PID=$!
            
            # Wait for the process
            wait $KAFKA_GUARDIAN_PID
            ;;
        "bash"|"sh")
            log "Starting interactive shell"
            exec "$@"
            ;;
        "config-validate")
            log "Validating configuration"
            kafka-guardian-config --validate "$DEFAULT_CONFIG_PATH"
            ;;
        "config-test")
            log "Testing configuration with dry-run"
            kafka-guardian --config "$DEFAULT_CONFIG_PATH" --dry-run --duration 60
            ;;
        *)
            log "Executing command: $*"
            exec "$@"
            ;;
    esac
}

# Run main function with all arguments
main "$@"