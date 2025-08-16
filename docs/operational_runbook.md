# Kafka Self-Healing System - Operational Runbook

This runbook provides step-by-step procedures for operating, monitoring, and troubleshooting the Kafka Self-Healing system.

## Table of Contents

1. [System Overview](#system-overview)
2. [Installation and Setup](#installation-and-setup)
3. [Starting and Stopping](#starting-and-stopping)
4. [Monitoring and Health Checks](#monitoring-and-health-checks)
5. [Configuration Management](#configuration-management)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance Procedures](#maintenance-procedures)
8. [Emergency Procedures](#emergency-procedures)
9. [Log Analysis](#log-analysis)
10. [Performance Tuning](#performance-tuning)

## System Overview

The Kafka Self-Healing system continuously monitors Kafka brokers and Zookeeper nodes, automatically attempts recovery when failures are detected, and escalates to human operators when automated recovery fails.

### Key Components

- **Monitoring Service**: Health checks and failure detection
- **Recovery Engine**: Automated recovery actions
- **Notification Service**: Alert generation and delivery
- **Plugin System**: Extensible monitoring, recovery, and notification
- **Configuration Manager**: Centralized configuration handling
- **Logging Service**: Comprehensive audit trails

### System Requirements

- Python 3.8+
- Network access to Kafka brokers and Zookeeper nodes
- SMTP access for notifications (optional)
- Sufficient disk space for logs
- Appropriate permissions for recovery actions

## Installation and Setup

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Create necessary directories
mkdir -p /var/log/kafka-self-healing
mkdir -p /etc/kafka-self-healing
mkdir -p /opt/kafka-self-healing/plugins

# Set up log rotation
sudo cp scripts/logrotate.conf /etc/logrotate.d/kafka-self-healing
```

### Configuration

1. **Copy configuration template**:
   ```bash
   cp examples/config_production.yaml /etc/kafka-self-healing/config.yaml
   ```

2. **Edit configuration**:
   ```bash
   sudo nano /etc/kafka-self-healing/config.yaml
   ```

3. **Set environment variables**:
   ```bash
   export SMTP_PASSWORD="your-smtp-password"
   export KAFKA_USERNAME="your-kafka-username"
   export KAFKA_PASSWORD="your-kafka-password"
   ```

4. **Validate configuration**:
   ```bash
   python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml
   ```

### Service Installation

1. **Create systemd service file**:
   ```bash
   sudo cp scripts/kafka-self-healing.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

2. **Enable and start service**:
   ```bash
   sudo systemctl enable kafka-self-healing
   sudo systemctl start kafka-self-healing
   ```

## Starting and Stopping

### Manual Start/Stop

```bash
# Start the system
python -m src.kafka_self_healing.main --config /etc/kafka-self-healing/config.yaml

# Stop the system (Ctrl+C or SIGTERM)
kill -TERM <pid>
```

### Service Management

```bash
# Start service
sudo systemctl start kafka-self-healing

# Stop service
sudo systemctl stop kafka-self-healing

# Restart service
sudo systemctl restart kafka-self-healing

# Check status
sudo systemctl status kafka-self-healing

# View logs
sudo journalctl -u kafka-self-healing -f
```

### Graceful Shutdown

The system supports graceful shutdown:

1. Completes current monitoring cycles
2. Finishes ongoing recovery actions
3. Sends pending notifications
4. Closes log files and connections
5. Exits cleanly

**Shutdown timeout**: 60 seconds (configurable)

## Monitoring and Health Checks

### System Health

Check if the self-healing system is running properly:

```bash
# Check process status
ps aux | grep kafka_self_healing

# Check system logs
tail -f /var/log/kafka-self-healing/application.log

# Check metrics endpoint (if enabled)
curl http://localhost:8080/metrics
```

### Cluster Health

Monitor the health of your Kafka cluster:

```bash
# View current node status
grep "Node status" /var/log/kafka-self-healing/application.log | tail -10

# Check recent recovery actions
grep "Recovery" /var/log/kafka-self-healing/audit.log | tail -5

# Monitor notification activity
grep "Notification" /var/log/kafka-self-healing/application.log | tail -5
```

### Key Metrics to Monitor

1. **Monitoring Latency**: Time to complete health checks
2. **Recovery Success Rate**: Percentage of successful recoveries
3. **Notification Delivery**: Success rate of alert delivery
4. **System Resource Usage**: CPU, memory, disk usage
5. **Error Rates**: Frequency of monitoring/recovery failures

### Health Check Commands

```bash
# Test Kafka broker connectivity
kafka-broker-api-versions.sh --bootstrap-server kafka1:9092

# Test Zookeeper connectivity
echo "ruok" | nc zookeeper1 2181

# Test JMX connectivity
jconsole kafka1:9999

# Test SMTP connectivity
telnet smtp.example.com 587
```

## Configuration Management

### Configuration Validation

```bash
# Validate configuration syntax
python -m src.kafka_self_healing.config --validate config.yaml

# Test configuration with dry-run
python -m src.kafka_self_healing.main --config config.yaml --dry-run
```

### Configuration Updates

1. **Edit configuration file**:
   ```bash
   sudo nano /etc/kafka-self-healing/config.yaml
   ```

2. **Validate changes**:
   ```bash
   python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml
   ```

3. **Apply changes** (restart required):
   ```bash
   sudo systemctl restart kafka-self-healing
   ```

### Environment Variables

Common environment variables:

```bash
# SMTP Configuration
export SMTP_PASSWORD="smtp-password"
export SMTP_USERNAME="smtp-username"

# Kafka Authentication
export KAFKA_USERNAME="kafka-user"
export KAFKA_PASSWORD="kafka-password"

# SSL/TLS
export KEYSTORE_PASSWORD="keystore-password"
export TRUSTSTORE_PASSWORD="truststore-password"

# JMX Authentication
export JMX_USERNAME="jmx-user"
export JMX_PASSWORD="jmx-password"
```

## Troubleshooting

### Common Issues

#### 1. System Won't Start

**Symptoms**: Service fails to start, exits immediately

**Diagnosis**:
```bash
# Check service status
sudo systemctl status kafka-self-healing

# Check logs
sudo journalctl -u kafka-self-healing --no-pager

# Validate configuration
python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml
```

**Solutions**:
- Fix configuration errors
- Check file permissions
- Verify Python dependencies
- Ensure required directories exist

#### 2. Monitoring Failures

**Symptoms**: Nodes showing as unhealthy when they're actually healthy

**Diagnosis**:
```bash
# Check monitoring logs
grep "Monitoring" /var/log/kafka-self-healing/application.log | tail -20

# Test connectivity manually
telnet kafka1 9092
echo "ruok" | nc zookeeper1 2181
```

**Solutions**:
- Check network connectivity
- Verify firewall rules
- Adjust timeout settings
- Check authentication credentials

#### 3. Recovery Actions Failing

**Symptoms**: Recovery attempts always fail

**Diagnosis**:
```bash
# Check recovery logs
grep "Recovery" /var/log/kafka-self-healing/audit.log | tail -10

# Check system permissions
sudo -u kafka-healing systemctl status kafka
```

**Solutions**:
- Verify service permissions
- Check recovery script paths
- Validate Ansible/Salt configuration
- Test recovery commands manually

#### 4. Notifications Not Sent

**Symptoms**: No email notifications received

**Diagnosis**:
```bash
# Check notification logs
grep "Notification" /var/log/kafka-self-healing/application.log | tail -10

# Test SMTP connectivity
telnet smtp.example.com 587
```

**Solutions**:
- Verify SMTP configuration
- Check network connectivity
- Validate email credentials
- Test with external SMTP tool

### Debug Mode

Enable debug logging for detailed troubleshooting:

1. **Update configuration**:
   ```yaml
   logging:
     level: DEBUG
   ```

2. **Restart service**:
   ```bash
   sudo systemctl restart kafka-self-healing
   ```

3. **Monitor debug logs**:
   ```bash
   tail -f /var/log/kafka-self-healing/application.log
   ```

### Log Analysis

#### Error Patterns

```bash
# Find connection errors
grep -i "connection" /var/log/kafka-self-healing/application.log

# Find timeout errors
grep -i "timeout" /var/log/kafka-self-healing/application.log

# Find authentication errors
grep -i "auth" /var/log/kafka-self-healing/application.log

# Find configuration errors
grep -i "config" /var/log/kafka-self-healing/application.log
```

#### Performance Analysis

```bash
# Find slow operations
grep "slow" /var/log/kafka-self-healing/performance.log

# Monitor response times
grep "response_time" /var/log/kafka-self-healing/application.log | tail -20

# Check resource usage
grep "memory\|cpu" /var/log/kafka-self-healing/application.log
```

## Maintenance Procedures

### Regular Maintenance

#### Daily Tasks

1. **Check system status**:
   ```bash
   sudo systemctl status kafka-self-healing
   ```

2. **Review error logs**:
   ```bash
   grep -i error /var/log/kafka-self-healing/application.log | tail -10
   ```

3. **Monitor disk usage**:
   ```bash
   df -h /var/log/kafka-self-healing/
   ```

#### Weekly Tasks

1. **Review recovery statistics**:
   ```bash
   grep "Recovery.*success" /var/log/kafka-self-healing/audit.log | wc -l
   grep "Recovery.*failed" /var/log/kafka-self-healing/audit.log | wc -l
   ```

2. **Check notification delivery**:
   ```bash
   grep "Notification.*sent" /var/log/kafka-self-healing/application.log | wc -l
   ```

3. **Validate configuration**:
   ```bash
   python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml
   ```

#### Monthly Tasks

1. **Update dependencies**:
   ```bash
   pip install -r requirements.txt --upgrade
   ```

2. **Review and rotate logs**:
   ```bash
   sudo logrotate -f /etc/logrotate.d/kafka-self-healing
   ```

3. **Performance review**:
   ```bash
   python scripts/generate_performance_report.py --month
   ```

### Log Rotation

Automatic log rotation is configured via logrotate:

```bash
# Manual log rotation
sudo logrotate -f /etc/logrotate.d/kafka-self-healing

# Check log rotation status
sudo logrotate -d /etc/logrotate.d/kafka-self-healing
```

### Backup Procedures

#### Configuration Backup

```bash
# Backup configuration
sudo cp /etc/kafka-self-healing/config.yaml /backup/kafka-self-healing-config-$(date +%Y%m%d).yaml

# Backup entire configuration directory
sudo tar -czf /backup/kafka-self-healing-config-$(date +%Y%m%d).tar.gz /etc/kafka-self-healing/
```

#### Log Backup

```bash
# Backup logs
sudo tar -czf /backup/kafka-self-healing-logs-$(date +%Y%m%d).tar.gz /var/log/kafka-self-healing/
```

## Emergency Procedures

### System Failure

If the self-healing system fails:

1. **Immediate Actions**:
   ```bash
   # Check if Kafka cluster is still operational
   kafka-topics.sh --bootstrap-server kafka1:9092 --list
   
   # Check Zookeeper status
   echo "ruok" | nc zookeeper1 2181
   
   # Restart self-healing system
   sudo systemctl restart kafka-self-healing
   ```

2. **Fallback Monitoring**:
   ```bash
   # Manual health checks
   ./scripts/manual_health_check.sh
   
   # Set up temporary monitoring
   watch -n 30 './scripts/cluster_status.sh'
   ```

### Kafka Cluster Emergency

If the entire Kafka cluster fails:

1. **Assessment**:
   ```bash
   # Check all brokers
   for broker in kafka1 kafka2 kafka3; do
     echo "Checking $broker..."
     kafka-broker-api-versions.sh --bootstrap-server $broker:9092
   done
   
   # Check Zookeeper ensemble
   for zk in zk1 zk2 zk3; do
     echo "Checking $zk..."
     echo "ruok" | nc $zk 2181
   done
   ```

2. **Manual Recovery**:
   ```bash
   # Restart Zookeeper ensemble
   sudo systemctl restart zookeeper
   
   # Restart Kafka brokers (one at a time)
   sudo systemctl restart kafka
   ```

3. **Disable Self-Healing** (temporarily):
   ```bash
   sudo systemctl stop kafka-self-healing
   ```

### Notification Failure

If notifications are not being sent:

1. **Test SMTP manually**:
   ```bash
   echo "Test message" | mail -s "Test" admin@example.com
   ```

2. **Use alternative notification**:
   ```bash
   # Send manual alert
   ./scripts/send_manual_alert.sh "Kafka cluster issue detected"
   ```

## Performance Tuning

### Monitoring Optimization

```yaml
# Adjust monitoring intervals
monitoring:
  interval_seconds: 30  # Increase for less frequent checks
  timeout_seconds: 15   # Increase for slow networks
  concurrent_checks: true  # Enable for faster checks
```

### Recovery Optimization

```yaml
# Tune retry policies
recovery:
  max_attempts: 3
  initial_delay_seconds: 10
  backoff_multiplier: 1.5  # Reduce for faster retries
  max_delay_seconds: 120   # Reduce for faster escalation
```

### Resource Limits

```yaml
# Set resource limits
system:
  max_concurrent_operations: 10  # Adjust based on system capacity
  memory_limit_mb: 512          # Adjust based on available memory
  cpu_limit_percent: 50         # Adjust based on CPU availability
```

### Log Optimization

```yaml
# Optimize logging
logging:
  level: INFO              # Use INFO in production, DEBUG for troubleshooting
  max_size_mb: 100        # Adjust based on disk space
  backup_count: 5         # Adjust based on retention requirements
```

## Monitoring Dashboard

### Metrics Collection

If Prometheus integration is enabled:

```bash
# View metrics
curl http://localhost:8080/metrics

# Key metrics to monitor:
# - kafka_self_healing_monitoring_latency_seconds
# - kafka_self_healing_recovery_attempts_total
# - kafka_self_healing_recovery_success_total
# - kafka_self_healing_notifications_sent_total
```

### Grafana Dashboard

Import the provided Grafana dashboard:

```bash
# Import dashboard
curl -X POST \
  http://grafana:3000/api/dashboards/db \
  -H 'Content-Type: application/json' \
  -d @dashboards/kafka-self-healing-dashboard.json
```

## Contact Information

### Escalation Contacts

- **Primary On-Call**: oncall@company.com
- **Kafka Team**: kafka-team@company.com
- **Platform Team**: platform@company.com

### Support Resources

- **Documentation**: https://wiki.company.com/kafka-self-healing
- **Issue Tracker**: https://jira.company.com/projects/KAFKA
- **Chat Channel**: #kafka-support

## Appendix

### Useful Commands

```bash
# Quick status check
sudo systemctl status kafka-self-healing && \
tail -5 /var/log/kafka-self-healing/application.log

# Configuration test
python -m src.kafka_self_healing.main --config /etc/kafka-self-healing/config.yaml --test

# Log analysis
grep -E "(ERROR|CRITICAL)" /var/log/kafka-self-healing/application.log | tail -10

# Performance check
grep "response_time" /var/log/kafka-self-healing/performance.log | \
awk '{sum+=$NF; count++} END {print "Average response time:", sum/count "ms"}'
```

### Configuration Templates

See the `examples/` directory for configuration templates:

- `config_minimal.yaml`: Basic configuration
- `config_production.yaml`: Production-ready configuration
- `config_development.yaml`: Development configuration
- `config_docker.yaml`: Docker deployment configuration