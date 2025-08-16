"""
Unit tests for recovery plugins.
"""

import pytest
import subprocess
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.recovery_plugins import ServiceRestartPlugin, ScriptRecoveryPlugin, AnsibleRecoveryPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult
from src.kafka_self_healing.exceptions import RecoveryError, ValidationError


class TestServiceRestartPlugin:
    """Test cases for ServiceRestartPlugin."""
    
    def test_plugin_initialization_default_config(self):
        """Test plugin initialization with default configuration."""
        plugin = ServiceRestartPlugin()
        
        assert plugin.name == "ServiceRestartPlugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Restart services using systemctl"
        assert plugin.service_mappings == {
            'kafka_broker': 'kafka',
            'zookeeper': 'zookeeper'
        }
        assert plugin.use_sudo is True
        assert plugin.timeout_seconds == 60
        assert plugin.systemctl_path == '/usr/bin/systemctl'
    
    def test_plugin_initialization_custom_config(self):
        """Test plugin initialization with custom configuration."""
        config = {
            'service_mappings': {
                'kafka_broker': 'confluent-kafka',
                'zookeeper': 'confluent-zookeeper'
            },
            'use_sudo': False,
            'timeout_seconds': 120,
            'systemctl_path': '/bin/systemctl'
        }
        
        plugin = ServiceRestartPlugin(config)
        
        assert plugin.service_mappings == config['service_mappings']
        assert plugin.use_sudo is False
        assert plugin.timeout_seconds == 120
        assert plugin.systemctl_path == '/bin/systemctl'
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        plugin = ServiceRestartPlugin()
        
        assert plugin.validate_config() is True
    
    def test_validate_config_invalid_service_mappings(self):
        """Test configuration validation with invalid service mappings."""
        config = {'service_mappings': 'not_a_dict'}
        plugin = ServiceRestartPlugin(config)
        
        with pytest.raises(ValidationError, match="service_mappings must be a dictionary"):
            plugin.validate_config()
    
    def test_validate_config_invalid_use_sudo(self):
        """Test configuration validation with invalid use_sudo."""
        config = {'use_sudo': 'not_a_bool'}
        plugin = ServiceRestartPlugin(config)
        
        with pytest.raises(ValidationError, match="use_sudo must be a boolean"):
            plugin.validate_config()
    
    def test_validate_config_invalid_timeout(self):
        """Test configuration validation with invalid timeout."""
        config = {'timeout_seconds': -1}
        plugin = ServiceRestartPlugin(config)
        
        with pytest.raises(ValidationError, match="timeout_seconds must be a positive integer"):
            plugin.validate_config()
    
    def test_validate_config_invalid_systemctl_path(self):
        """Test configuration validation with invalid systemctl path."""
        config = {'systemctl_path': ''}
        plugin = ServiceRestartPlugin(config)
        
        with pytest.raises(ValidationError, match="systemctl_path must be a non-empty string"):
            plugin.validate_config()
    
    @patch('subprocess.run')
    def test_initialize_success(self, mock_run):
        """Test successful plugin initialization."""
        mock_run.return_value = Mock(returncode=0)
        
        plugin = ServiceRestartPlugin()
        
        assert plugin.initialize() is True
        mock_run.assert_called_once_with(
            ['/usr/bin/systemctl', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
    
    @patch('subprocess.run')
    def test_initialize_failure(self, mock_run):
        """Test failed plugin initialization."""
        mock_run.return_value = Mock(returncode=1)
        
        plugin = ServiceRestartPlugin()
        
        assert plugin.initialize() is False
    
    @patch('subprocess.run')
    def test_initialize_subprocess_error(self, mock_run):
        """Test plugin initialization with subprocess error."""
        mock_run.side_effect = subprocess.SubprocessError("Command failed")
        
        plugin = ServiceRestartPlugin()
        
        assert plugin.initialize() is False
    
    def test_supports_recovery_type(self):
        """Test recovery type support checking."""
        plugin = ServiceRestartPlugin()
        
        # Supported types
        assert plugin.supports_recovery_type("service_restart") is True
        assert plugin.supports_recovery_type("service_down") is True
        assert plugin.supports_recovery_type("process_failure") is True
        assert plugin.supports_recovery_type("connection_failure") is True
        assert plugin.supports_recovery_type("health_check_failure") is True
        
        # Unsupported types
        assert plugin.supports_recovery_type("unknown_failure") is False
        assert plugin.supports_recovery_type("network_failure") is False
    
    def test_get_service_name(self):
        """Test getting service name for node types."""
        plugin = ServiceRestartPlugin()
        
        assert plugin._get_service_name("kafka_broker") == "kafka"
        assert plugin._get_service_name("zookeeper") == "zookeeper"
        assert plugin._get_service_name("unknown") is None
    
    def test_build_restart_command_with_sudo(self):
        """Test building restart command with sudo."""
        plugin = ServiceRestartPlugin({'use_sudo': True})
        
        command = plugin._build_restart_command("kafka")
        
        assert command == ['sudo', '/usr/bin/systemctl', 'restart', 'kafka']
    
    def test_build_restart_command_without_sudo(self):
        """Test building restart command without sudo."""
        plugin = ServiceRestartPlugin({'use_sudo': False})
        
        command = plugin._build_restart_command("kafka")
        
        assert command == ['/usr/bin/systemctl', 'restart', 'kafka']
    
    @patch('subprocess.run')
    def test_execute_recovery_success(self, mock_run):
        """Test successful recovery execution."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Service restarted successfully",
            stderr=""
        )
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.execute_recovery(node, "service_down")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_restart"
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "Service restarted successfully"
        assert result.stderr == ""
        assert "sudo /usr/bin/systemctl restart kafka" in result.command_executed
        
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ['sudo', '/usr/bin/systemctl', 'restart', 'kafka']
    
    @patch('subprocess.run')
    def test_execute_recovery_failure(self, mock_run):
        """Test failed recovery execution."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Service restart failed"
        )
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.execute_recovery(node, "service_down")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_restart"
        assert result.success is False
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr == "Service restart failed"
    
    @patch('subprocess.run')
    def test_execute_recovery_timeout(self, mock_run):
        """Test recovery execution timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(['systemctl'], 60)
        
        plugin = ServiceRestartPlugin({'timeout_seconds': 30})
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.execute_recovery(node, "service_down")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_restart"
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out after 30 seconds" in result.stderr
    
    @patch('subprocess.run')
    def test_execute_recovery_subprocess_error(self, mock_run):
        """Test recovery execution with subprocess error."""
        mock_run.side_effect = subprocess.SubprocessError("Command execution failed")
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.execute_recovery(node, "service_down")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_restart"
        assert result.success is False
        assert result.exit_code == -1
        assert "subprocess error" in result.stderr
    
    def test_execute_recovery_unknown_node_type(self):
        """Test recovery execution with unknown node type."""
        plugin = ServiceRestartPlugin({'service_mappings': {}})  # Empty mappings
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        with pytest.raises(RecoveryError, match="No service mapping found for node type: kafka_broker"):
            plugin.execute_recovery(node, "service_down")
    
    @patch('subprocess.run')
    def test_get_service_status_success(self, mock_run):
        """Test getting service status successfully."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="● kafka.service - Apache Kafka\n   Active: active (running)",
            stderr=""
        )
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.get_service_status(node)
        
        assert result is not None
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_status"
        assert result.success is True
        assert result.exit_code == 0
        assert "Active: active (running)" in result.stdout
    
    @patch('subprocess.run')
    def test_get_service_status_failure(self, mock_run):
        """Test getting service status with failure."""
        mock_run.side_effect = subprocess.SubprocessError("Command failed")
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.get_service_status(node)
        
        assert result is None
    
    def test_get_service_status_unknown_node_type(self):
        """Test getting service status for unknown node type."""
        plugin = ServiceRestartPlugin({'service_mappings': {}})  # Empty mappings
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.get_service_status(node)
        
        assert result is None
    
    @patch('subprocess.run')
    def test_stop_service_success(self, mock_run):
        """Test stopping service successfully."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Service stopped successfully",
            stderr=""
        )
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.stop_service(node)
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_stop"
        assert result.success is True
        assert result.exit_code == 0
        assert "sudo /usr/bin/systemctl stop kafka" in result.command_executed
    
    @patch('subprocess.run')
    def test_stop_service_failure(self, mock_run):
        """Test stopping service with failure."""
        mock_run.side_effect = subprocess.SubprocessError("Stop failed")
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.stop_service(node)
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_stop"
        assert result.success is False
        assert result.exit_code == -1
        assert "Service stop error" in result.stderr
    
    def test_stop_service_unknown_node_type(self):
        """Test stopping service for unknown node type."""
        plugin = ServiceRestartPlugin({'service_mappings': {}})  # Empty mappings
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        with pytest.raises(RecoveryError, match="No service mapping found for node type: kafka_broker"):
            plugin.stop_service(node)
    
    @patch('subprocess.run')
    def test_start_service_success(self, mock_run):
        """Test starting service successfully."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Service started successfully",
            stderr=""
        )
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.start_service(node)
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_start"
        assert result.success is True
        assert result.exit_code == 0
        assert "sudo /usr/bin/systemctl start kafka" in result.command_executed
    
    @patch('subprocess.run')
    def test_start_service_failure(self, mock_run):
        """Test starting service with failure."""
        mock_run.side_effect = subprocess.SubprocessError("Start failed")
        
        plugin = ServiceRestartPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.start_service(node)
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "service_start"
        assert result.success is False
        assert result.exit_code == -1
        assert "Service start error" in result.stderr
    
    def test_start_service_unknown_node_type(self):
        """Test starting service for unknown node type."""
        plugin = ServiceRestartPlugin({'service_mappings': {}})  # Empty mappings
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        with pytest.raises(RecoveryError, match="No service mapping found for node type: kafka_broker"):
            plugin.start_service(node)
    
    def test_cleanup(self):
        """Test plugin cleanup."""
        plugin = ServiceRestartPlugin()
        
        # Should not raise any exceptions
        plugin.cleanup()


class TestScriptRecoveryPlugin:
    """Test cases for ScriptRecoveryPlugin."""
    
    def test_plugin_initialization_default_config(self):
        """Test plugin initialization with default configuration."""
        plugin = ScriptRecoveryPlugin()
        
        assert plugin.name == "ScriptRecoveryPlugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Execute shell scripts and commands for recovery"
        assert plugin.script_directory == '/opt/kafka-recovery/scripts'
        assert plugin.scripts == {}
        assert plugin.default_shell == '/bin/bash'
        assert plugin.timeout_seconds == 300
        assert plugin.use_sudo is False
        assert plugin.environment_variables == {}
        assert plugin.working_directory is None
    
    def test_plugin_initialization_custom_config(self):
        """Test plugin initialization with custom configuration."""
        config = {
            'script_directory': '/custom/scripts',
            'scripts': {
                'restart': 'restart_kafka.sh',
                'cleanup': {'path': 'cleanup.sh', 'args': ['--force']}
            },
            'default_shell': '/bin/zsh',
            'timeout_seconds': 600,
            'use_sudo': True,
            'environment_variables': {'KAFKA_HOME': '/opt/kafka'},
            'working_directory': '/tmp'
        }
        
        plugin = ScriptRecoveryPlugin(config)
        
        assert plugin.script_directory == '/custom/scripts'
        assert plugin.scripts == config['scripts']
        assert plugin.default_shell == '/bin/zsh'
        assert plugin.timeout_seconds == 600
        assert plugin.use_sudo is True
        assert plugin.environment_variables == {'KAFKA_HOME': '/opt/kafka'}
        assert plugin.working_directory == '/tmp'
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        plugin = ScriptRecoveryPlugin()
        
        assert plugin.validate_config() is True
    
    def test_validate_config_invalid_script_directory(self):
        """Test configuration validation with invalid script directory."""
        config = {'script_directory': 123}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="script_directory must be a string"):
            plugin.validate_config()
    
    def test_validate_config_invalid_scripts(self):
        """Test configuration validation with invalid scripts."""
        config = {'scripts': 'not_a_dict'}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="scripts must be a dictionary"):
            plugin.validate_config()
    
    def test_validate_config_invalid_shell(self):
        """Test configuration validation with invalid shell."""
        config = {'default_shell': ''}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="default_shell must be a non-empty string"):
            plugin.validate_config()
    
    def test_validate_config_invalid_timeout(self):
        """Test configuration validation with invalid timeout."""
        config = {'timeout_seconds': -1}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="timeout_seconds must be a positive integer"):
            plugin.validate_config()
    
    def test_validate_config_invalid_use_sudo(self):
        """Test configuration validation with invalid use_sudo."""
        config = {'use_sudo': 'not_a_bool'}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="use_sudo must be a boolean"):
            plugin.validate_config()
    
    def test_validate_config_invalid_environment_variables(self):
        """Test configuration validation with invalid environment variables."""
        config = {'environment_variables': 'not_a_dict'}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="environment_variables must be a dictionary"):
            plugin.validate_config()
    
    def test_validate_config_invalid_working_directory(self):
        """Test configuration validation with invalid working directory."""
        config = {'working_directory': 123}
        plugin = ScriptRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="working_directory must be a string or None"):
            plugin.validate_config()
    
    @patch('subprocess.run')
    @patch('pathlib.Path.mkdir')
    def test_initialize_success(self, mock_mkdir, mock_run):
        """Test successful plugin initialization."""
        mock_run.return_value = Mock(returncode=0)
        
        plugin = ScriptRecoveryPlugin()
        
        assert plugin.initialize() is True
        mock_run.assert_called_once_with(
            ['/bin/bash', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    
    @patch('subprocess.run')
    @patch('pathlib.Path.mkdir')
    def test_initialize_shell_check_failure(self, mock_mkdir, mock_run):
        """Test plugin initialization with shell check failure."""
        mock_run.return_value = Mock(returncode=1)
        
        plugin = ScriptRecoveryPlugin()
        
        # Should still return True even if shell check fails
        assert plugin.initialize() is True
    
    @patch('subprocess.run')
    def test_initialize_exception(self, mock_run):
        """Test plugin initialization with exception."""
        mock_run.side_effect = Exception("Shell check failed")
        
        plugin = ScriptRecoveryPlugin()
        
        assert plugin.initialize() is False
    
    def test_supports_recovery_type(self):
        """Test recovery type support checking."""
        config = {
            'scripts': {
                'service_restart': 'restart.sh',
                'cleanup': 'cleanup.sh',
                'default': 'default_recovery.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        
        # Supported types
        assert plugin.supports_recovery_type("service_restart") is True
        assert plugin.supports_recovery_type("cleanup") is True
        assert plugin.supports_recovery_type("unknown_type") is True  # Has default
        
        # Test without default
        plugin.scripts = {'service_restart': 'restart.sh'}
        assert plugin.supports_recovery_type("service_restart") is True
        assert plugin.supports_recovery_type("unknown_type") is False  # No default
    
    def test_substitute_parameters(self):
        """Test parameter substitution."""
        plugin = ScriptRecoveryPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        
        text = "Node {node_id} of type {node_type} at {host}:{port} (JMX: {jmx_port})"
        result = plugin._substitute_parameters(text, node)
        
        expected = "Node kafka-1 of type kafka_broker at localhost:9092 (JMX: 9999)"
        assert result == expected
    
    def test_substitute_parameters_no_jmx(self):
        """Test parameter substitution without JMX port."""
        plugin = ScriptRecoveryPlugin()
        node = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="localhost",
            port=2181
        )
        
        text = "Node {node_id} JMX: {jmx_port}"
        result = plugin._substitute_parameters(text, node)
        
        expected = "Node zk-1 JMX: "
        assert result == expected
    
    @patch.dict('os.environ', {'EXISTING_VAR': 'existing_value'})
    def test_prepare_environment(self):
        """Test environment preparation."""
        config = {
            'environment_variables': {
                'CUSTOM_VAR': 'custom_value',
                'NODE_VAR': 'Node: {node_id}'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        
        env = plugin._prepare_environment(node)
        
        # Check existing environment is preserved
        assert env['EXISTING_VAR'] == 'existing_value'
        
        # Check custom variables
        assert env['CUSTOM_VAR'] == 'custom_value'
        assert env['NODE_VAR'] == 'Node: kafka-1'
        
        # Check node-specific variables
        assert env['KAFKA_NODE_ID'] == 'kafka-1'
        assert env['KAFKA_NODE_TYPE'] == 'kafka_broker'
        assert env['KAFKA_HOST'] == 'localhost'
        assert env['KAFKA_PORT'] == '9092'
        assert env['KAFKA_JMX_PORT'] == '9999'
    
    @patch('os.path.exists')
    @patch('os.access')
    def test_get_script_for_recovery_string_config(self, mock_access, mock_exists):
        """Test getting script for recovery with string configuration."""
        mock_exists.return_value = True
        mock_access.return_value = True
        
        config = {
            'script_directory': '/scripts',
            'scripts': {
                'restart': 'restart.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_script_for_recovery(node, "restart")
        
        assert result is not None
        script_path, script_args = result
        assert script_path == '/scripts/restart.sh'
        assert script_args == []
    
    @patch('os.path.exists')
    @patch('os.access')
    def test_get_script_for_recovery_dict_config(self, mock_access, mock_exists):
        """Test getting script for recovery with dictionary configuration."""
        mock_exists.return_value = True
        mock_access.return_value = True
        
        config = {
            'script_directory': '/scripts',
            'scripts': {
                'restart': {
                    'path': 'restart.sh',
                    'args': ['--force', '{node_id}']
                }
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_script_for_recovery(node, "restart")
        
        assert result is not None
        script_path, script_args = result
        assert script_path == '/scripts/restart.sh'
        assert script_args == ['--force', '{node_id}']
    
    @patch('os.path.exists')
    def test_get_script_for_recovery_not_found(self, mock_exists):
        """Test getting script for recovery when script doesn't exist."""
        mock_exists.return_value = False
        
        config = {
            'scripts': {
                'restart': 'restart.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_script_for_recovery(node, "restart")
        
        assert result is None
    
    @patch('os.path.exists')
    @patch('os.access')
    def test_get_script_for_recovery_not_executable(self, mock_access, mock_exists):
        """Test getting script for recovery when script is not executable."""
        mock_exists.return_value = True
        mock_access.return_value = False
        
        config = {
            'scripts': {
                'restart': 'restart.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_script_for_recovery(node, "restart")
        
        assert result is None
    
    def test_get_script_for_recovery_fallback_to_default(self):
        """Test getting script for recovery falls back to default."""
        config = {
            'scripts': {
                'default': 'default.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        with patch('os.path.exists', return_value=True), \
             patch('os.access', return_value=True):
            result = plugin._get_script_for_recovery(node, "unknown_type")
            
            assert result is not None
            script_path, script_args = result
            assert 'default.sh' in script_path
    
    @patch('os.access')
    def test_build_script_command_with_sudo(self, mock_access):
        """Test building script command with sudo."""
        mock_access.return_value = True
        
        plugin = ScriptRecoveryPlugin({'use_sudo': True})
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_script_command('/path/to/script.py', ['--arg', '{node_id}'], node)
        
        assert command == ['sudo', '/path/to/script.py', '--arg', 'kafka-1']
    
    @patch('os.access')
    def test_build_script_command_shell_script(self, mock_access):
        """Test building script command for shell script."""
        mock_access.return_value = False  # Not directly executable
        
        plugin = ScriptRecoveryPlugin({'use_sudo': False})
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_script_command('/path/to/script.sh', ['--arg'], node)
        
        assert command == ['/bin/bash', '/path/to/script.sh', '--arg']
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.access')
    def test_execute_recovery_success(self, mock_access, mock_exists, mock_run):
        """Test successful recovery execution."""
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Script executed successfully",
            stderr=""
        )
        
        config = {
            'scripts': {
                'service_restart': 'restart.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin.execute_recovery(node, "service_restart")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "script_recovery"
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "Script executed successfully"
        assert result.stderr == ""
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.access')
    def test_execute_recovery_failure(self, mock_access, mock_exists, mock_run):
        """Test failed recovery execution."""
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Script execution failed"
        )
        
        config = {
            'scripts': {
                'service_restart': 'restart.sh'
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin.execute_recovery(node, "service_restart")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "script_recovery"
        assert result.success is False
        assert result.exit_code == 1
        assert result.stderr == "Script execution failed"
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.access')
    def test_execute_recovery_timeout(self, mock_access, mock_exists, mock_run):
        """Test recovery execution timeout."""
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(['script'], 300)
        
        config = {
            'scripts': {
                'service_restart': 'restart.sh'
            },
            'timeout_seconds': 60
        }
        plugin = ScriptRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin.execute_recovery(node, "service_restart")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "script_recovery"
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out after 60 seconds" in result.stderr
    
    def test_execute_recovery_no_script(self):
        """Test recovery execution when no script is found."""
        plugin = ScriptRecoveryPlugin()
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        with pytest.raises(RecoveryError, match="No script found for node type kafka_broker and failure type unknown"):
            plugin.execute_recovery(node, "unknown")
    
    @patch('os.path.exists')
    @patch('os.access')
    def test_list_available_scripts(self, mock_access, mock_exists):
        """Test listing available scripts."""
        mock_exists.return_value = True
        mock_access.return_value = True
        
        config = {
            'script_directory': '/scripts',
            'scripts': {
                'restart': 'restart.sh',
                'cleanup': {
                    'path': 'cleanup.sh',
                    'args': ['--force']
                }
            }
        }
        plugin = ScriptRecoveryPlugin(config)
        
        scripts = plugin.list_available_scripts()
        
        assert 'restart' in scripts
        assert scripts['restart']['path'] == 'restart.sh'
        assert scripts['restart']['args'] == []
        assert scripts['restart']['resolved_path'] == '/scripts/restart.sh'
        
        assert 'cleanup' in scripts
        assert scripts['cleanup']['path'] == 'cleanup.sh'
        assert scripts['cleanup']['args'] == ['--force']
        assert scripts['cleanup']['resolved_path'] == '/scripts/cleanup.sh'
        assert scripts['cleanup']['exists'] is True
        assert scripts['cleanup']['executable'] is True
    
    def test_cleanup(self):
        """Test plugin cleanup."""
        plugin = ScriptRecoveryPlugin()
        
        # Should not raise any exceptions
        plugin.cleanup()


class TestAnsibleRecoveryPlugin:
    """Test cases for AnsibleRecoveryPlugin."""
    
    def test_plugin_initialization_default_config(self):
        """Test plugin initialization with default configuration."""
        plugin = AnsibleRecoveryPlugin()
        
        assert plugin.name == "AnsibleRecoveryPlugin"
        assert plugin.version == "1.0.0"
        assert plugin.description == "Execute Ansible playbooks for recovery"
        assert plugin.playbook_directory == '/opt/kafka-recovery/playbooks'
        assert plugin.playbooks == {}
        assert plugin.inventory_file is None
        assert plugin.inventory_directory is None
        assert plugin.ansible_playbook_path == 'ansible-playbook'
        assert plugin.timeout_seconds == 600
        assert plugin.extra_vars == {}
        assert plugin.ansible_config is None
        assert plugin.vault_password_file is None
        assert plugin.become is False
        assert plugin.become_user == 'root'
        assert plugin.verbosity == 0
    
    def test_plugin_initialization_custom_config(self):
        """Test plugin initialization with custom configuration."""
        config = {
            'playbook_directory': '/custom/playbooks',
            'playbooks': {
                'restart': 'restart.yml',
                'cleanup': {'path': 'cleanup.yml', 'vars': {'force': True}}
            },
            'inventory_file': '/etc/ansible/hosts',
            'ansible_playbook_path': '/usr/local/bin/ansible-playbook',
            'timeout_seconds': 1200,
            'extra_vars': {'env': 'production'},
            'ansible_config': '/etc/ansible/ansible.cfg',
            'vault_password_file': '/etc/ansible/vault_pass',
            'become': True,
            'become_user': 'kafka',
            'verbosity': 2
        }
        
        plugin = AnsibleRecoveryPlugin(config)
        
        assert plugin.playbook_directory == '/custom/playbooks'
        assert plugin.playbooks == config['playbooks']
        assert plugin.inventory_file == '/etc/ansible/hosts'
        assert plugin.ansible_playbook_path == '/usr/local/bin/ansible-playbook'
        assert plugin.timeout_seconds == 1200
        assert plugin.extra_vars == {'env': 'production'}
        assert plugin.ansible_config == '/etc/ansible/ansible.cfg'
        assert plugin.vault_password_file == '/etc/ansible/vault_pass'
        assert plugin.become is True
        assert plugin.become_user == 'kafka'
        assert plugin.verbosity == 2
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        plugin = AnsibleRecoveryPlugin()
        
        assert plugin.validate_config() is True
    
    def test_validate_config_invalid_playbook_directory(self):
        """Test configuration validation with invalid playbook directory."""
        config = {'playbook_directory': 123}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="playbook_directory must be a string"):
            plugin.validate_config()
    
    def test_validate_config_invalid_playbooks(self):
        """Test configuration validation with invalid playbooks."""
        config = {'playbooks': 'not_a_dict'}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="playbooks must be a dictionary"):
            plugin.validate_config()
    
    def test_validate_config_invalid_ansible_path(self):
        """Test configuration validation with invalid ansible path."""
        config = {'ansible_playbook_path': ''}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="ansible_playbook_path must be a non-empty string"):
            plugin.validate_config()
    
    def test_validate_config_invalid_timeout(self):
        """Test configuration validation with invalid timeout."""
        config = {'timeout_seconds': -1}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="timeout_seconds must be a positive integer"):
            plugin.validate_config()
    
    def test_validate_config_invalid_extra_vars(self):
        """Test configuration validation with invalid extra vars."""
        config = {'extra_vars': 'not_a_dict'}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="extra_vars must be a dictionary"):
            plugin.validate_config()
    
    def test_validate_config_invalid_become(self):
        """Test configuration validation with invalid become."""
        config = {'become': 'not_a_bool'}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="become must be a boolean"):
            plugin.validate_config()
    
    def test_validate_config_invalid_verbosity(self):
        """Test configuration validation with invalid verbosity."""
        config = {'verbosity': -1}
        plugin = AnsibleRecoveryPlugin(config)
        
        with pytest.raises(ValidationError, match="verbosity must be a non-negative integer"):
            plugin.validate_config()
    
    @patch('subprocess.run')
    @patch('pathlib.Path.mkdir')
    def test_initialize_success(self, mock_mkdir, mock_run):
        """Test successful plugin initialization."""
        mock_run.return_value = Mock(returncode=0)
        
        plugin = AnsibleRecoveryPlugin()
        
        assert plugin.initialize() is True
        mock_run.assert_called_once_with(
            ['ansible-playbook', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    
    @patch('subprocess.run')
    def test_initialize_failure(self, mock_run):
        """Test failed plugin initialization."""
        mock_run.return_value = Mock(returncode=1)
        
        plugin = AnsibleRecoveryPlugin()
        
        assert plugin.initialize() is False
    
    @patch('subprocess.run')
    def test_initialize_subprocess_error(self, mock_run):
        """Test plugin initialization with subprocess error."""
        mock_run.side_effect = subprocess.SubprocessError("Command failed")
        
        plugin = AnsibleRecoveryPlugin()
        
        assert plugin.initialize() is False
    
    def test_supports_recovery_type(self):
        """Test recovery type support checking."""
        config = {
            'playbooks': {
                'service_restart': 'restart.yml',
                'cleanup': 'cleanup.yml',
                'default': 'default_recovery.yml'
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        
        # Supported types
        assert plugin.supports_recovery_type("service_restart") is True
        assert plugin.supports_recovery_type("cleanup") is True
        assert plugin.supports_recovery_type("unknown_type") is True  # Has default
        
        # Test without default
        plugin.playbooks = {'service_restart': 'restart.yml'}
        assert plugin.supports_recovery_type("service_restart") is True
        assert plugin.supports_recovery_type("unknown_type") is False  # No default
    
    def test_get_node_variables(self):
        """Test getting node variables."""
        plugin = AnsibleRecoveryPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        
        vars_dict = plugin._get_node_variables(node)
        
        expected = {
            'kafka_node_id': 'kafka-1',
            'kafka_node_type': 'kafka_broker',
            'kafka_host': 'localhost',
            'kafka_port': 9092,
            'kafka_jmx_port': 9999,
            'target_host': 'localhost'
        }
        assert vars_dict == expected
    
    def test_get_node_variables_no_jmx(self):
        """Test getting node variables without JMX port."""
        plugin = AnsibleRecoveryPlugin()
        node = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="localhost",
            port=2181
        )
        
        vars_dict = plugin._get_node_variables(node)
        
        expected = {
            'kafka_node_id': 'zk-1',
            'kafka_node_type': 'zookeeper',
            'kafka_host': 'localhost',
            'kafka_port': 2181,
            'kafka_jmx_port': '',
            'target_host': 'localhost'
        }
        assert vars_dict == expected
    
    def test_substitute_parameters(self):
        """Test parameter substitution."""
        plugin = AnsibleRecoveryPlugin()
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        
        text = "Node {node_id} of type {node_type} at {host}:{port} (JMX: {jmx_port})"
        result = plugin._substitute_parameters(text, node)
        
        expected = "Node kafka-1 of type kafka_broker at localhost:9092 (JMX: 9999)"
        assert result == expected
    
    @patch.dict('os.environ', {'EXISTING_VAR': 'existing_value'})
    def test_prepare_environment(self):
        """Test environment preparation."""
        config = {
            'ansible_config': '/etc/ansible/ansible.cfg'
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        
        env = plugin._prepare_environment(node)
        
        # Check existing environment is preserved
        assert env['EXISTING_VAR'] == 'existing_value'
        
        # Check Ansible config
        assert env['ANSIBLE_CONFIG'] == '/etc/ansible/ansible.cfg'
        
        # Check node-specific variables
        assert env['KAFKA_NODE_ID'] == 'kafka-1'
        assert env['KAFKA_NODE_TYPE'] == 'kafka_broker'
        assert env['KAFKA_HOST'] == 'localhost'
        assert env['KAFKA_PORT'] == '9092'
        assert env['KAFKA_JMX_PORT'] == '9999'
    
    def test_dict_to_json_string(self):
        """Test dictionary to JSON string conversion."""
        plugin = AnsibleRecoveryPlugin()
        data = {
            'string_var': 'value',
            'int_var': 42,
            'bool_var': True,
            'list_var': [1, 2, 3]
        }
        
        result = plugin._dict_to_json_string(data)
        
        # Parse back to verify it's valid JSON
        import json
        parsed = json.loads(result)
        assert parsed == data
    
    @patch('os.path.exists')
    def test_get_playbook_for_recovery_string_config(self, mock_exists):
        """Test getting playbook for recovery with string configuration."""
        mock_exists.return_value = True
        
        config = {
            'playbook_directory': '/playbooks',
            'playbooks': {
                'restart': 'restart.yml'
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_playbook_for_recovery(node, "restart")
        
        assert result is not None
        playbook_path, playbook_vars = result
        assert playbook_path == '/playbooks/restart.yml'
        assert playbook_vars == {}
    
    @patch('os.path.exists')
    def test_get_playbook_for_recovery_dict_config(self, mock_exists):
        """Test getting playbook for recovery with dictionary configuration."""
        mock_exists.return_value = True
        
        config = {
            'playbook_directory': '/playbooks',
            'playbooks': {
                'restart': {
                    'path': 'restart.yml',
                    'vars': {'force': True, 'node': '{node_id}'}
                }
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_playbook_for_recovery(node, "restart")
        
        assert result is not None
        playbook_path, playbook_vars = result
        assert playbook_path == '/playbooks/restart.yml'
        assert playbook_vars == {'force': True, 'node': '{node_id}'}
    
    @patch('os.path.exists')
    def test_get_playbook_for_recovery_not_found(self, mock_exists):
        """Test getting playbook for recovery when playbook doesn't exist."""
        mock_exists.return_value = False
        
        config = {
            'playbooks': {
                'restart': 'restart.yml'
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin._get_playbook_for_recovery(node, "restart")
        
        assert result is None
    
    def test_build_ansible_command_basic(self):
        """Test building basic Ansible command."""
        plugin = AnsibleRecoveryPlugin()
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_ansible_command('/path/to/playbook.yml', {}, node)
        
        expected_start = ['ansible-playbook', '-i', 'localhost,']
        assert command[:3] == expected_start
        assert command[-1] == '/path/to/playbook.yml'
    
    def test_build_ansible_command_with_inventory_file(self):
        """Test building Ansible command with inventory file."""
        config = {'inventory_file': '/etc/ansible/hosts'}
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_ansible_command('/path/to/playbook.yml', {}, node)
        
        assert '-i' in command
        inventory_index = command.index('-i')
        assert command[inventory_index + 1] == '/etc/ansible/hosts'
    
    def test_build_ansible_command_with_verbosity(self):
        """Test building Ansible command with verbosity."""
        config = {'verbosity': 3}
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_ansible_command('/path/to/playbook.yml', {}, node)
        
        assert '-vvv' in command
    
    def test_build_ansible_command_with_become(self):
        """Test building Ansible command with become options."""
        config = {'become': True, 'become_user': 'kafka'}
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_ansible_command('/path/to/playbook.yml', {}, node)
        
        assert '--become' in command
        assert '--become-user' in command
        become_user_index = command.index('--become-user')
        assert command[become_user_index + 1] == 'kafka'
    
    def test_build_ansible_command_with_extra_vars(self):
        """Test building Ansible command with extra variables."""
        config = {'extra_vars': {'env': 'production'}}
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        command = plugin._build_ansible_command('/path/to/playbook.yml', {'force': True}, node)
        
        assert '--extra-vars' in command
        extra_vars_index = command.index('--extra-vars')
        vars_json = command[extra_vars_index + 1]
        
        # Parse the JSON to verify it contains expected variables
        import json
        vars_dict = json.loads(vars_json)
        assert 'env' in vars_dict
        assert 'force' in vars_dict
        assert 'kafka_node_id' in vars_dict
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_execute_recovery_success(self, mock_exists, mock_run):
        """Test successful recovery execution."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Playbook executed successfully",
            stderr=""
        )
        
        config = {
            'playbooks': {
                'service_restart': 'restart.yml'
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin.execute_recovery(node, "service_restart")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "ansible_recovery"
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "Playbook executed successfully"
        assert result.stderr == ""
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_execute_recovery_failure(self, mock_exists, mock_run):
        """Test failed recovery execution."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Playbook execution failed"
        )
        
        config = {
            'playbooks': {
                'service_restart': 'restart.yml'
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin.execute_recovery(node, "service_restart")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "ansible_recovery"
        assert result.success is False
        assert result.exit_code == 1
        assert result.stderr == "Playbook execution failed"
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_execute_recovery_timeout(self, mock_exists, mock_run):
        """Test recovery execution timeout."""
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(['ansible-playbook'], 600)
        
        config = {
            'playbooks': {
                'service_restart': 'restart.yml'
            },
            'timeout_seconds': 300
        }
        plugin = AnsibleRecoveryPlugin(config)
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        result = plugin.execute_recovery(node, "service_restart")
        
        assert result.node_id == "kafka-1"
        assert result.action_type == "ansible_recovery"
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out after 300 seconds" in result.stderr
    
    def test_execute_recovery_no_playbook(self):
        """Test recovery execution when no playbook is found."""
        plugin = AnsibleRecoveryPlugin()
        node = NodeConfig(node_id="kafka-1", node_type="kafka_broker", host="localhost", port=9092)
        
        with pytest.raises(RecoveryError, match="No playbook found for node type kafka_broker and failure type unknown"):
            plugin.execute_recovery(node, "unknown")
    
    @patch('os.path.exists')
    def test_list_available_playbooks(self, mock_exists):
        """Test listing available playbooks."""
        mock_exists.return_value = True
        
        config = {
            'playbook_directory': '/playbooks',
            'playbooks': {
                'restart': 'restart.yml',
                'cleanup': {
                    'path': 'cleanup.yml',
                    'vars': {'force': True}
                }
            }
        }
        plugin = AnsibleRecoveryPlugin(config)
        
        playbooks = plugin.list_available_playbooks()
        
        assert 'restart' in playbooks
        assert playbooks['restart']['path'] == 'restart.yml'
        assert playbooks['restart']['vars'] == {}
        assert playbooks['restart']['resolved_path'] == '/playbooks/restart.yml'
        
        assert 'cleanup' in playbooks
        assert playbooks['cleanup']['path'] == 'cleanup.yml'
        assert playbooks['cleanup']['vars'] == {'force': True}
        assert playbooks['cleanup']['resolved_path'] == '/playbooks/cleanup.yml'
        assert playbooks['cleanup']['exists'] is True
    
    def test_cleanup(self):
        """Test plugin cleanup."""
        plugin = AnsibleRecoveryPlugin()
        
        # Should not raise any exceptions
        plugin.cleanup()


if __name__ == "__main__":
    pytest.main([__file__])