# Kafka Self-Healing System - Setup and Deployment Guide

This guide provides comprehensive instructions for setting up and deploying the Kafka Self-Healing system in various environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Methods](#installation-methods)
3. [Configuration](#configuration)
4. [Deployment Scenarios](#deployment-scenarios)
5. [Security Setup](#security-setup)
6. [Monitoring Integration](#monitoring-integration)
7. [Testing and Validation](#testing-and-validation)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 18.04+, CentOS 7+, RHEL 7+)
- **Python**: 3.8 or higher
- **Memory**: Minimum 512MB RAM, Recommended 1GB+
- **Disk Space**: Minimum 1GB for logs and temporary files
- **Network**: Access to Kafka brokers and Zookeeper nodes

### Software Dependencies

```bash
# Python packages (installed automatically)
pip install -r requirements.txt

# System packages (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git curl

# System packages (CentOS/RHEL)
sudo yum install -y python3 python3-pip git curl
```

### Network Requirements

- **Kafka Brokers**: TCP access to Kafka ports (default 9092)
- **Zookeeper**: TCP access to Zookeeper ports (default 2181)
- **JMX**: TCP access to JMX ports (if JMX monitoring enabled)
- **SMTP**: TCP access to SMTP server (for notifications)
- **DNS**: Proper DNS resolution for all cluster nodes

### Permissions

The system requires appropriate permissions for:

- Reading configuration files
- Writing log files
- Executing recovery scripts
- Managing services (if using systemctl recovery)
- Network access to cluster nodes

## Installation Methods

### Method 1: Package Installation (Recommended)

```bash
# Install from PyPI (when available)
pip install kafka-self-healing

# Or install from source
git clone https://github.com/company/kafka-self-healing.git
cd kafka-self-healing
pip install -e .
```

### Method 2: Manual Installation

```bash
# Clone repository
git clone https://github.com/company/kafka-self-healing.git
cd kafka-self-healing

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .
```

### Method 3: Docker Installation

```bash
# Build Docker image
docker build -t kafka-self-healing .

# Or pull from registry
docker pull company/kafka-self-healing:latest
```

### Method 4: Ansible Installation

```bash
# Use provided Ansible playbook
ansible-playbook -i inventory playbooks/install.yml
```

## Configuration

### Basic Configuration

1. **Create configuration directory**:
   ```bash
   sudo mkdir -p /etc/kafka-self-healing
   sudo mkdir -p /var/log/kafka-self-healing
   sudo mkdir -p /opt/kafka-self-healing/plugins
   ```

2. **Copy configuration template**:
   ```bash
   # For production
   cp examples/config_production.yaml /etc/kafka-self-healing/config.yaml
   
   # For development
   cp examples/config_development.yaml /etc/kafka-self-healing/config.yaml
   
   # For Docker
   cp examples/config_docker.yaml /etc/kafka-self-healing/config.yaml
   ```

3. **Edit configuration**:
   ```bash
   sudo nano /etc/kafka-self-healing/config.yaml
   ```

### Essential Configuration Sections

#### Cluster Configuration

```yaml
cluster:
  kafka_brokers:
    - node_id: kafka1
      host: kafka1.example.com
      port: 9092
      jmx_port: 9999
    - node_id: kafka2
      host: kafka2.example.com
      port: 9092
      jmx_port: 9999

  zookeeper_nodes:
    - node_id: zk1
      host: zk1.example.com
      port: 2181
    - node_id: zk2
      host: zk2.example.com
      port: 2181
```

#### Monitoring Configuration

```yaml
monitoring:
  interval_seconds: 30
  timeout_seconds: 15
  methods: ["socket", "jmx", "zookeeper"]
```

#### Recovery Configuration

```yaml
recovery:
  max_attempts: 3
  initial_delay_seconds: 10
  actions: ["restart_service", "script"]
```

#### Notification Configuration

```yaml
notifications:
  smtp:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    from_email: kafka-alerts@example.com
    to_emails:
      - admin@example.com
```

### Environment Variables

Set up environment variables for sensitive configuration:

```bash
# Create environment file
sudo nano /etc/kafka-self-healing/environment

# Add variables
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
KAFKA_USERNAME=your-kafka-username
KAFKA_PASSWORD=your-kafka-password
JMX_USERNAME=your-jmx-username
JMX_PASSWORD=your-jmx-password
```

Load environment variables:

```bash
# In systemd service
EnvironmentFile=/etc/kafka-self-healing/environment

# Or export manually
source /etc/kafka-self-healing/environment
```

## Deployment Scenarios

### Scenario 1: Standalone Server Deployment

**Use Case**: Single server monitoring a Kafka cluster

**Setup**:

1. **Install on dedicated server**:
   ```bash
   # Install system
   pip install kafka-self-healing
   
   # Create user
   sudo useradd -r -s /bin/false kafka-healing
   
   # Set permissions
   sudo chown -R kafka-healing:kafka-healing /var/log/kafka-self-healing
   sudo chown kafka-healing:kafka-healing /etc/kafka-self-healing/config.yaml
   ```

2. **Create systemd service**:
   ```bash
   sudo cp scripts/kafka-self-healing.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable kafka-self-healing
   sudo systemctl start kafka-self-healing
   ```

3. **Configure log rotation**:
   ```bash
   sudo cp scripts/logrotate.conf /etc/logrotate.d/kafka-self-healing
   ```

### Scenario 2: Docker Deployment

**Use Case**: Containerized deployment with Docker

**Setup**:

1. **Create Docker configuration**:
   ```bash
   # Create config directory
   mkdir -p ./config ./logs
   
   # Copy configuration
   cp examples/config_docker.yaml ./config/config.yaml
   ```

2. **Run with Docker**:
   ```bash
   docker run -d \
     --name kafka-self-healing \
     --restart unless-stopped \
     -v $(pwd)/config:/etc/kafka-self-healing \
     -v $(pwd)/logs:/var/log/kafka-self-healing \
     -e SMTP_PASSWORD=your-password \
     kafka-self-healing:latest
   ```

3. **Or use Docker Compose**:
   ```yaml
   version: '3.8'
   services:
     kafka-self-healing:
       image: kafka-self-healing:latest
       container_name: kafka-self-healing
       restart: unless-stopped
       volumes:
         - ./config:/etc/kafka-self-healing
         - ./logs:/var/log/kafka-self-healing
       environment:
         - SMTP_PASSWORD=${SMTP_PASSWORD}
         - KAFKA_USERNAME=${KAFKA_USERNAME}
         - KAFKA_PASSWORD=${KAFKA_PASSWORD}
       networks:
         - kafka-network
   ```

### Scenario 3: Kubernetes Deployment

**Use Case**: Kubernetes cluster deployment

**Setup**:

1. **Create ConfigMap**:
   ```yaml
   apiVersion: v1
   kind: ConfigMap
   metadata:
     name: kafka-self-healing-config
   data:
     config.yaml: |
       # Your configuration here
   ```

2. **Create Secret**:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: kafka-self-healing-secrets
   type: Opaque
   data:
     smtp-password: <base64-encoded-password>
     kafka-password: <base64-encoded-password>
   ```

3. **Create Deployment**:
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: kafka-self-healing
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: kafka-self-healing
     template:
       metadata:
         labels:
           app: kafka-self-healing
       spec:
         containers:
         - name: kafka-self-healing
           image: kafka-self-healing:latest
           env:
           - name: SMTP_PASSWORD
             valueFrom:
               secretKeyRef:
                 name: kafka-self-healing-secrets
                 key: smtp-password
           volumeMounts:
           - name: config
             mountPath: /etc/kafka-self-healing
           - name: logs
             mountPath: /var/log/kafka-self-healing
         volumes:
         - name: config
           configMap:
             name: kafka-self-healing-config
         - name: logs
           emptyDir: {}
   ```

### Scenario 4: High Availability Deployment

**Use Case**: Multiple instances for redundancy

**Setup**:

1. **Deploy multiple instances**:
   ```bash
   # Instance 1
   systemctl start kafka-self-healing@instance1
   
   # Instance 2
   systemctl start kafka-self-healing@instance2
   ```

2. **Configure leader election** (if supported):
   ```yaml
   high_availability:
     enabled: true
     leader_election:
       method: "file_lock"  # or "etcd", "consul"
       lock_path: "/var/lock/kafka-self-healing"
   ```

3. **Load balancer configuration**:
   ```nginx
   upstream kafka-healing {
       server kafka-healing-1:8080;
       server kafka-healing-2:8080;
   }
   ```

### Scenario 5: Multi-Datacenter Deployment

**Use Case**: Monitoring Kafka clusters across multiple datacenters

**Setup**:

1. **Deploy per datacenter**:
   ```bash
   # DC1 configuration
   cluster:
     name: "kafka-dc1"
     datacenters: ["dc1"]
   
   # DC2 configuration
   cluster:
     name: "kafka-dc2"
     datacenters: ["dc2"]
   ```

2. **Configure cross-DC monitoring**:
   ```yaml
   monitoring:
     cross_datacenter:
       enabled: true
       remote_clusters:
         - name: "kafka-dc2"
           endpoint: "https://kafka-healing-dc2.example.com:8080"
   ```

## Security Setup

### SSL/TLS Configuration

1. **Generate certificates** (if needed):
   ```bash
   # Create keystore
   keytool -genkey -alias kafka-healing -keyalg RSA -keystore keystore.jks
   
   # Create truststore
   keytool -import -alias ca-cert -file ca-cert.pem -keystore truststore.jks
   ```

2. **Configure SSL in config.yaml**:
   ```yaml
   security:
     ssl:
       enabled: true
       keystore_path: "/etc/kafka-self-healing/ssl/keystore.jks"
       keystore_password_env: "KEYSTORE_PASSWORD"
       truststore_path: "/etc/kafka-self-healing/ssl/truststore.jks"
       truststore_password_env: "TRUSTSTORE_PASSWORD"
   ```

### SASL Authentication

```yaml
security:
  sasl:
    enabled: true
    mechanism: "SCRAM-SHA-256"
    username_env: "KAFKA_USERNAME"
    password_env: "KAFKA_PASSWORD"
```

### Credential Management

1. **Environment variables** (recommended):
   ```bash
   export SMTP_PASSWORD="secure-password"
   export KAFKA_PASSWORD="kafka-password"
   ```

2. **Encrypted configuration files**:
   ```yaml
   security:
     credentials:
       storage_method: "file"
       encryption_key_file: "/etc/kafka-self-healing/encryption.key"
   ```

3. **External credential stores**:
   ```yaml
   security:
     credentials:
       storage_method: "external"
       vault_url: "https://vault.example.com"
       vault_token_env: "VAULT_TOKEN"
   ```

### Firewall Configuration

```bash
# Allow access to Kafka brokers
sudo ufw allow out 9092/tcp

# Allow access to Zookeeper
sudo ufw allow out 2181/tcp

# Allow access to JMX ports
sudo ufw allow out 9999/tcp

# Allow access to SMTP
sudo ufw allow out 587/tcp
```

## Monitoring Integration

### Prometheus Integration

1. **Enable metrics endpoint**:
   ```yaml
   system:
     metrics:
       enabled: true
       port: 8080
       endpoint: "/metrics"
       format: "prometheus"
   ```

2. **Configure Prometheus scraping**:
   ```yaml
   # prometheus.yml
   scrape_configs:
     - job_name: 'kafka-self-healing'
       static_configs:
         - targets: ['kafka-healing:8080']
   ```

### Grafana Dashboard

1. **Import dashboard**:
   ```bash
   curl -X POST \
     http://grafana:3000/api/dashboards/db \
     -H 'Content-Type: application/json' \
     -d @dashboards/kafka-self-healing-dashboard.json
   ```

### Log Aggregation

#### ELK Stack Integration

1. **Configure Filebeat**:
   ```yaml
   filebeat.inputs:
   - type: log
     paths:
       - /var/log/kafka-self-healing/*.log
     fields:
       service: kafka-self-healing
   ```

2. **Logstash configuration**:
   ```ruby
   filter {
     if [fields][service] == "kafka-self-healing" {
       grok {
         match => { "message" => "%{TIMESTAMP_ISO8601:timestamp} - %{WORD:logger} - %{LOGLEVEL:level} - %{GREEDYDATA:message}" }
       }
     }
   }
   ```

#### Fluentd Integration

```xml
<source>
  @type tail
  path /var/log/kafka-self-healing/*.log
  pos_file /var/log/fluentd/kafka-self-healing.log.pos
  tag kafka.self-healing
  format multiline
  format_firstline /^\d{4}-\d{2}-\d{2}/
</source>
```

## Testing and Validation

### Configuration Validation

```bash
# Validate configuration syntax
python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml

# Test configuration with dry-run
python -m src.kafka_self_healing.main --config /etc/kafka-self-healing/config.yaml --dry-run --duration 60
```

### Connectivity Testing

```bash
# Test Kafka connectivity
kafka-broker-api-versions.sh --bootstrap-server kafka1:9092

# Test Zookeeper connectivity
echo "ruok" | nc zookeeper1 2181

# Test JMX connectivity
jconsole kafka1:9999

# Test SMTP connectivity
python -c "
import smtplib
server = smtplib.SMTP('smtp.example.com', 587)
server.starttls()
server.login('username', 'password')
server.quit()
print('SMTP connection successful')
"
```

### End-to-End Testing

```bash
# Run comprehensive test suite
make test-all

# Run specific test scenarios
python tests/failure_simulation.py --scenario kafka1_failure --duration 60

# Performance testing
python tests/benchmark.py --config /etc/kafka-self-healing/config.yaml
```

### Monitoring Validation

```bash
# Check monitoring functionality
curl http://localhost:8080/metrics | grep kafka_self_healing

# Verify log output
tail -f /var/log/kafka-self-healing/application.log

# Test notification delivery
python -c "
from src.kafka_self_healing.notification import EmailNotifier
notifier = EmailNotifier(config)
notifier.send_test_notification()
"
```

## Troubleshooting

### Common Installation Issues

#### Python Version Compatibility

```bash
# Check Python version
python3 --version

# Install specific Python version (Ubuntu)
sudo apt-get install python3.8 python3.8-venv python3.8-dev

# Create virtual environment with specific version
python3.8 -m venv venv
```

#### Dependency Conflicts

```bash
# Clean install
pip uninstall kafka-self-healing
pip cache purge
pip install --no-cache-dir kafka-self-healing

# Use virtual environment
python3 -m venv clean-env
source clean-env/bin/activate
pip install kafka-self-healing
```

#### Permission Issues

```bash
# Fix log directory permissions
sudo chown -R kafka-healing:kafka-healing /var/log/kafka-self-healing
sudo chmod 755 /var/log/kafka-self-healing

# Fix configuration permissions
sudo chown kafka-healing:kafka-healing /etc/kafka-self-healing/config.yaml
sudo chmod 600 /etc/kafka-self-healing/config.yaml
```

### Network Connectivity Issues

```bash
# Test network connectivity
telnet kafka1 9092
telnet zookeeper1 2181

# Check DNS resolution
nslookup kafka1.example.com
dig kafka1.example.com

# Check firewall rules
sudo iptables -L
sudo ufw status
```

### Configuration Issues

```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('/etc/kafka-self-healing/config.yaml'))"

# Check environment variables
env | grep -E "(KAFKA|SMTP|JMX)"

# Test configuration loading
python -c "
from src.kafka_self_healing.config import ConfigurationManager
config = ConfigurationManager('/etc/kafka-self-healing/config.yaml')
print('Configuration loaded successfully')
"
```

### Service Issues

```bash
# Check service status
sudo systemctl status kafka-self-healing

# View service logs
sudo journalctl -u kafka-self-healing -f

# Check service file
sudo systemctl cat kafka-self-healing

# Reload service configuration
sudo systemctl daemon-reload
sudo systemctl restart kafka-self-healing
```

## Deployment Checklist

### Pre-Deployment

- [ ] System requirements verified
- [ ] Dependencies installed
- [ ] Network connectivity tested
- [ ] Permissions configured
- [ ] Configuration validated
- [ ] Security credentials set up
- [ ] Backup procedures established

### Deployment

- [ ] Application installed
- [ ] Configuration deployed
- [ ] Service configured
- [ ] Log rotation set up
- [ ] Monitoring integration configured
- [ ] Security settings applied

### Post-Deployment

- [ ] Service started successfully
- [ ] Health checks passing
- [ ] Logs being generated
- [ ] Metrics being collected
- [ ] Notifications working
- [ ] Documentation updated
- [ ] Team trained

### Production Readiness

- [ ] Load testing completed
- [ ] Failover testing completed
- [ ] Monitoring dashboards configured
- [ ] Alerting rules configured
- [ ] Runbooks updated
- [ ] On-call procedures established

## Support and Maintenance

### Regular Maintenance Tasks

```bash
# Weekly health check
./scripts/weekly_health_check.sh

# Monthly log cleanup
sudo logrotate -f /etc/logrotate.d/kafka-self-healing

# Quarterly dependency updates
pip install -r requirements.txt --upgrade
```

### Backup Procedures

```bash
# Backup configuration
sudo tar -czf /backup/kafka-self-healing-config-$(date +%Y%m%d).tar.gz /etc/kafka-self-healing/

# Backup logs
sudo tar -czf /backup/kafka-self-healing-logs-$(date +%Y%m%d).tar.gz /var/log/kafka-self-healing/
```

### Update Procedures

```bash
# Update application
pip install --upgrade kafka-self-healing

# Restart service
sudo systemctl restart kafka-self-healing

# Verify update
python -c "import src.kafka_self_healing; print(src.kafka_self_healing.__version__)"
```

For additional support, refer to:

- [Operational Runbook](operational_runbook.md)
- [Plugin Development Guide](plugin_development.md)
- [Troubleshooting Guide](troubleshooting.md)