# Plugin Development Guide

This guide explains how to develop custom plugins for the Kafka Self-Healing system. The system supports three types of plugins: Monitoring, Recovery, and Notification plugins.

## Plugin Architecture

The plugin system is designed to be modular and extensible. Each plugin type has a base class that defines the interface, and custom plugins inherit from these base classes.

### Plugin Types

1. **Monitoring Plugins**: Check the health of Kafka brokers and Zookeeper nodes
2. **Recovery Plugins**: Execute recovery actions when failures are detected
3. **Notification Plugins**: Send alerts when recovery fails or succeeds

## Monitoring Plugins

Monitoring plugins are responsible for checking the health of cluster nodes.

### Base Class

```python
from abc import ABC, abstractmethod
from typing import Optional
from src.kafka_self_healing.models import NodeConfig, NodeStatus

class MonitoringPlugin(ABC):
    """Base class for monitoring plugins."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    @abstractmethod
    def check_health(self, node_config: NodeConfig) -> NodeStatus:
        """Check the health of a node."""
        pass
    
    @abstractmethod
    def get_plugin_name(self) -> str:
        """Return the plugin name."""
        pass
    
    @abstractmethod
    def get_supported_node_types(self) -> list:
        """Return list of supported node types."""
        pass
    
    def validate_config(self) -> bool:
        """Validate plugin configuration."""
        return True
    
    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        pass
```

### Example: Custom HTTP Monitoring Plugin

```python
import requests
import time
from src.kafka_self_healing.plugins import MonitoringPlugin
from src.kafka_self_healing.models import NodeConfig, NodeStatus

class HTTPMonitoringPlugin(MonitoringPlugin):
    """Monitor Kafka REST Proxy endpoints via HTTP."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.timeout = self.config.get('timeout', 10)
        self.endpoint_path = self.config.get('endpoint_path', '/v3/clusters')
    
    def check_health(self, node_config: NodeConfig) -> NodeStatus:
        """Check health via HTTP endpoint."""
        start_time = time.time()
        
        try:
            # Construct URL
            url = f"http://{node_config.host}:{node_config.port}{self.endpoint_path}"
            
            # Make HTTP request
            response = requests.get(url, timeout=self.timeout)
            
            # Calculate response time
            response_time_ms = (time.time() - start_time) * 1000
            
            # Determine health based on status code
            is_healthy = response.status_code == 200
            error_message = None if is_healthy else f"HTTP {response.status_code}"
            
            return NodeStatus(
                node_id=node_config.node_id,
                is_healthy=is_healthy,
                last_check_time=time.time(),
                response_time_ms=response_time_ms,
                error_message=error_message,
                monitoring_method="http"
            )
            
        except requests.RequestException as e:
            return NodeStatus(
                node_id=node_config.node_id,
                is_healthy=False,
                last_check_time=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
                monitoring_method="http"
            )
    
    def get_plugin_name(self) -> str:
        return "http_monitoring"
    
    def get_supported_node_types(self) -> list:
        return ["kafka_broker"]
    
    def validate_config(self) -> bool:
        """Validate HTTP monitoring configuration."""
        required_fields = ['timeout', 'endpoint_path']
        return all(field in self.config for field in required_fields)
```

## Recovery Plugins

Recovery plugins execute actions to recover failed nodes.

### Base Class

```python
from abc import ABC, abstractmethod
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class RecoveryPlugin(ABC):
    """Base class for recovery plugins."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    @abstractmethod
    def execute_recovery(self, node_config: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute recovery action for a failed node."""
        pass
    
    @abstractmethod
    def get_plugin_name(self) -> str:
        """Return the plugin name."""
        pass
    
    @abstractmethod
    def get_supported_node_types(self) -> list:
        """Return list of supported node types."""
        pass
    
    @abstractmethod
    def get_supported_failure_types(self) -> list:
        """Return list of supported failure types."""
        pass
    
    def validate_config(self) -> bool:
        """Validate plugin configuration."""
        return True
    
    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        pass
```

### Example: Kubernetes Recovery Plugin

```python
import subprocess
import time
from src.kafka_self_healing.plugins import RecoveryPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class KubernetesRecoveryPlugin(RecoveryPlugin):
    """Recovery plugin for Kubernetes deployments."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.namespace = self.config.get('namespace', 'default')
        self.kubectl_timeout = self.config.get('kubectl_timeout', 60)
    
    def execute_recovery(self, node_config: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute recovery by restarting Kubernetes pod."""
        start_time = time.time()
        
        # Determine pod name from node config
        pod_name = self._get_pod_name(node_config)
        
        # Build kubectl command
        command = [
            'kubectl', 'delete', 'pod', pod_name,
            '--namespace', self.namespace,
            '--timeout', f'{self.kubectl_timeout}s'
        ]
        
        try:
            # Execute kubectl command
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.kubectl_timeout
            )
            
            return RecoveryResult(
                node_id=node_config.node_id,
                action_type="kubernetes_pod_restart",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=time.time(),
                success=result.returncode == 0
            )
            
        except subprocess.TimeoutExpired:
            return RecoveryResult(
                node_id=node_config.node_id,
                action_type="kubernetes_pod_restart",
                command_executed=' '.join(command),
                exit_code=-1,
                stdout="",
                stderr="Command timed out",
                execution_time=time.time(),
                success=False
            )
        except Exception as e:
            return RecoveryResult(
                node_id=node_config.node_id,
                action_type="kubernetes_pod_restart",
                command_executed=' '.join(command),
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=time.time(),
                success=False
            )
    
    def _get_pod_name(self, node_config: NodeConfig) -> str:
        """Generate pod name from node configuration."""
        # This is a simplified example - in practice, you might need
        # to query Kubernetes API to find the actual pod name
        return f"{node_config.node_id}-pod"
    
    def get_plugin_name(self) -> str:
        return "kubernetes_recovery"
    
    def get_supported_node_types(self) -> list:
        return ["kafka_broker", "zookeeper"]
    
    def get_supported_failure_types(self) -> list:
        return ["connection_failure", "health_check_failure", "performance_degradation"]
    
    def validate_config(self) -> bool:
        """Validate Kubernetes configuration."""
        # Check if kubectl is available
        try:
            subprocess.run(['kubectl', 'version', '--client'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
```

## Notification Plugins

Notification plugins send alerts when recovery actions fail or succeed.

### Base Class

```python
from abc import ABC, abstractmethod
from typing import List
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class NotificationPlugin(ABC):
    """Base class for notification plugins."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    @abstractmethod
    def send_failure_notification(self, node_config: NodeConfig, 
                                recovery_history: List[RecoveryResult]) -> bool:
        """Send notification when recovery fails."""
        pass
    
    @abstractmethod
    def send_recovery_notification(self, node_config: NodeConfig) -> bool:
        """Send notification when recovery succeeds."""
        pass
    
    @abstractmethod
    def get_plugin_name(self) -> str:
        """Return the plugin name."""
        pass
    
    def validate_config(self) -> bool:
        """Validate plugin configuration."""
        return True
    
    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        pass
```

### Example: Slack Notification Plugin

```python
import requests
import json
from typing import List
from src.kafka_self_healing.plugins import NotificationPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class SlackNotificationPlugin(NotificationPlugin):
    """Send notifications to Slack via webhook."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.webhook_url = self.config.get('webhook_url')
        self.channel = self.config.get('channel', '#kafka-alerts')
        self.username = self.config.get('username', 'Kafka Self-Healing')
        self.timeout = self.config.get('timeout', 10)
    
    def send_failure_notification(self, node_config: NodeConfig, 
                                recovery_history: List[RecoveryResult]) -> bool:
        """Send failure notification to Slack."""
        
        # Build failure message
        message = self._build_failure_message(node_config, recovery_history)
        
        # Send to Slack
        return self._send_slack_message(message, color="danger")
    
    def send_recovery_notification(self, node_config: NodeConfig) -> bool:
        """Send recovery notification to Slack."""
        
        message = f"✅ *Node Recovered*\n" \
                 f"Node: `{node_config.node_id}`\n" \
                 f"Host: `{node_config.host}:{node_config.port}`\n" \
                 f"Type: `{node_config.node_type}`"
        
        return self._send_slack_message(message, color="good")
    
    def _build_failure_message(self, node_config: NodeConfig, 
                             recovery_history: List[RecoveryResult]) -> str:
        """Build formatted failure message."""
        
        message = f"🚨 *Node Recovery Failed*\n" \
                 f"Node: `{node_config.node_id}`\n" \
                 f"Host: `{node_config.host}:{node_config.port}`\n" \
                 f"Type: `{node_config.node_type}`\n\n"
        
        if recovery_history:
            message += "*Recovery Attempts:*\n"
            for i, result in enumerate(recovery_history[-3:], 1):  # Last 3 attempts
                status = "✅" if result.success else "❌"
                message += f"{status} Attempt {i}: `{result.action_type}` " \
                          f"(Exit code: {result.exit_code})\n"
                
                if result.stderr:
                    message += f"   Error: `{result.stderr[:100]}...`\n"
        
        return message
    
    def _send_slack_message(self, message: str, color: str = "warning") -> bool:
        """Send message to Slack webhook."""
        
        payload = {
            "channel": self.channel,
            "username": self.username,
            "attachments": [{
                "color": color,
                "text": message,
                "mrkdwn_in": ["text"]
            }]
        }
        
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )
            
            return response.status_code == 200
            
        except requests.RequestException:
            return False
    
    def get_plugin_name(self) -> str:
        return "slack_notification"
    
    def validate_config(self) -> bool:
        """Validate Slack configuration."""
        return bool(self.webhook_url)
```

## Plugin Registration

### Plugin Discovery

Plugins are automatically discovered in configured directories. Create a plugin file with the following structure:

```python
# plugins/monitoring/my_custom_plugin.py

from src.kafka_self_healing.plugins import MonitoringPlugin

class MyCustomMonitoringPlugin(MonitoringPlugin):
    # Implementation here
    pass

# Plugin registration
def create_plugin(config: dict = None):
    """Factory function to create plugin instance."""
    return MyCustomMonitoringPlugin(config)

# Plugin metadata
PLUGIN_INFO = {
    "name": "my_custom_monitoring",
    "version": "1.0.0",
    "description": "Custom monitoring plugin",
    "author": "Your Name",
    "supported_node_types": ["kafka_broker"],
    "config_schema": {
        "timeout": {"type": "int", "default": 10},
        "endpoint": {"type": "str", "required": True}
    }
}
```

### Configuration

Add your plugin to the configuration file:

```yaml
plugins:
  discovery:
    enabled: true
    directories:
      - "plugins/monitoring"
      - "plugins/recovery"
      - "plugins/notification"
  
  monitoring_plugins:
    my_custom_monitoring:
      enabled: true
      priority: 1
      config:
        timeout: 15
        endpoint: "/health"
```

## Testing Plugins

### Unit Testing

Create unit tests for your plugins:

```python
import unittest
from unittest.mock import Mock, patch
from plugins.monitoring.my_custom_plugin import MyCustomMonitoringPlugin
from src.kafka_self_healing.models import NodeConfig

class TestMyCustomMonitoringPlugin(unittest.TestCase):
    
    def setUp(self):
        self.config = {"timeout": 10, "endpoint": "/health"}
        self.plugin = MyCustomMonitoringPlugin(self.config)
        
        self.node_config = NodeConfig(
            node_id="test-node",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
    
    def test_check_health_success(self):
        """Test successful health check."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            status = self.plugin.check_health(self.node_config)
            
            self.assertTrue(status.is_healthy)
            self.assertEqual(status.node_id, "test-node")
    
    def test_check_health_failure(self):
        """Test failed health check."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response
            
            status = self.plugin.check_health(self.node_config)
            
            self.assertFalse(status.is_healthy)
            self.assertIn("HTTP 500", status.error_message)

if __name__ == '__main__':
    unittest.main()
```

### Integration Testing

Test your plugin with the actual system:

```python
import unittest
from src.kafka_self_healing.main import SelfHealingSystem

class TestPluginIntegration(unittest.TestCase):
    
    def test_plugin_loading(self):
        """Test that plugin loads correctly."""
        config_file = "test_config_with_plugin.yaml"
        system = SelfHealingSystem(config_file)
        
        # Check that plugin is loaded
        monitoring_service = system.monitoring_service
        plugins = monitoring_service.get_loaded_plugins()
        
        self.assertIn("my_custom_monitoring", plugins)
    
    def test_plugin_execution(self):
        """Test plugin execution in system context."""
        # Implementation depends on your specific plugin
        pass
```

## Best Practices

### Error Handling

- Always handle exceptions gracefully
- Return appropriate error messages
- Log errors for debugging
- Don't let plugin failures crash the main system

### Performance

- Implement timeouts for all external calls
- Use connection pooling where appropriate
- Cache results when possible
- Monitor plugin performance

### Configuration

- Validate configuration on plugin initialization
- Provide sensible defaults
- Document all configuration options
- Support environment variable substitution

### Logging

- Use structured logging
- Include relevant context in log messages
- Respect the system's logging configuration
- Don't log sensitive information

### Security

- Validate all inputs
- Use secure communication protocols
- Handle credentials securely
- Follow principle of least privilege

## Plugin Examples

The system includes several built-in plugins that serve as examples:

- **JMX Monitoring Plugin**: `src/kafka_self_healing/monitoring_plugins.py`
- **Service Restart Plugin**: `src/kafka_self_healing/recovery_plugins.py`
- **Email Notification Plugin**: `src/kafka_self_healing/notification.py`

Study these implementations to understand the plugin patterns and best practices.

## Troubleshooting

### Plugin Not Loading

1. Check plugin directory configuration
2. Verify plugin file structure
3. Check for syntax errors
4. Review system logs for error messages

### Plugin Execution Failures

1. Check plugin configuration
2. Verify external dependencies
3. Test plugin in isolation
4. Review plugin logs

### Performance Issues

1. Monitor plugin execution time
2. Check for resource leaks
3. Optimize external calls
4. Consider caching strategies

For more help, check the system logs and enable debug logging for detailed plugin execution information.

## Advanced Plugin Examples

### Custom Monitoring Plugin with Metrics Collection

```python
import time
import requests
from typing import Dict, Any
from src.kafka_self_healing.plugins import MonitoringPlugin
from src.kafka_self_healing.models import NodeConfig, NodeStatus

class PrometheusMonitoringPlugin(MonitoringPlugin):
    """Monitor Kafka via Prometheus metrics."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.prometheus_url = self.config.get('prometheus_url', 'http://localhost:9090')
        self.timeout = self.config.get('timeout', 10)
        self.metrics_queries = self.config.get('metrics_queries', {
            'kafka_server_brokertopicmetrics_messagesinpersec': 'rate(kafka_server_brokertopicmetrics_messagesinpersec[5m])',
            'kafka_server_brokertopicmetrics_bytesinpersec': 'rate(kafka_server_brokertopicmetrics_bytesinpersec[5m])'
        })
    
    def check_health(self, node_config: NodeConfig) -> NodeStatus:
        """Check health via Prometheus metrics."""
        start_time = time.time()
        
        try:
            # Query Prometheus for node metrics
            metrics = self._query_prometheus_metrics(node_config)
            
            # Analyze metrics to determine health
            is_healthy = self._analyze_metrics(metrics)
            
            response_time_ms = (time.time() - start_time) * 1000
            
            return NodeStatus(
                node_id=node_config.node_id,
                is_healthy=is_healthy,
                last_check_time=time.time(),
                response_time_ms=response_time_ms,
                error_message=None if is_healthy else "Metrics indicate unhealthy state",
                monitoring_method="prometheus",
                additional_data=metrics
            )
            
        except Exception as e:
            return NodeStatus(
                node_id=node_config.node_id,
                is_healthy=False,
                last_check_time=time.time(),
                response_time_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
                monitoring_method="prometheus"
            )
    
    def _query_prometheus_metrics(self, node_config: NodeConfig) -> Dict[str, Any]:
        """Query Prometheus for specific metrics."""
        metrics = {}
        
        for metric_name, query in self.metrics_queries.items():
            # Add node-specific filters to query
            node_query = f'{query}{{instance="{node_config.host}:{node_config.port}"}}'
            
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={'query': node_query},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'success' and data['data']['result']:
                    metrics[metric_name] = float(data['data']['result'][0]['value'][1])
                else:
                    metrics[metric_name] = 0.0
            else:
                raise Exception(f"Prometheus query failed: {response.status_code}")
        
        return metrics
    
    def _analyze_metrics(self, metrics: Dict[str, Any]) -> bool:
        """Analyze metrics to determine node health."""
        # Example health checks based on metrics
        message_rate = metrics.get('kafka_server_brokertopicmetrics_messagesinpersec', 0)
        bytes_rate = metrics.get('kafka_server_brokertopicmetrics_bytesinpersec', 0)
        
        # Consider node healthy if it's processing messages or if it's a new node
        return message_rate > 0 or bytes_rate > 0
    
    def get_plugin_name(self) -> str:
        return "prometheus_monitoring"
    
    def get_supported_node_types(self) -> list:
        return ["kafka_broker"]
```

### Advanced Recovery Plugin with Rollback Capability

```python
import subprocess
import time
import json
from typing import List, Dict, Any
from src.kafka_self_healing.plugins import RecoveryPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class AdvancedRecoveryPlugin(RecoveryPlugin):
    """Advanced recovery plugin with rollback and validation."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.backup_enabled = self.config.get('backup_enabled', True)
        self.validation_enabled = self.config.get('validation_enabled', True)
        self.rollback_enabled = self.config.get('rollback_enabled', True)
        self.backup_dir = self.config.get('backup_dir', '/opt/kafka-backups')
    
    def execute_recovery(self, node_config: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute recovery with backup and validation."""
        start_time = time.time()
        recovery_steps = []
        
        try:
            # Step 1: Create backup if enabled
            if self.backup_enabled:
                backup_result = self._create_backup(node_config)
                recovery_steps.append(backup_result)
                if not backup_result['success']:
                    return self._create_failure_result(node_config, recovery_steps, "Backup failed")
            
            # Step 2: Execute recovery action
            recovery_result = self._execute_recovery_action(node_config, failure_type)
            recovery_steps.append(recovery_result)
            
            if not recovery_result['success']:
                # Step 3: Rollback if recovery failed and rollback is enabled
                if self.rollback_enabled and self.backup_enabled:
                    rollback_result = self._rollback_changes(node_config)
                    recovery_steps.append(rollback_result)
                
                return self._create_failure_result(node_config, recovery_steps, "Recovery action failed")
            
            # Step 4: Validate recovery if enabled
            if self.validation_enabled:
                validation_result = self._validate_recovery(node_config)
                recovery_steps.append(validation_result)
                
                if not validation_result['success']:
                    # Rollback if validation failed
                    if self.rollback_enabled and self.backup_enabled:
                        rollback_result = self._rollback_changes(node_config)
                        recovery_steps.append(rollback_result)
                    
                    return self._create_failure_result(node_config, recovery_steps, "Recovery validation failed")
            
            # Success
            return RecoveryResult(
                node_id=node_config.node_id,
                action_type="advanced_recovery",
                command_executed=json.dumps(recovery_steps),
                exit_code=0,
                stdout=json.dumps(recovery_steps, indent=2),
                stderr="",
                execution_time=time.time(),
                success=True,
                additional_data={'steps': recovery_steps}
            )
            
        except Exception as e:
            return RecoveryResult(
                node_id=node_config.node_id,
                action_type="advanced_recovery",
                command_executed=json.dumps(recovery_steps),
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=time.time(),
                success=False
            )
    
    def _create_backup(self, node_config: NodeConfig) -> Dict[str, Any]:
        """Create backup of node configuration and data."""
        try:
            backup_timestamp = int(time.time())
            backup_path = f"{self.backup_dir}/{node_config.node_id}_{backup_timestamp}"
            
            # Create backup directory
            subprocess.run(['mkdir', '-p', backup_path], check=True)
            
            # Backup configuration files
            if node_config.node_type == "kafka_broker":
                config_files = ['/opt/kafka/config/server.properties']
            else:  # zookeeper
                config_files = ['/opt/zookeeper/conf/zoo.cfg']
            
            for config_file in config_files:
                subprocess.run(['cp', config_file, backup_path], check=True)
            
            return {
                'step': 'backup',
                'success': True,
                'backup_path': backup_path,
                'timestamp': backup_timestamp
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'step': 'backup',
                'success': False,
                'error': str(e)
            }
    
    def _execute_recovery_action(self, node_config: NodeConfig, failure_type: str) -> Dict[str, Any]:
        """Execute the actual recovery action."""
        try:
            if node_config.node_type == "kafka_broker":
                service_name = "kafka"
            else:
                service_name = "zookeeper"
            
            # Stop service
            subprocess.run(['systemctl', 'stop', service_name], check=True, timeout=60)
            
            # Wait a moment
            time.sleep(5)
            
            # Start service
            subprocess.run(['systemctl', 'start', service_name], check=True, timeout=60)
            
            return {
                'step': 'recovery',
                'success': True,
                'action': f'restart_{service_name}'
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'step': 'recovery',
                'success': False,
                'error': str(e)
            }
    
    def _validate_recovery(self, node_config: NodeConfig) -> Dict[str, Any]:
        """Validate that recovery was successful."""
        try:
            # Wait for service to fully start
            time.sleep(10)
            
            if node_config.node_type == "kafka_broker":
                # Test Kafka connectivity
                result = subprocess.run([
                    'kafka-broker-api-versions.sh',
                    '--bootstrap-server', f"{node_config.host}:{node_config.port}"
                ], capture_output=True, timeout=30)
            else:
                # Test Zookeeper connectivity
                result = subprocess.run([
                    'bash', '-c', f'echo "ruok" | nc {node_config.host} {node_config.port}'
                ], capture_output=True, timeout=10)
            
            success = result.returncode == 0
            
            return {
                'step': 'validation',
                'success': success,
                'output': result.stdout.decode() if success else result.stderr.decode()
            }
            
        except subprocess.TimeoutExpired:
            return {
                'step': 'validation',
                'success': False,
                'error': 'Validation timeout'
            }
    
    def _rollback_changes(self, node_config: NodeConfig) -> Dict[str, Any]:
        """Rollback changes using backup."""
        try:
            # Find most recent backup
            import glob
            backup_pattern = f"{self.backup_dir}/{node_config.node_id}_*"
            backups = sorted(glob.glob(backup_pattern), reverse=True)
            
            if not backups:
                return {
                    'step': 'rollback',
                    'success': False,
                    'error': 'No backup found'
                }
            
            latest_backup = backups[0]
            
            # Restore configuration files
            if node_config.node_type == "kafka_broker":
                config_files = ['/opt/kafka/config/server.properties']
            else:
                config_files = ['/opt/zookeeper/conf/zoo.cfg']
            
            for config_file in config_files:
                backup_file = f"{latest_backup}/{config_file.split('/')[-1]}"
                subprocess.run(['cp', backup_file, config_file], check=True)
            
            return {
                'step': 'rollback',
                'success': True,
                'backup_used': latest_backup
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'step': 'rollback',
                'success': False,
                'error': str(e)
            }
    
    def _create_failure_result(self, node_config: NodeConfig, steps: List[Dict], error_msg: str) -> RecoveryResult:
        """Create a failure result with step details."""
        return RecoveryResult(
            node_id=node_config.node_id,
            action_type="advanced_recovery",
            command_executed=json.dumps(steps),
            exit_code=1,
            stdout="",
            stderr=error_msg,
            execution_time=time.time(),
            success=False,
            additional_data={'steps': steps}
        )
    
    def get_plugin_name(self) -> str:
        return "advanced_recovery"
    
    def get_supported_node_types(self) -> list:
        return ["kafka_broker", "zookeeper"]
    
    def get_supported_failure_types(self) -> list:
        return ["connection_failure", "health_check_failure", "performance_degradation"]
```

### Multi-Channel Notification Plugin

```python
import requests
import json
from typing import List, Dict, Any
from src.kafka_self_healing.plugins import NotificationPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class MultiChannelNotificationPlugin(NotificationPlugin):
    """Send notifications via multiple channels (Slack, Teams, PagerDuty)."""
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self.channels = self.config.get('channels', {})
        self.severity_routing = self.config.get('severity_routing', {})
        self.timeout = self.config.get('timeout', 10)
    
    def send_failure_notification(self, node_config: NodeConfig, 
                                recovery_history: List[RecoveryResult]) -> bool:
        """Send failure notification via multiple channels."""
        
        # Determine severity based on recovery history
        severity = self._determine_severity(recovery_history)
        
        # Get channels for this severity
        target_channels = self._get_channels_for_severity(severity)
        
        # Build notification content
        notification_data = self._build_failure_notification(node_config, recovery_history, severity)
        
        # Send to each channel
        results = []
        for channel in target_channels:
            result = self._send_to_channel(channel, notification_data)
            results.append(result)
        
        # Return True if at least one channel succeeded
        return any(results)
    
    def send_recovery_notification(self, node_config: NodeConfig) -> bool:
        """Send recovery notification via configured channels."""
        
        notification_data = self._build_recovery_notification(node_config)
        
        # Send to info channels only
        target_channels = self._get_channels_for_severity('info')
        
        results = []
        for channel in target_channels:
            result = self._send_to_channel(channel, notification_data)
            results.append(result)
        
        return any(results)
    
    def _determine_severity(self, recovery_history: List[RecoveryResult]) -> str:
        """Determine notification severity based on recovery history."""
        if not recovery_history:
            return 'info'
        
        failed_attempts = len([r for r in recovery_history if not r.success])
        total_attempts = len(recovery_history)
        
        if failed_attempts >= 3:
            return 'critical'
        elif failed_attempts >= 2:
            return 'warning'
        else:
            return 'info'
    
    def _get_channels_for_severity(self, severity: str) -> List[str]:
        """Get notification channels for given severity."""
        routing = self.severity_routing.get(severity, ['slack'])
        return [ch for ch in routing if ch in self.channels]
    
    def _build_failure_notification(self, node_config: NodeConfig, 
                                  recovery_history: List[RecoveryResult], 
                                  severity: str) -> Dict[str, Any]:
        """Build failure notification content."""
        
        # Determine emoji and color based on severity
        severity_config = {
            'info': {'emoji': 'ℹ️', 'color': 'good'},
            'warning': {'emoji': '⚠️', 'color': 'warning'},
            'critical': {'emoji': '🚨', 'color': 'danger'}
        }
        
        config = severity_config.get(severity, severity_config['warning'])
        
        return {
            'severity': severity,
            'emoji': config['emoji'],
            'color': config['color'],
            'title': f"Kafka Node Recovery Failed",
            'node_id': node_config.node_id,
            'host': f"{node_config.host}:{node_config.port}",
            'node_type': node_config.node_type,
            'failed_attempts': len([r for r in recovery_history if not r.success]),
            'total_attempts': len(recovery_history),
            'last_error': recovery_history[-1].stderr if recovery_history else "Unknown",
            'recovery_history': recovery_history[-3:]  # Last 3 attempts
        }
    
    def _build_recovery_notification(self, node_config: NodeConfig) -> Dict[str, Any]:
        """Build recovery success notification content."""
        return {
            'severity': 'info',
            'emoji': '✅',
            'color': 'good',
            'title': f"Kafka Node Recovered",
            'node_id': node_config.node_id,
            'host': f"{node_config.host}:{node_config.port}",
            'node_type': node_config.node_type
        }
    
    def _send_to_channel(self, channel: str, notification_data: Dict[str, Any]) -> bool:
        """Send notification to specific channel."""
        
        if channel == 'slack':
            return self._send_slack_notification(notification_data)
        elif channel == 'teams':
            return self._send_teams_notification(notification_data)
        elif channel == 'pagerduty':
            return self._send_pagerduty_notification(notification_data)
        elif channel == 'webhook':
            return self._send_webhook_notification(notification_data)
        else:
            return False
    
    def _send_slack_notification(self, data: Dict[str, Any]) -> bool:
        """Send notification to Slack."""
        try:
            slack_config = self.channels.get('slack', {})
            webhook_url = slack_config.get('webhook_url')
            
            if not webhook_url:
                return False
            
            # Build Slack message
            if data['severity'] == 'info' and 'Recovered' in data['title']:
                # Recovery message
                message = f"{data['emoji']} *{data['title']}*\n" \
                         f"Node: `{data['node_id']}`\n" \
                         f"Host: `{data['host']}`\n" \
                         f"Type: `{data['node_type']}`"
            else:
                # Failure message
                message = f"{data['emoji']} *{data['title']}*\n" \
                         f"Node: `{data['node_id']}`\n" \
                         f"Host: `{data['host']}`\n" \
                         f"Type: `{data['node_type']}`\n" \
                         f"Failed Attempts: {data['failed_attempts']}/{data['total_attempts']}\n" \
                         f"Last Error: `{data['last_error'][:100]}...`"
            
            payload = {
                "channel": slack_config.get('channel', '#kafka-alerts'),
                "username": slack_config.get('username', 'Kafka Self-Healing'),
                "attachments": [{
                    "color": data['color'],
                    "text": message,
                    "mrkdwn_in": ["text"]
                }]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=self.timeout)
            return response.status_code == 200
            
        except Exception:
            return False
    
    def _send_teams_notification(self, data: Dict[str, Any]) -> bool:
        """Send notification to Microsoft Teams."""
        try:
            teams_config = self.channels.get('teams', {})
            webhook_url = teams_config.get('webhook_url')
            
            if not webhook_url:
                return False
            
            # Build Teams message
            payload = {
                "@type": "MessageCard",
                "@context": "http://schema.org/extensions",
                "themeColor": "FF0000" if data['severity'] == 'critical' else "FFA500" if data['severity'] == 'warning' else "00FF00",
                "summary": data['title'],
                "sections": [{
                    "activityTitle": f"{data['emoji']} {data['title']}",
                    "facts": [
                        {"name": "Node ID", "value": data['node_id']},
                        {"name": "Host", "value": data['host']},
                        {"name": "Type", "value": data['node_type']}
                    ]
                }]
            }
            
            if 'failed_attempts' in data:
                payload["sections"][0]["facts"].extend([
                    {"name": "Failed Attempts", "value": f"{data['failed_attempts']}/{data['total_attempts']}"},
                    {"name": "Last Error", "value": data['last_error'][:100]}
                ])
            
            response = requests.post(webhook_url, json=payload, timeout=self.timeout)
            return response.status_code == 200
            
        except Exception:
            return False
    
    def _send_pagerduty_notification(self, data: Dict[str, Any]) -> bool:
        """Send notification to PagerDuty."""
        try:
            pagerduty_config = self.channels.get('pagerduty', {})
            routing_key = pagerduty_config.get('routing_key')
            
            if not routing_key:
                return False
            
            # Only send critical alerts to PagerDuty
            if data['severity'] != 'critical':
                return True
            
            payload = {
                "routing_key": routing_key,
                "event_action": "trigger",
                "dedup_key": f"kafka-{data['node_id']}",
                "payload": {
                    "summary": f"Kafka Node {data['node_id']} Recovery Failed",
                    "source": data['host'],
                    "severity": "critical",
                    "component": "kafka-self-healing",
                    "group": "kafka-cluster",
                    "class": "infrastructure"
                }
            }
            
            response = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=self.timeout
            )
            return response.status_code == 202
            
        except Exception:
            return False
    
    def _send_webhook_notification(self, data: Dict[str, Any]) -> bool:
        """Send notification to generic webhook."""
        try:
            webhook_config = self.channels.get('webhook', {})
            webhook_url = webhook_config.get('url')
            
            if not webhook_url:
                return False
            
            # Send raw notification data
            response = requests.post(webhook_url, json=data, timeout=self.timeout)
            return response.status_code in [200, 201, 202]
            
        except Exception:
            return False
    
    def get_plugin_name(self) -> str:
        return "multi_channel_notification"
    
    def validate_config(self) -> bool:
        """Validate multi-channel configuration."""
        if not self.channels:
            return False
        
        # Validate each configured channel
        for channel_name, channel_config in self.channels.items():
            if channel_name == 'slack':
                if not channel_config.get('webhook_url'):
                    return False
            elif channel_name == 'teams':
                if not channel_config.get('webhook_url'):
                    return False
            elif channel_name == 'pagerduty':
                if not channel_config.get('routing_key'):
                    return False
            elif channel_name == 'webhook':
                if not channel_config.get('url'):
                    return False
        
        return True
```

## Plugin Configuration Examples

### Complete Plugin Configuration

```yaml
plugins:
  discovery:
    enabled: true
    directories:
      - "/opt/kafka-healing/plugins/monitoring"
      - "/opt/kafka-healing/plugins/recovery"
      - "/opt/kafka-healing/plugins/notification"
    auto_load: true
    plugin_timeout: 30
  
  monitoring_plugins:
    prometheus_monitoring:
      enabled: true
      priority: 1
      config:
        prometheus_url: "http://prometheus:9090"
        timeout: 15
        metrics_queries:
          kafka_messages_in: 'rate(kafka_server_brokertopicmetrics_messagesinpersec[5m])'
          kafka_bytes_in: 'rate(kafka_server_brokertopicmetrics_bytesinpersec[5m])'
          kafka_active_controllers: 'kafka_controller_kafkacontroller_activecontrollercount'
    
    jmx_monitoring:
      enabled: true
      priority: 2
      config:
        connection_timeout: 10
        read_timeout: 15
    
    socket_monitoring:
      enabled: true
      priority: 3
      config:
        connection_timeout: 5
  
  recovery_plugins:
    advanced_recovery:
      enabled: true
      priority: 1
      config:
        backup_enabled: true
        validation_enabled: true
        rollback_enabled: true
        backup_dir: "/opt/kafka-backups"
    
    kubernetes_recovery:
      enabled: false  # Enable for K8s deployments
      priority: 2
      config:
        namespace: "kafka"
        kubectl_timeout: 60
    
    service_restart:
      enabled: true
      priority: 3
  
  notification_plugins:
    multi_channel_notification:
      enabled: true
      priority: 1
      config:
        timeout: 10
        channels:
          slack:
            webhook_url: "${SLACK_WEBHOOK_URL}"
            channel: "#kafka-alerts"
            username: "Kafka Self-Healing"
          teams:
            webhook_url: "${TEAMS_WEBHOOK_URL}"
          pagerduty:
            routing_key: "${PAGERDUTY_ROUTING_KEY}"
          webhook:
            url: "${CUSTOM_WEBHOOK_URL}"
        severity_routing:
          info: ["slack"]
          warning: ["slack", "teams"]
          critical: ["slack", "teams", "pagerduty"]
    
    email_notification:
      enabled: true
      priority: 2
```

## Plugin Testing Framework

### Unit Test Template

```python
import unittest
from unittest.mock import Mock, patch, MagicMock
from your_plugin_module import YourPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult

class TestYourPlugin(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'timeout': 10,
            'custom_setting': 'test_value'
        }
        self.plugin = YourPlugin(self.config)
        
        self.node_config = NodeConfig(
            node_id="test-node",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
    
    def test_plugin_initialization(self):
        """Test plugin initializes correctly."""
        self.assertEqual(self.plugin.config['timeout'], 10)
        self.assertEqual(self.plugin.get_plugin_name(), "your_plugin")
    
    def test_config_validation_success(self):
        """Test successful configuration validation."""
        self.assertTrue(self.plugin.validate_config())
    
    def test_config_validation_failure(self):
        """Test configuration validation failure."""
        invalid_plugin = YourPlugin({})  # Missing required config
        self.assertFalse(invalid_plugin.validate_config())
    
    @patch('your_plugin_module.external_dependency')
    def test_successful_operation(self, mock_dependency):
        """Test successful plugin operation."""
        # Setup mock
        mock_dependency.return_value = Mock(status_code=200)
        
        # Execute
        result = self.plugin.your_method(self.node_config)
        
        # Verify
        self.assertTrue(result.success)
        mock_dependency.assert_called_once()
    
    @patch('your_plugin_module.external_dependency')
    def test_operation_failure(self, mock_dependency):
        """Test plugin operation failure."""
        # Setup mock to raise exception
        mock_dependency.side_effect = Exception("Connection failed")
        
        # Execute
        result = self.plugin.your_method(self.node_config)
        
        # Verify
        self.assertFalse(result.success)
        self.assertIn("Connection failed", result.error_message)
    
    def test_timeout_handling(self):
        """Test timeout handling."""
        with patch('your_plugin_module.time.sleep') as mock_sleep:
            mock_sleep.side_effect = TimeoutError("Operation timed out")
            
            result = self.plugin.your_method(self.node_config)
            
            self.assertFalse(result.success)
            self.assertIn("timeout", result.error_message.lower())
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self.plugin, 'cleanup'):
            self.plugin.cleanup()

if __name__ == '__main__':
    unittest.main()
```

### Integration Test Template

```python
import unittest
import time
from src.kafka_self_healing.main import SelfHealingSystem
from src.kafka_self_healing.models import NodeConfig

class TestPluginIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        cls.config_file = "test_config_with_plugins.yaml"
        cls.system = SelfHealingSystem(cls.config_file)
    
    def test_plugin_loading(self):
        """Test that plugins load correctly in system."""
        monitoring_service = self.system.monitoring_service
        loaded_plugins = monitoring_service.get_loaded_plugins()
        
        self.assertIn("your_plugin", loaded_plugins)
        
        plugin = loaded_plugins["your_plugin"]
        self.assertEqual(plugin.get_plugin_name(), "your_plugin")
    
    def test_plugin_execution_in_system(self):
        """Test plugin execution within system context."""
        node_config = NodeConfig(
            node_id="test-node",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        # Execute monitoring with plugin
        status = self.system.monitoring_service.check_node_health(node_config)
        
        # Verify plugin was used
        self.assertIsNotNone(status)
        self.assertEqual(status.node_id, "test-node")
    
    def test_plugin_error_handling_in_system(self):
        """Test plugin error handling in system context."""
        # Create node config that will cause plugin to fail
        failing_node_config = NodeConfig(
            node_id="failing-node",
            node_type="kafka_broker",
            host="nonexistent-host",
            port=9092
        )
        
        # System should handle plugin failure gracefully
        status = self.system.monitoring_service.check_node_health(failing_node_config)
        
        self.assertIsNotNone(status)
        self.assertFalse(status.is_healthy)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        if hasattr(cls.system, 'shutdown'):
            cls.system.shutdown()

if __name__ == '__main__':
    unittest.main()
```