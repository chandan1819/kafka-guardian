# Configuration Reference Guide

This document provides a comprehensive reference for all configuration options in the Kafka Self-Healing system.

## Table of Contents

1. [Configuration File Formats](#configuration-file-formats)
2. [Environment Variable Substitution](#environment-variable-substitution)
3. [Cluster Configuration](#cluster-configuration)
4. [Monitoring Configuration](#monitoring-configuration)
5. [Recovery Configuration](#recovery-configuration)
6. [Notification Configuration](#notification-configuration)
7. [Logging Configuration](#logging-configuration)
8. [Security Configuration](#security-configuration)
9. [Plugin Configuration](#plugin-configuration)
10. [System Configuration](#system-configuration)
11. [Advanced Configuration](#advanced-configuration)
12. [Configuration Validation](#configuration-validation)

## Configuration File Formats

The system supports three configuration file formats:

### YAML Format (Recommended)

```yaml
# config.yaml
cluster:
  kafka_brokers:
    - node_id: kafka1
      host: localhost
      port: 9092
```

### JSON Format

```json
{
  "cluster": {
    "kafka_brokers": [
      {
        "node_id": "kafka1",
        "host": "localhost",
        "port": 9092
      }
    ]
  }
}
```

### INI Format

```ini
# config.ini
[cluster]
kafka_brokers = [{"node_id": "kafka1", "host": "localhost", "port": 9092}]
```

## Environment Variable Substitution

Environment variables can be used in configuration files:

```yaml
# Basic substitution
password: ${SMTP_PASSWORD}

# With default value
password: ${SMTP_PASSWORD:default-password}

# Nested substitution
host: ${KAFKA_HOST:${DEFAULT_HOST:localhost}}
```

### Common Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SMTP_USERNAME` | SMTP authentication username | `alerts@company.com` |
| `SMTP_PASSWORD` | SMTP authentication password | `secure-password` |
| `KAFKA_USERNAME` | Kafka SASL username | `kafka-user` |
| `KAFKA_PASSWORD` | Kafka SASL password | `kafka-password` |
| `JMX_USERNAME` | JMX authentication username | `jmx-user` |
| `JMX_PASSWORD` | JMX authentication password | `jmx-password` |
| `KEYSTORE_PASSWORD` | SSL keystore password | `keystore-pass` |
| `TRUSTSTORE_PASSWORD` | SSL truststore password | `truststore-pass` |

## Cluster Configuration

### Basic Cluster Structure

```yaml
cluster:
  # Kafka broker configuration
  kafka_brokers:
    - node_id: "kafka-1"                    # Required: Unique identifier
      host: "kafka1.example.com"            # Required: Hostname or IP
      port: 9092                            # Required: Kafka port
      jmx_port: 9999                        # Optional: JMX port
      datacenter: "dc1"                     # Optional: Datacenter identifier
      monitoring_methods: ["socket", "jmx"]  # Optional: Override global methods
      recovery_actions: ["restart_service"]  # Optional: Override global actions
      retry_policy:                         # Optional: Node-specific retry policy
        max_attempts: 3
        initial_delay_seconds: 10
        backoff_multiplier: 2.0
        max_delay_seconds: 300
      tags:                                 # Optional: Custom tags
        environment: "production"
        team: "platform"
  
  # Zookeeper node configuration
  zookeeper_nodes:
    - node_id: "zk-1"
      host: "zk1.example.com"
      port: 2181
      monitoring_methods: ["socket", "zookeeper"]
      recovery_actions: ["restart_service"]
```

### Node Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `node_id` | string | Yes | Unique identifier for the node |
| `host` | string | Yes | Hostname or IP address |
| `port` | integer | Yes | Primary service port |
| `jmx_port` | integer | No | JMX monitoring port |
| `datacenter` | string | No | Datacenter identifier |
| `monitoring_methods` | array | No | Override global monitoring methods |
| `recovery_actions` | array | No | Override global recovery actions |
| `retry_policy` | object | No | Node-specific retry configuration |
| `tags` | object | No | Custom metadata tags |

## Monitoring Configuration

### Global Monitoring Settings

```yaml
monitoring:
  # Basic settings
  interval_seconds: 30                     # How often to check nodes
  timeout_seconds: 15                      # Global timeout for checks
  concurrent_checks: true                  # Enable parallel checking
  health_check_retries: 2                  # Retries before marking unhealthy
  methods: ["socket", "jmx", "zookeeper"]  # Default monitoring methods
  
  # Method-specific settings
  jmx:
    connection_timeout: 10                 # JMX connection timeout
    read_timeout: 15                       # JMX read timeout
    authentication: true                   # Enable JMX authentication
    username: ${JMX_USERNAME}              # JMX username
    password: ${JMX_PASSWORD}              # JMX password
    ssl_enabled: false                     # Enable JMX over SSL
    metrics_to_check:                      # Specific JMX metrics
      - "kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec"
      - "kafka.server:type=BrokerTopicMetrics,name=BytesInPerSec"
  
  socket:
    connection_timeout: 5                  # Socket connection timeout
    read_timeout: 10                       # Socket read timeout
    verify_ssl: true                       # Verify SSL certificates
  
  zookeeper:
    four_letter_words: ["ruok", "stat"]    # ZK commands to use
    timeout: 10                            # ZK command timeout
    
  # Advanced settings
  failure_threshold: 3                     # Consecutive failures before action
  recovery_threshold: 2                    # Consecutive successes before recovery
  blackout_periods:                        # Maintenance windows
    - start_time: "02:00"
      end_time: "04:00"
      days: ["sunday"]
```

### Monitoring Method Options

| Method | Description | Configuration Options |
|--------|-------------|----------------------|
| `socket` | TCP connection test | `connection_timeout`, `read_timeout` |
| `jmx` | JMX metrics monitoring | `authentication`, `ssl_enabled`, `metrics_to_check` |
| `zookeeper` | ZK four-letter words | `four_letter_words`, `timeout` |
| `http` | HTTP endpoint check | `endpoint`, `expected_status`, `headers` |
| `cli` | Command-line tools | `commands`, `timeout`, `expected_output` |

## Recovery Configuration

### Global Recovery Settings

```yaml
recovery:
  # Basic retry policy
  max_attempts: 5                          # Maximum recovery attempts
  initial_delay_seconds: 10                # Initial delay between attempts
  backoff_multiplier: 2.0                  # Exponential backoff multiplier
  max_delay_seconds: 600                   # Maximum delay between attempts
  
  # Recovery actions (in order of preference)
  actions: ["restart_service", "ansible", "script"]
  
  # Action-specific configuration
  restart_service:
    service_manager: "systemctl"           # Service manager (systemctl, docker, k8s)
    kafka_service_name: "kafka"           # Kafka service name
    zookeeper_service_name: "zookeeper"   # Zookeeper service name
    timeout: 60                           # Service restart timeout
    pre_restart_commands:                 # Commands before restart
      - "systemctl stop kafka-connect"
    post_restart_commands:                # Commands after restart
      - "sleep 30"
      - "systemctl start kafka-connect"
  
  ansible:
    playbook_directory: "/opt/recovery/playbooks"
    inventory_file: "/opt/recovery/inventory"
    timeout: 300                          # Playbook execution timeout
    extra_vars:                           # Additional Ansible variables
      environment: "production"
      notification_webhook: "${SLACK_WEBHOOK}"
    vault_password_file: "/opt/recovery/.vault_pass"
  
  script:
    script_directory: "/opt/recovery/scripts"
    timeout: 120                          # Script execution timeout
    environment_variables:                # Environment for scripts
      KAFKA_HOME: "/opt/kafka"
      JAVA_HOME: "/usr/lib/jvm/java-11"
    
  # Advanced recovery options
  parallel_recovery: false                # Allow parallel recovery attempts
  recovery_validation:                    # Validate recovery success
    enabled: true
    timeout: 60
    methods: ["socket", "jmx"]
  
  escalation:                            # Escalation rules
    enabled: true
    escalation_delay: 300                # Delay before escalation
    escalation_actions: ["notification", "manual_intervention"]
```

### Recovery Action Types

| Action Type | Description | Configuration Options |
|-------------|-------------|----------------------|
| `restart_service` | System service restart | `service_manager`, `service_name`, `timeout` |
| `ansible` | Ansible playbook execution | `playbook_directory`, `inventory_file`, `extra_vars` |
| `script` | Shell script execution | `script_directory`, `timeout`, `environment_variables` |
| `docker` | Docker container operations | `container_name`, `operation`, `timeout` |
| `kubernetes` | Kubernetes pod operations | `namespace`, `pod_selector`, `operation` |

## Notification Configuration

### SMTP Configuration

```yaml
notifications:
  smtp:
    # Connection settings
    host: "smtp.company.com"              # SMTP server hostname
    port: 587                             # SMTP server port
    username: ${SMTP_USERNAME}            # SMTP username
    password: ${SMTP_PASSWORD}            # SMTP password
    use_tls: true                         # Enable TLS
    use_ssl: false                        # Enable SSL (alternative to TLS)
    timeout: 30                           # Connection timeout
    
    # Email settings
    from_email: "kafka-alerts@company.com"
    to_emails:                            # Primary recipients
      - "kafka-ops@company.com"
      - "platform-team@company.com"
    cc_emails:                            # CC recipients
      - "manager@company.com"
    bcc_emails:                           # BCC recipients
      - "audit@company.com"
    
    # Email templates
    templates:
      failure_subject: "[ALERT] Kafka Node {node_id} Recovery Failed"
      recovery_subject: "[INFO] Kafka Node {node_id} Recovered"
      escalation_subject: "[CRITICAL] Kafka Node {node_id} Requires Manual Intervention"
      
      failure_body: |
        Kafka node recovery has failed after multiple attempts.
        
        Node Details:
        - Node ID: {node_id}
        - Host: {host}:{port}
        - Type: {node_type}
        - Datacenter: {datacenter}
        
        Recovery History:
        {recovery_history}
        
        Please investigate immediately.
      
      recovery_body: |
        Kafka node has recovered successfully.
        
        Node Details:
        - Node ID: {node_id}
        - Host: {host}:{port}
        - Recovery Time: {recovery_time}
  
  # Notification triggers
  triggers:
    on_recovery_failure: true             # Send on recovery failure
    on_recovery_success: true             # Send on recovery success
    on_max_retries_exceeded: true         # Send when max retries reached
    on_system_error: true                 # Send on system errors
    on_configuration_change: false        # Send on config changes
  
  # Rate limiting
  rate_limiting:
    max_notifications_per_hour: 20        # Maximum notifications per hour
    cooldown_period_minutes: 10           # Cooldown between notifications
    escalation_threshold: 3               # Failures before escalation
    
  # Advanced notification settings
  delivery_retry:
    max_attempts: 3                       # Retry failed deliveries
    retry_delay_seconds: 60               # Delay between retries
    
  content_filtering:
    include_sensitive_data: false         # Include passwords/keys in notifications
    max_log_lines: 50                     # Maximum log lines to include
    truncate_long_messages: true          # Truncate long error messages
```

### Template Variables

Available variables for email templates:

| Variable | Description | Example |
|----------|-------------|---------|
| `{node_id}` | Node identifier | `kafka-1` |
| `{host}` | Node hostname | `kafka1.example.com` |
| `{port}` | Node port | `9092` |
| `{node_type}` | Node type | `kafka_broker` |
| `{datacenter}` | Datacenter | `us-east-1` |
| `{failure_time}` | Failure timestamp | `2023-10-15 14:30:00` |
| `{recovery_time}` | Recovery timestamp | `2023-10-15 14:35:00` |
| `{recovery_history}` | Recovery attempt details | Multi-line history |
| `{error_message}` | Last error message | Connection refused |
| `{attempts}` | Number of attempts | `3` |

## Logging Configuration

### Basic Logging Settings

```yaml
logging:
  # Application logging
  level: "INFO"                           # Log level (DEBUG, INFO, WARN, ERROR)
  file: "/var/log/kafka-self-healing/application.log"
  max_size_mb: 100                        # Maximum log file size
  backup_count: 10                        # Number of backup files
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  
  # Audit logging
  audit:
    enabled: true                         # Enable audit logging
    file: "/var/log/kafka-self-healing/audit.log"
    max_size_mb: 200                      # Audit log size limit
    backup_count: 20                      # Audit log backups
    include_sensitive_data: false         # Log sensitive information
    log_successful_operations: true       # Log successful operations
    
  # Performance logging
  performance:
    enabled: true                         # Enable performance logging
    file: "/var/log/kafka-self-healing/performance.log"
    log_slow_operations: true             # Log slow operations
    slow_operation_threshold_ms: 1000     # Threshold for slow operations
    include_memory_usage: true            # Include memory metrics
    include_cpu_usage: true               # Include CPU metrics
    
  # Console logging
  console:
    enabled: true                         # Enable console output
    level: "INFO"                         # Console log level
    format: "%(levelname)s: %(message)s"  # Console format
    
  # Structured logging
  structured:
    enabled: false                        # Enable JSON structured logging
    format: "json"                        # Format (json, logfmt)
    include_context: true                 # Include contextual information
    
  # Log filtering
  filters:
    exclude_patterns:                     # Patterns to exclude from logs
      - "password"
      - "secret"
      - "token"
    include_only_levels: []               # Only log specific levels
    rate_limit_identical: true            # Rate limit identical messages
```

### Log Rotation Configuration

```yaml
logging:
  rotation:
    # Time-based rotation
    when: "midnight"                      # Rotation time (midnight, hourly)
    interval: 1                           # Rotation interval
    
    # Size-based rotation
    max_bytes: 104857600                  # 100MB in bytes
    backup_count: 10                      # Number of backup files
    
    # Compression
    compress: true                        # Compress rotated logs
    compression_format: "gzip"            # Compression format
    
    # Cleanup
    cleanup_older_than_days: 30           # Delete logs older than X days
```

## Security Configuration

### Credential Management

```yaml
security:
  credentials:
    # Storage method
    storage_method: "environment"         # environment, file, vault, k8s_secrets
    
    # File-based credentials
    credentials_file: "/etc/kafka-healing/credentials.json"
    encryption_key_file: "/etc/kafka-healing/encryption.key"
    
    # External vault integration
    vault:
      url: "https://vault.company.com"
      token_env: "VAULT_TOKEN"
      secret_path: "secret/kafka-healing"
      
    # Kubernetes secrets
    kubernetes:
      secret_name: "kafka-healing-secrets"
      namespace: "kafka"
```

### SSL/TLS Configuration

```yaml
security:
  ssl:
    enabled: true                         # Enable SSL/TLS
    protocol: "TLSv1.2"                   # SSL protocol version
    
    # Certificate configuration
    keystore_path: "/etc/kafka-healing/ssl/keystore.jks"
    keystore_password_env: "KEYSTORE_PASSWORD"
    keystore_type: "JKS"                  # JKS, PKCS12
    
    truststore_path: "/etc/kafka-healing/ssl/truststore.jks"
    truststore_password_env: "TRUSTSTORE_PASSWORD"
    truststore_type: "JKS"
    
    # Certificate validation
    verify_certificates: true             # Verify SSL certificates
    check_hostname: true                  # Verify hostname in certificates
    
    # Advanced SSL settings
    cipher_suites:                        # Allowed cipher suites
      - "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"
      - "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
```

### SASL Authentication

```yaml
security:
  sasl:
    enabled: true                         # Enable SASL authentication
    mechanism: "SCRAM-SHA-256"            # SASL mechanism
    username_env: "KAFKA_USERNAME"        # Username environment variable
    password_env: "KAFKA_PASSWORD"        # Password environment variable
    
    # Kerberos configuration (for GSSAPI)
    kerberos:
      principal: "kafka-healing@REALM.COM"
      keytab_file: "/etc/kafka-healing/kafka-healing.keytab"
      krb5_conf: "/etc/krb5.conf"
```

## Plugin Configuration

### Plugin Discovery

```yaml
plugins:
  discovery:
    enabled: true                         # Enable plugin discovery
    directories:                          # Plugin directories
      - "/opt/kafka-healing/plugins/monitoring"
      - "/opt/kafka-healing/plugins/recovery"
      - "/opt/kafka-healing/plugins/notification"
    auto_load: true                       # Automatically load discovered plugins
    plugin_timeout: 30                    # Plugin operation timeout
    
  # Plugin-specific configuration
  monitoring_plugins:
    jmx_monitoring:
      enabled: true                       # Enable this plugin
      priority: 1                         # Plugin priority (lower = higher priority)
      config:                            # Plugin-specific configuration
        connection_timeout: 10
        read_timeout: 15
        
    prometheus_monitoring:
      enabled: false
      priority: 2
      config:
        prometheus_url: "http://prometheus:9090"
        metrics_queries:
          kafka_messages: 'rate(kafka_server_brokertopicmetrics_messagesinpersec[5m])'
  
  recovery_plugins:
    service_restart:
      enabled: true
      priority: 1
      
    ansible_recovery:
      enabled: true
      priority: 2
      config:
        playbook_directory: "/opt/recovery/playbooks"
        
  notification_plugins:
    email_notification:
      enabled: true
      priority: 1
      
    slack_notification:
      enabled: false
      priority: 2
      config:
        webhook_url: "${SLACK_WEBHOOK_URL}"
        channel: "#kafka-alerts"
```

## System Configuration

### Resource Management

```yaml
system:
  # Resource limits
  max_concurrent_operations: 20          # Maximum concurrent operations
  memory_limit_mb: 1024                  # Memory limit in MB
  cpu_limit_percent: 75                  # CPU usage limit percentage
  
  # Threading
  thread_pool_size: 10                   # Thread pool size
  max_queue_size: 100                    # Maximum queue size
  
  # Timeouts
  shutdown_timeout_seconds: 60           # Graceful shutdown timeout
  operation_timeout_seconds: 300         # Default operation timeout
  
  # Self-monitoring
  self_monitoring:
    enabled: true                         # Enable self-monitoring
    interval_seconds: 30                  # Self-check interval
    memory_threshold_mb: 800              # Memory usage threshold
    cpu_threshold_percent: 60             # CPU usage threshold
    disk_threshold_percent: 85            # Disk usage threshold
    
  # Metrics export
  metrics:
    enabled: true                         # Enable metrics export
    port: 8080                           # Metrics server port
    endpoint: "/metrics"                  # Metrics endpoint path
    format: "prometheus"                  # Metrics format (prometheus, json)
    include_system_metrics: true          # Include system metrics
    include_jvm_metrics: true             # Include JVM metrics
    
  # Health checks
  health_check:
    enabled: true                         # Enable health check endpoint
    port: 8081                           # Health check port
    endpoint: "/health"                   # Health check endpoint
```

### High Availability

```yaml
system:
  high_availability:
    enabled: true                         # Enable HA mode
    
    # Leader election
    leader_election:
      enabled: true                       # Enable leader election
      method: "file_lock"                 # file_lock, etcd, consul, k8s
      lock_path: "/var/lock/kafka-healing"
      lease_duration_seconds: 30          # Leader lease duration
      renew_deadline_seconds: 20          # Lease renewal deadline
      retry_period_seconds: 5             # Retry period for leader election
      
    # Cluster coordination
    cluster:
      node_id: "${HOSTNAME}"              # Unique node identifier
      cluster_members:                    # Other cluster members
        - "kafka-healing-1:8080"
        - "kafka-healing-2:8080"
      heartbeat_interval_seconds: 10      # Heartbeat interval
      failure_detection_timeout: 30       # Failure detection timeout
```

## Advanced Configuration

### Multi-Datacenter Setup

```yaml
# Multi-datacenter configuration
multi_datacenter:
  enabled: true                           # Enable multi-DC support
  
  datacenters:
    dc1:
      name: "Primary Datacenter"
      location: "US East"
      priority: 1                         # Primary DC
      is_primary: true
      
    dc2:
      name: "Secondary Datacenter"
      location: "US West"
      priority: 2                         # Secondary DC
      is_primary: false
      
  # Cross-DC monitoring
  cross_dc_monitoring:
    enabled: true                         # Enable cross-DC monitoring
    latency_threshold_ms: 500             # Latency threshold
    bandwidth_threshold_mbps: 100         # Bandwidth threshold
    
  # Failover configuration
  failover:
    enabled: true                         # Enable automatic failover
    strategy: "active_passive"            # active_passive, active_active
    health_threshold: 0.5                 # Health threshold for failover
    failover_timeout_seconds: 900         # Failover timeout
```

### Development and Testing

```yaml
# Development/testing configuration
development:
  debug_mode: true                        # Enable debug mode
  mock_mode: false                        # Enable mock mode
  hot_reload: true                        # Enable configuration hot reload
  
  # Failure simulation
  failure_simulation:
    enabled: false                        # Enable failure simulation
    failure_rate: 0.1                     # Failure rate (0.0-1.0)
    scenarios:                            # Failure scenarios
      - name: "network_partition"
        probability: 0.05
        duration_seconds: 60
        
  # Testing hooks
  testing:
    validate_operations: true             # Validate all operations
    record_metrics: true                  # Record detailed metrics
    generate_test_data: false             # Generate test data
```

## Configuration Validation

### Validation Rules

The system validates configuration on startup:

1. **Required Fields**: All required fields must be present
2. **Data Types**: Fields must have correct data types
3. **Value Ranges**: Numeric values must be within valid ranges
4. **Dependencies**: Dependent configurations must be consistent
5. **External Resources**: External resources must be accessible

### Validation Commands

```bash
# Validate configuration file
python -m src.kafka_self_healing.config --validate /path/to/config.yaml

# Test configuration with dry-run
python -m src.kafka_self_healing.main --config /path/to/config.yaml --dry-run

# Validate specific sections
python -m src.kafka_self_healing.config --validate-section monitoring /path/to/config.yaml
```

### Common Validation Errors

| Error | Description | Solution |
|-------|-------------|----------|
| `Missing required field` | Required configuration missing | Add the required field |
| `Invalid data type` | Wrong data type for field | Correct the data type |
| `Value out of range` | Numeric value outside valid range | Adjust the value |
| `Invalid format` | Incorrect format (e.g., email, URL) | Fix the format |
| `Dependency conflict` | Conflicting configuration options | Resolve the conflict |

### Configuration Schema

The system uses JSON Schema for validation. Key schema rules:

- **Ports**: Must be integers between 1-65535
- **Timeouts**: Must be positive integers
- **Email addresses**: Must be valid email format
- **File paths**: Must be absolute paths for production
- **URLs**: Must be valid HTTP/HTTPS URLs
- **Percentages**: Must be between 0-100

For complete schema documentation, see the `schema/` directory in the project repository.