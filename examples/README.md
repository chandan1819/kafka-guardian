# Configuration Examples

This directory contains sample configuration files for different deployment scenarios of the Kafka Self-Healing system.

## Available Configurations

### Basic Configurations

- **[config_minimal.yaml](config_minimal.yaml)** - Minimal configuration to get started
- **[config_development.yaml](config_development.yaml)** - Development environment setup
- **[config_testing.yaml](config_testing.yaml)** - Testing and validation configuration

### Production Configurations

- **[config_production.yaml](config_production.yaml)** - Production-ready configuration with full features
- **[config_docker.yaml](config_docker.yaml)** - Docker containerized deployment
- **[config_kubernetes.yaml](config_kubernetes.yaml)** - Kubernetes deployment configuration

### Advanced Configurations

- **[config_multi_datacenter.yaml](config_multi_datacenter.yaml)** - Multi-datacenter setup with failover

### Legacy Format Examples

- **[../sample_config.yaml](../sample_config.yaml)** - YAML format with environment variables
- **[../sample_config.json](../sample_config.json)** - JSON format example
- **[../sample_config.ini](../sample_config.ini)** - INI format example

## Quick Start

1. **Choose a configuration** that matches your deployment scenario
2. **Copy the configuration** to your desired location:
   ```bash
   cp examples/config_production.yaml /etc/kafka-self-healing/config.yaml
   ```
3. **Edit the configuration** to match your environment:
   ```bash
   nano /etc/kafka-self-healing/config.yaml
   ```
4. **Set environment variables** for sensitive data:
   ```bash
   export SMTP_PASSWORD="your-smtp-password"
   export KAFKA_USERNAME="your-kafka-username"
   export KAFKA_PASSWORD="your-kafka-password"
   ```
5. **Validate the configuration**:
   ```bash
   python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml
   ```

## Configuration Comparison

| Feature | Minimal | Development | Production | Docker | Kubernetes | Multi-DC |
|---------|---------|-------------|------------|--------|------------|----------|
| **Monitoring Methods** | Socket only | Socket, JMX | Socket, JMX, ZK | Socket, JMX, Docker | Socket, JMX, K8s | All methods |
| **Recovery Actions** | Service restart | Service, Script | Service, Ansible | Container restart | Pod restart | Cross-DC failover |
| **Security** | None | None | SSL/SASL | Basic | RBAC | Full security |
| **Notifications** | Email only | Email, Mock | Email, Multi-channel | Email | Email | Multi-channel |
| **Logging Level** | INFO | DEBUG | INFO | INFO | INFO | INFO |
| **Plugin Support** | No | Basic | Full | Docker plugins | K8s plugins | All plugins |
| **HA Support** | No | No | Yes | No | Yes | Yes |

## Environment-Specific Customization

### Development Environment

```yaml
# Fast monitoring for quick feedback
monitoring:
  interval_seconds: 10
  timeout_seconds: 5

# Reduced retry attempts for faster testing
recovery:
  max_attempts: 2
  initial_delay_seconds: 2

# Debug logging for troubleshooting
logging:
  level: DEBUG
```

### Production Environment

```yaml
# Balanced monitoring for reliability
monitoring:
  interval_seconds: 30
  timeout_seconds: 15
  health_check_retries: 3

# Comprehensive retry policy
recovery:
  max_attempts: 5
  initial_delay_seconds: 10
  backoff_multiplier: 2.0

# Structured logging for analysis
logging:
  level: INFO
  audit:
    enabled: true
```

### High-Traffic Environment

```yaml
# Optimized for performance
monitoring:
  concurrent_checks: true
  interval_seconds: 15

# Parallel recovery for faster resolution
recovery:
  parallel_recovery: true
  
# Resource limits for stability
system:
  max_concurrent_operations: 50
  memory_limit_mb: 2048
```

## Security Considerations

### Credential Management

**Environment Variables (Recommended):**
```bash
export SMTP_PASSWORD="secure-password"
export KAFKA_USERNAME="kafka-user"
export KAFKA_PASSWORD="kafka-password"
export JMX_USERNAME="jmx-user"
export JMX_PASSWORD="jmx-password"
```

**Configuration File:**
```yaml
security:
  credentials:
    storage_method: "environment"
```

### SSL/TLS Setup

```yaml
security:
  ssl:
    enabled: true
    keystore_path: "/etc/kafka-healing/ssl/keystore.jks"
    keystore_password_env: "KEYSTORE_PASSWORD"
    truststore_path: "/etc/kafka-healing/ssl/truststore.jks"
    truststore_password_env: "TRUSTSTORE_PASSWORD"
```

## Common Customizations

### Adding New Kafka Brokers

```yaml
cluster:
  kafka_brokers:
    - node_id: kafka1
      host: kafka1.example.com
      port: 9092
      jmx_port: 9999
    - node_id: kafka2  # Add new broker
      host: kafka2.example.com
      port: 9092
      jmx_port: 9999
```

### Custom Recovery Scripts

```yaml
recovery:
  actions: ["restart_service", "script"]
  script:
    script_directory: "/opt/custom-recovery"
    timeout: 120
    environment_variables:
      KAFKA_HOME: "/opt/kafka"
      CUSTOM_VAR: "value"
```

### Multiple Notification Channels

```yaml
notifications:
  smtp:
    # Primary email notifications
    to_emails:
      - "primary-oncall@company.com"
      - "kafka-team@company.com"
  
  # Additional notification methods via plugins
plugins:
  notification_plugins:
    slack_notification:
      enabled: true
      config:
        webhook_url: "${SLACK_WEBHOOK_URL}"
        channel: "#kafka-alerts"
```

## Validation and Testing

### Configuration Validation

```bash
# Validate syntax and structure
python -m src.kafka_self_healing.config --validate config.yaml

# Test with dry-run mode
python -m src.kafka_self_healing.main --config config.yaml --dry-run --duration 60

# Validate specific sections
python -m src.kafka_self_healing.config --validate-section monitoring config.yaml
```

### Connectivity Testing

```bash
# Test Kafka connectivity
kafka-broker-api-versions.sh --bootstrap-server kafka1:9092

# Test Zookeeper connectivity
echo "ruok" | nc zookeeper1 2181

# Test SMTP connectivity
telnet smtp.example.com 587
```

### End-to-End Testing

```bash
# Use testing configuration
cp examples/config_testing.yaml test_config.yaml

# Run with test configuration
python -m src.kafka_self_healing.main --config test_config.yaml

# Run failure simulation
python tests/failure_simulation.py --config test_config.yaml --scenario kafka_failure
```

## Migration Guide

### From Legacy Configuration

If you're migrating from an older configuration format:

1. **Backup existing configuration:**
   ```bash
   cp /etc/kafka-self-healing/config.yaml /etc/kafka-self-healing/config.yaml.backup
   ```

2. **Use migration tool:**
   ```bash
   python scripts/migrate_config.py --input config.yaml.backup --output config.yaml --target-version 2.0
   ```

3. **Validate migrated configuration:**
   ```bash
   python -m src.kafka_self_healing.config --validate config.yaml
   ```

### Configuration Version Compatibility

| Config Version | System Version | Notes |
|----------------|----------------|-------|
| 1.0 | 1.0-1.5 | Legacy format, limited features |
| 1.1 | 1.6-1.9 | Added plugin support |
| 2.0 | 2.0+ | Current format, full features |

## Troubleshooting

### Common Configuration Issues

1. **YAML Syntax Errors:**
   ```bash
   # Validate YAML syntax
   python -c "import yaml; yaml.safe_load(open('config.yaml'))"
   ```

2. **Environment Variable Issues:**
   ```bash
   # Check variable expansion
   python -c "
   import os
   config = open('config.yaml').read()
   print(os.path.expandvars(config))
   "
   ```

3. **Permission Issues:**
   ```bash
   # Check file permissions
   ls -la /etc/kafka-self-healing/config.yaml
   
   # Fix permissions if needed
   sudo chown kafka-healing:kafka-healing /etc/kafka-self-healing/config.yaml
   sudo chmod 600 /etc/kafka-self-healing/config.yaml
   ```

### Getting Help

- **Documentation:** See [docs/](../docs/) directory for comprehensive guides
- **Configuration Reference:** [docs/configuration_reference.md](../docs/configuration_reference.md)
- **Troubleshooting:** [docs/troubleshooting.md](../docs/troubleshooting.md)
- **Plugin Development:** [docs/plugin_development.md](../docs/plugin_development.md)

## Contributing

When adding new configuration examples:

1. **Follow naming convention:** `config_<scenario>.yaml`
2. **Include comprehensive comments** explaining each section
3. **Test the configuration** in the target environment
4. **Update this README** with the new example
5. **Add validation tests** in the test suite

For more information, see the [Contributing Guide](../CONTRIBUTING.md).