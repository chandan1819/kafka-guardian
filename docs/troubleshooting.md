# Kafka Self-Healing System - Troubleshooting Guide

This guide provides comprehensive troubleshooting procedures for common issues with the Kafka Self-Healing system.

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [System Startup Issues](#system-startup-issues)
3. [Monitoring Problems](#monitoring-problems)
4. [Recovery Failures](#recovery-failures)
5. [Notification Issues](#notification-issues)
6. [Performance Problems](#performance-problems)
7. [Configuration Issues](#configuration-issues)
8. [Network and Connectivity](#network-and-connectivity)
9. [Security and Authentication](#security-and-authentication)
10. [Plugin Issues](#plugin-issues)
11. [Log Analysis](#log-analysis)
12. [Emergency Procedures](#emergency-procedures)

## Quick Diagnostics

### System Health Check

Run this quick health check to identify common issues:

```bash
#!/bin/bash
# Quick health check script

echo "=== Kafka Self-Healing System Health Check ==="

# Check if service is running
echo "1. Service Status:"
systemctl is-active kafka-self-healing
systemctl status kafka-self-healing --no-pager -l

# Check configuration
echo "2. Configuration Validation:"
python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml

# Check log files
echo "3. Recent Errors:"
tail -20 /var/log/kafka-self-healing/application.log | grep -i error

# Check disk space
echo "4. Disk Space:"
df -h /var/log/kafka-self-healing/

# Check network connectivity
echo "5. Network Connectivity:"
for host in kafka1 kafka2 zookeeper1; do
    echo "Testing $host..."
    nc -zv $host 9092 2>&1 | head -1
done

# Check memory usage
echo "6. Memory Usage:"
ps aux | grep kafka_self_healing | grep -v grep

echo "=== Health Check Complete ==="
```

### Log File Locations

```bash
# Application logs
/var/log/kafka-self-healing/application.log

# Audit logs
/var/log/kafka-self-healing/audit.log

# Performance logs
/var/log/kafka-self-healing/performance.log

# System logs
journalctl -u kafka-self-healing

# Configuration file
/etc/kafka-self-healing/config.yaml
```

## System Startup Issues

### Issue: Service Fails to Start

**Symptoms:**
- `systemctl start kafka-self-healing` fails
- Service exits immediately after starting
- "Failed to start" messages in logs

**Diagnosis:**
```bash
# Check service status
sudo systemctl status kafka-self-healing

# Check system logs
sudo journalctl -u kafka-self-healing --no-pager

# Check configuration
python -m src.kafka_self_healing.config --validate /etc/kafka-self-healing/config.yaml

# Check file permissions
ls -la /etc/kafka-self-healing/
ls -la /var/log/kafka-self-healing/
```

**Common Causes and Solutions:**

1. **Configuration Errors:**
   ```bash
   # Validate YAML syntax
   python -c "import yaml; yaml.safe_load(open('/etc/kafka-self-healing/config.yaml'))"
   
   # Check for missing required fields
   grep -E "(host|port|username|password)" /etc/kafka-self-healing/config.yaml
   ```

2. **Permission Issues:**
   ```bash
   # Fix file permissions
   sudo chown kafka-healing:kafka-healing /etc/kafka-self-healing/config.yaml
   sudo chmod 600 /etc/kafka-self-healing/config.yaml
   
   # Fix log directory permissions
   sudo chown -R kafka-healing:kafka-healing /var/log/kafka-self-healing/
   sudo chmod 755 /var/log/kafka-self-healing/
   ```

3. **Missing Dependencies:**
   ```bash
   # Check Python dependencies
   pip list | grep -E "(kafka|pyyaml|requests)"
   
   # Reinstall if needed
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   ```bash
   # Check environment variables
   sudo -u kafka-healing env | grep -E "(KAFKA|SMTP|JMX)"
   
   # Set missing variables
   echo "SMTP_PASSWORD=your-password" | sudo tee -a /etc/kafka-self-healing/environment
   ```

### Issue: Python Import Errors

**Symptoms:**
- `ModuleNotFoundError` in logs
- `ImportError` messages
- Service starts but crashes immediately

**Solutions:**
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Check if package is installed
python -c "import src.kafka_self_healing; print('OK')"

# Reinstall package
pip uninstall kafka-self-healing
pip install -e .

# Check virtual environment
which python
pip list | grep kafka-self-healing
```

## Monitoring Problems

### Issue: Nodes Always Show as Unhealthy

**Symptoms:**
- All nodes report as unhealthy
- Constant recovery attempts
- "Connection refused" errors

**Diagnosis:**
```bash
# Test connectivity manually
telnet kafka1 9092
echo "ruok" | nc zookeeper1 2181

# Check JMX connectivity
jconsole kafka1:9999

# Check monitoring logs
grep "Monitoring" /var/log/kafka-self-healing/application.log | tail -20
```

**Solutions:**

1. **Network Connectivity:**
   ```bash
   # Check firewall rules
   sudo iptables -L | grep -E "(9092|2181|9999)"
   sudo ufw status
   
   # Test DNS resolution
   nslookup kafka1
   dig kafka1
   ```

2. **Authentication Issues:**
   ```bash
   # Check JMX credentials
   echo $JMX_USERNAME
   echo $JMX_PASSWORD
   
   # Test JMX connection
   java -jar jmxterm.jar -l kafka1:9999 -u $JMX_USERNAME -p $JMX_PASSWORD
   ```

3. **Timeout Settings:**
   ```yaml
   # Increase timeouts in config.yaml
   monitoring:
     timeout_seconds: 30  # Increase from default
     jmx:
       connection_timeout: 15
       read_timeout: 20
   ```

### Issue: Intermittent Monitoring Failures

**Symptoms:**
- Nodes randomly show as unhealthy
- Inconsistent monitoring results
- Network timeout errors

**Solutions:**

1. **Adjust Monitoring Intervals:**
   ```yaml
   monitoring:
     interval_seconds: 60  # Increase interval
     health_check_retries: 3  # Add retries
   ```

2. **Enable Concurrent Checks:**
   ```yaml
   monitoring:
     concurrent_checks: false  # Disable if causing issues
   ```

3. **Check Network Stability:**
   ```bash
   # Monitor network latency
   ping -c 100 kafka1 | tail -5
   
   # Check for packet loss
   mtr kafka1
   ```

### Issue: JMX Monitoring Fails

**Symptoms:**
- JMX connection errors
- Authentication failures
- SSL handshake errors

**Solutions:**

1. **Check JMX Configuration:**
   ```bash
   # Verify JMX is enabled on Kafka
   ps aux | grep kafka | grep -i jmx
   
   # Check JMX port
   netstat -tlnp | grep 9999
   ```

2. **Test JMX Connection:**
   ```bash
   # Use jconsole
   jconsole kafka1:9999
   
   # Use command line
   echo "get -b kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec" | \
   java -jar jmxterm.jar -l kafka1:9999
   ```

3. **SSL/Authentication Issues:**
   ```yaml
   monitoring:
     jmx:
       authentication: true
       username: ${JMX_USERNAME}
       password: ${JMX_PASSWORD}
       ssl_enabled: true
   ```

## Recovery Failures

### Issue: Recovery Actions Always Fail

**Symptoms:**
- All recovery attempts fail
- Permission denied errors
- Command not found errors

**Diagnosis:**
```bash
# Check recovery logs
grep "Recovery" /var/log/kafka-self-healing/audit.log | tail -10

# Test recovery commands manually
sudo -u kafka-healing systemctl restart kafka
sudo -u kafka-healing /opt/recovery-scripts/restart-kafka.sh
```

**Solutions:**

1. **Permission Issues:**
   ```bash
   # Add user to required groups
   sudo usermod -a -G sudo kafka-healing
   
   # Configure sudoers
   echo "kafka-healing ALL=(ALL) NOPASSWD: /bin/systemctl restart kafka" | \
   sudo tee /etc/sudoers.d/kafka-healing
   ```

2. **Service Names:**
   ```yaml
   recovery:
     restart_service:
       kafka_service_name: "kafka"  # Verify correct service name
       zookeeper_service_name: "zookeeper"
   ```

3. **Script Paths:**
   ```bash
   # Verify script exists and is executable
   ls -la /opt/recovery-scripts/
   chmod +x /opt/recovery-scripts/*.sh
   ```

### Issue: Ansible Recovery Fails

**Symptoms:**
- Ansible playbook execution fails
- Inventory errors
- SSH connection issues

**Solutions:**

1. **Check Ansible Configuration:**
   ```bash
   # Test Ansible connectivity
   ansible all -i /opt/kafka-recovery/inventory/production -m ping
   
   # Check playbook syntax
   ansible-playbook --syntax-check /opt/kafka-recovery/playbooks/restart-kafka.yml
   ```

2. **SSH Key Issues:**
   ```bash
   # Check SSH keys
   sudo -u kafka-healing ssh kafka1
   
   # Add SSH keys if needed
   sudo -u kafka-healing ssh-copy-id kafka1
   ```

3. **Inventory Configuration:**
   ```ini
   # /opt/kafka-recovery/inventory/production
   [kafka_brokers]
   kafka1 ansible_host=kafka1.example.com
   kafka2 ansible_host=kafka2.example.com
   
   [all:vars]
   ansible_user=kafka-healing
   ansible_ssh_private_key_file=/home/kafka-healing/.ssh/id_rsa
   ```

### Issue: Script Recovery Fails

**Symptoms:**
- Script execution timeouts
- Exit code errors
- Script not found errors

**Solutions:**

1. **Script Permissions:**
   ```bash
   # Make scripts executable
   chmod +x /opt/recovery-scripts/*.sh
   
   # Check script ownership
   chown kafka-healing:kafka-healing /opt/recovery-scripts/*.sh
   ```

2. **Script Debugging:**
   ```bash
   # Test script manually
   sudo -u kafka-healing /opt/recovery-scripts/restart-kafka.sh
   
   # Add debugging to scripts
   set -x  # Add to beginning of script
   ```

3. **Timeout Issues:**
   ```yaml
   recovery:
     script:
       timeout: 300  # Increase timeout
   ```

## Notification Issues

### Issue: Email Notifications Not Sent

**Symptoms:**
- No emails received
- SMTP connection errors
- Authentication failures

**Diagnosis:**
```bash
# Check notification logs
grep "Notification" /var/log/kafka-self-healing/application.log | tail -10

# Test SMTP connectivity
telnet smtp.example.com 587

# Check email queue
mailq
```

**Solutions:**

1. **SMTP Configuration:**
   ```yaml
   notifications:
     smtp:
       host: smtp.example.com
       port: 587
       use_tls: true
       username: ${SMTP_USERNAME}
       password: ${SMTP_PASSWORD}
   ```

2. **Test Email Manually:**
   ```python
   import smtplib
   from email.mime.text import MIMEText
   
   msg = MIMEText("Test message")
   msg['Subject'] = "Test"
   msg['From'] = "kafka-alerts@example.com"
   msg['To'] = "admin@example.com"
   
   server = smtplib.SMTP('smtp.example.com', 587)
   server.starttls()
   server.login('username', 'password')
   server.send_message(msg)
   server.quit()
   ```

3. **Firewall Issues:**
   ```bash
   # Check SMTP port access
   telnet smtp.example.com 587
   nc -zv smtp.example.com 587
   ```

### Issue: Too Many Notifications

**Symptoms:**
- Email flooding
- Notification spam
- Rate limiting triggered

**Solutions:**

1. **Configure Rate Limiting:**
   ```yaml
   notifications:
     rate_limiting:
       max_notifications_per_hour: 10
       cooldown_period_minutes: 15
   ```

2. **Adjust Triggers:**
   ```yaml
   notifications:
     triggers:
       on_recovery_success: false  # Disable success notifications
       on_recovery_failure: true
   ```

3. **Check for Monitoring Issues:**
   ```bash
   # Look for flapping nodes
   grep "Node status changed" /var/log/kafka-self-healing/application.log | \
   awk '{print $NF}' | sort | uniq -c | sort -nr
   ```

## Performance Problems

### Issue: High CPU Usage

**Symptoms:**
- System CPU usage > 80%
- Slow monitoring responses
- System becomes unresponsive

**Diagnosis:**
```bash
# Check CPU usage
top -p $(pgrep -f kafka_self_healing)
htop

# Check system load
uptime
cat /proc/loadavg
```

**Solutions:**

1. **Reduce Monitoring Frequency:**
   ```yaml
   monitoring:
     interval_seconds: 60  # Increase from 30
     concurrent_checks: false  # Disable if causing issues
   ```

2. **Limit Concurrent Operations:**
   ```yaml
   system:
     max_concurrent_operations: 5  # Reduce from default
     cpu_limit_percent: 50
   ```

3. **Optimize Plugins:**
   ```bash
   # Disable unnecessary plugins
   # Check plugin performance logs
   grep "slow" /var/log/kafka-self-healing/performance.log
   ```

### Issue: High Memory Usage

**Symptoms:**
- Memory usage constantly increasing
- Out of memory errors
- System swapping

**Solutions:**

1. **Set Memory Limits:**
   ```yaml
   system:
     memory_limit_mb: 512  # Set appropriate limit
   ```

2. **Check for Memory Leaks:**
   ```bash
   # Monitor memory usage over time
   while true; do
     ps aux | grep kafka_self_healing | grep -v grep
     sleep 60
   done
   ```

3. **Reduce Log Retention:**
   ```yaml
   logging:
     max_size_mb: 50  # Reduce log file size
     backup_count: 3  # Reduce backup count
   ```

### Issue: Slow Monitoring Response

**Symptoms:**
- Monitoring takes too long
- Timeout errors
- Delayed failure detection

**Solutions:**

1. **Optimize Timeouts:**
   ```yaml
   monitoring:
     timeout_seconds: 10  # Reduce timeout
     concurrent_checks: true  # Enable parallel checks
   ```

2. **Use Faster Monitoring Methods:**
   ```yaml
   monitoring:
     methods: ["socket"]  # Use only socket checks
   ```

3. **Check Network Latency:**
   ```bash
   # Measure network latency
   ping -c 10 kafka1
   traceroute kafka1
   ```

## Configuration Issues

### Issue: Configuration Not Loading

**Symptoms:**
- Default values used instead of config
- Configuration validation errors
- YAML parsing errors

**Solutions:**

1. **Validate YAML Syntax:**
   ```bash
   # Check YAML syntax
   python -c "import yaml; yaml.safe_load(open('/etc/kafka-self-healing/config.yaml'))"
   
   # Use online YAML validator
   yamllint /etc/kafka-self-healing/config.yaml
   ```

2. **Check File Permissions:**
   ```bash
   # Verify file is readable
   sudo -u kafka-healing cat /etc/kafka-self-healing/config.yaml
   ```

3. **Environment Variable Substitution:**
   ```bash
   # Check environment variables
   env | grep -E "(KAFKA|SMTP|JMX)"
   
   # Test substitution
   python -c "
   import os
   config = open('/etc/kafka-self-healing/config.yaml').read()
   print(os.path.expandvars(config))
   "
   ```

### Issue: Environment Variables Not Working

**Symptoms:**
- Variables not substituted
- Default values used
- Authentication failures

**Solutions:**

1. **Check Variable Format:**
   ```yaml
   # Correct format
   password: ${SMTP_PASSWORD}
   
   # With default value
   password: ${SMTP_PASSWORD:default-password}
   ```

2. **Set Variables Properly:**
   ```bash
   # For systemd service
   sudo systemctl edit kafka-self-healing
   
   # Add:
   [Service]
   Environment="SMTP_PASSWORD=your-password"
   EnvironmentFile=/etc/kafka-self-healing/environment
   ```

3. **Test Variable Expansion:**
   ```bash
   # Test expansion
   echo ${SMTP_PASSWORD}
   sudo -u kafka-healing -E env | grep SMTP_PASSWORD
   ```

## Network and Connectivity

### Issue: Connection Timeouts

**Symptoms:**
- Frequent timeout errors
- Intermittent connectivity
- Slow response times

**Solutions:**

1. **Check Network Path:**
   ```bash
   # Test connectivity
   telnet kafka1 9092
   nc -zv kafka1 9092
   
   # Check routing
   traceroute kafka1
   mtr kafka1
   ```

2. **Adjust Timeouts:**
   ```yaml
   monitoring:
     timeout_seconds: 30
     socket:
       connection_timeout: 10
       read_timeout: 15
   ```

3. **Check Firewall Rules:**
   ```bash
   # Check iptables
   sudo iptables -L -n
   
   # Check ufw
   sudo ufw status verbose
   
   # Check for blocked ports
   sudo netstat -tlnp | grep -E "(9092|2181|9999)"
   ```

### Issue: DNS Resolution Problems

**Symptoms:**
- "Name or service not known" errors
- Inconsistent connectivity
- Long connection delays

**Solutions:**

1. **Test DNS Resolution:**
   ```bash
   # Test DNS
   nslookup kafka1
   dig kafka1
   
   # Check /etc/hosts
   cat /etc/hosts | grep kafka
   ```

2. **Use IP Addresses:**
   ```yaml
   cluster:
     kafka_brokers:
       - host: 192.168.1.10  # Use IP instead of hostname
   ```

3. **Configure DNS:**
   ```bash
   # Add to /etc/hosts
   echo "192.168.1.10 kafka1" | sudo tee -a /etc/hosts
   ```

## Security and Authentication

### Issue: SSL/TLS Connection Failures

**Symptoms:**
- SSL handshake failures
- Certificate validation errors
- "SSL: CERTIFICATE_VERIFY_FAILED" errors

**Solutions:**

1. **Check Certificates:**
   ```bash
   # Test SSL connection
   openssl s_client -connect kafka1:9092 -servername kafka1
   
   # Check certificate validity
   openssl x509 -in /etc/kafka-healing/ssl/ca-cert.pem -text -noout
   ```

2. **Configure SSL Properly:**
   ```yaml
   security:
     ssl:
       enabled: true
       keystore_path: "/etc/kafka-healing/ssl/keystore.jks"
       truststore_path: "/etc/kafka-healing/ssl/truststore.jks"
       protocol: "TLSv1.2"
   ```

3. **Import Certificates:**
   ```bash
   # Import CA certificate
   keytool -import -alias ca-cert -file ca-cert.pem -keystore truststore.jks
   ```

### Issue: SASL Authentication Failures

**Symptoms:**
- Authentication failed errors
- Invalid credentials messages
- SASL mechanism errors

**Solutions:**

1. **Check Credentials:**
   ```bash
   # Verify environment variables
   echo $KAFKA_USERNAME
   echo $KAFKA_PASSWORD
   ```

2. **Test Authentication:**
   ```bash
   # Test with kafka tools
   kafka-console-producer.sh --bootstrap-server kafka1:9092 \
     --producer.config client.properties
   ```

3. **Configure SASL:**
   ```yaml
   security:
     sasl:
       enabled: true
       mechanism: "SCRAM-SHA-256"
       username_env: "KAFKA_USERNAME"
       password_env: "KAFKA_PASSWORD"
   ```

## Plugin Issues

### Issue: Plugins Not Loading

**Symptoms:**
- Plugin not found errors
- Import errors in plugins
- Plugin validation failures

**Solutions:**

1. **Check Plugin Directory:**
   ```bash
   # Verify plugin files exist
   ls -la /opt/kafka-healing/plugins/
   
   # Check plugin structure
   find /opt/kafka-healing/plugins/ -name "*.py"
   ```

2. **Validate Plugin Code:**
   ```python
   # Test plugin import
   import sys
   sys.path.append('/opt/kafka-healing/plugins')
   import my_plugin
   ```

3. **Check Plugin Configuration:**
   ```yaml
   plugins:
     discovery:
       directories:
         - "/opt/kafka-healing/plugins/monitoring"
       auto_load: true
   ```

### Issue: Plugin Execution Failures

**Symptoms:**
- Plugin errors in logs
- Fallback to built-in methods
- Plugin timeout errors

**Solutions:**

1. **Debug Plugin:**
   ```bash
   # Enable debug logging
   # Check plugin logs
   grep "plugin" /var/log/kafka-self-healing/application.log
   ```

2. **Test Plugin Manually:**
   ```python
   # Test plugin directly
   from plugins.monitoring.my_plugin import MyPlugin
   plugin = MyPlugin(config)
   result = plugin.check_health(node_config)
   print(result)
   ```

## Log Analysis

### Useful Log Analysis Commands

```bash
# Find errors in last hour
grep "$(date -d '1 hour ago' '+%Y-%m-%d %H')" /var/log/kafka-self-healing/application.log | grep ERROR

# Count error types
grep ERROR /var/log/kafka-self-healing/application.log | \
awk '{print $NF}' | sort | uniq -c | sort -nr

# Monitor logs in real-time
tail -f /var/log/kafka-self-healing/application.log | grep -E "(ERROR|WARN)"

# Find slow operations
grep "slow" /var/log/kafka-self-healing/performance.log | tail -20

# Analyze recovery success rate
grep "Recovery.*success" /var/log/kafka-self-healing/audit.log | wc -l
grep "Recovery.*failed" /var/log/kafka-self-healing/audit.log | wc -l

# Find notification delivery issues
grep "Notification.*failed" /var/log/kafka-self-healing/application.log

# Check for memory issues
grep -i "memory\|oom" /var/log/kafka-self-healing/application.log

# Find configuration issues
grep -i "config" /var/log/kafka-self-healing/application.log | grep -i error
```

### Log Patterns to Watch

```bash
# Critical patterns
grep -E "(CRITICAL|FATAL|OutOfMemory)" /var/log/kafka-self-healing/application.log

# Connection issues
grep -E "(Connection refused|timeout|unreachable)" /var/log/kafka-self-healing/application.log

# Authentication issues
grep -E "(Authentication failed|Invalid credentials|SSL)" /var/log/kafka-self-healing/application.log

# Performance issues
grep -E "(slow|timeout|high CPU|memory)" /var/log/kafka-self-healing/performance.log
```

## Emergency Procedures

### Complete System Failure

If the self-healing system completely fails:

1. **Immediate Actions:**
   ```bash
   # Check Kafka cluster status
   kafka-topics.sh --bootstrap-server kafka1:9092 --list
   
   # Check Zookeeper status
   echo "ruok" | nc zookeeper1 2181
   
   # Restart self-healing system
   sudo systemctl restart kafka-self-healing
   ```

2. **Manual Monitoring:**
   ```bash
   # Create temporary monitoring script
   cat > /tmp/manual_monitor.sh << 'EOF'
   #!/bin/bash
   while true; do
     echo "$(date): Checking cluster..."
     kafka-broker-api-versions.sh --bootstrap-server kafka1:9092 >/dev/null 2>&1
     if [ $? -eq 0 ]; then
       echo "Kafka OK"
     else
       echo "KAFKA FAILED - Manual intervention required"
       # Send alert
       echo "Kafka cluster failure detected" | mail -s "URGENT: Kafka Down" admin@example.com
     fi
     sleep 30
   done
   EOF
   
   chmod +x /tmp/manual_monitor.sh
   nohup /tmp/manual_monitor.sh &
   ```

### Kafka Cluster Emergency

If the entire Kafka cluster fails:

1. **Assessment:**
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

2. **Recovery Steps:**
   ```bash
   # Stop self-healing to prevent interference
   sudo systemctl stop kafka-self-healing
   
   # Restart Zookeeper ensemble (one at a time)
   sudo systemctl restart zookeeper
   
   # Wait for Zookeeper to stabilize
   sleep 30
   
   # Restart Kafka brokers (one at a time)
   sudo systemctl restart kafka
   
   # Verify cluster health
   kafka-topics.sh --bootstrap-server kafka1:9092 --list
   
   # Restart self-healing system
   sudo systemctl start kafka-self-healing
   ```

### Contact Information

For escalation and support:

- **Primary On-Call**: oncall@company.com
- **Kafka Team**: kafka-team@company.com
- **Platform Team**: platform@company.com
- **Emergency Hotline**: +1-555-KAFKA-911

### Additional Resources

- [Setup and Deployment Guide](setup_and_deployment.md)
- [Operational Runbook](operational_runbook.md)
- [Plugin Development Guide](plugin_development.md)
- [Configuration Examples](../examples/)