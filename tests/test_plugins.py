"""
Unit tests for the plugin system.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.kafka_self_healing.exceptions import PluginError, PluginLoadError, PluginValidationError
from src.kafka_self_healing.models import NodeConfig, NodeStatus, RecoveryResult
from src.kafka_self_healing.plugins import (
    MonitoringPlugin,
    NotificationPlugin,
    PluginBase,
    PluginManager,
    RecoveryPlugin,
)


class TestPluginBase(unittest.TestCase):
    """Test cases for PluginBase class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a concrete implementation for testing
        class TestPlugin(PluginBase):
            def validate_config(self):
                return True
            
            def initialize(self):
                return True
            
            def cleanup(self):
                pass
        
        self.TestPlugin = TestPlugin
    
    def test_plugin_base_initialization(self):
        """Test plugin base initialization."""
        config = {'test_key': 'test_value'}
        plugin = self.TestPlugin(config)
        
        self.assertEqual(plugin.config, config)
        self.assertEqual(plugin.name, 'TestPlugin')
        self.assertEqual(plugin.version, '1.0.0')
        self.assertEqual(plugin.description, '')
    
    def test_plugin_base_initialization_no_config(self):
        """Test plugin base initialization without config."""
        plugin = self.TestPlugin()
        
        self.assertEqual(plugin.config, {})
        self.assertEqual(plugin.name, 'TestPlugin')
    
    def test_plugin_base_get_info(self):
        """Test plugin info retrieval."""
        plugin = self.TestPlugin()
        info = plugin.get_info()
        
        expected_info = {
            'name': 'TestPlugin',
            'version': '1.0.0',
            'description': ''
        }
        self.assertEqual(info, expected_info)
    
    def test_plugin_base_with_custom_attributes(self):
        """Test plugin base with custom version and description."""
        class CustomPlugin(PluginBase):
            __version__ = '2.1.0'
            __description__ = 'Custom test plugin'
            
            def validate_config(self):
                return True
            
            def initialize(self):
                return True
            
            def cleanup(self):
                pass
        
        plugin = CustomPlugin()
        self.assertEqual(plugin.version, '2.1.0')
        self.assertEqual(plugin.description, 'Custom test plugin')


class TestMonitoringPlugin(unittest.TestCase):
    """Test cases for MonitoringPlugin class."""
    
    def setUp(self):
        """Set up test fixtures."""
        class TestMonitoringPlugin(MonitoringPlugin):
            def validate_config(self):
                return True
            
            def initialize(self):
                return True
            
            def cleanup(self):
                pass
            
            def check_health(self, node):
                return NodeStatus(
                    node_id=node.node_id,
                    is_healthy=True,
                    last_check_time=None,
                    response_time_ms=100.0,
                    error_message=None,
                    monitoring_method='test'
                )
            
            def supports_node_type(self, node_type):
                return node_type == 'kafka_broker'
        
        self.TestMonitoringPlugin = TestMonitoringPlugin
    
    def test_monitoring_plugin_check_health(self):
        """Test monitoring plugin health check."""
        plugin = self.TestMonitoringPlugin()
        node = NodeConfig(
            node_id='test-node',
            node_type='kafka_broker',
            host='localhost',
            port=9092,
            jmx_port=None,
            monitoring_methods=[],
            recovery_actions=[],
            retry_policy=None
        )
        
        status = plugin.check_health(node)
        self.assertEqual(status.node_id, 'test-node')
        self.assertTrue(status.is_healthy)
        self.assertEqual(status.response_time_ms, 100.0)
    
    def test_monitoring_plugin_supports_node_type(self):
        """Test monitoring plugin node type support."""
        plugin = self.TestMonitoringPlugin()
        
        self.assertTrue(plugin.supports_node_type('kafka_broker'))
        self.assertFalse(plugin.supports_node_type('zookeeper'))


class TestRecoveryPlugin(unittest.TestCase):
    """Test cases for RecoveryPlugin class."""
    
    def setUp(self):
        """Set up test fixtures."""
        class TestRecoveryPlugin(RecoveryPlugin):
            def validate_config(self):
                return True
            
            def initialize(self):
                return True
            
            def cleanup(self):
                pass
            
            def execute_recovery(self, node, failure_type):
                return RecoveryResult(
                    node_id=node.node_id,
                    action_type='test_recovery',
                    command_executed='test command',
                    exit_code=0,
                    stdout='success',
                    stderr='',
                    execution_time=None,
                    success=True
                )
            
            def supports_recovery_type(self, recovery_type):
                return recovery_type == 'service_restart'
        
        self.TestRecoveryPlugin = TestRecoveryPlugin
    
    def test_recovery_plugin_execute_recovery(self):
        """Test recovery plugin execution."""
        plugin = self.TestRecoveryPlugin()
        node = NodeConfig(
            node_id='test-node',
            node_type='kafka_broker',
            host='localhost',
            port=9092,
            jmx_port=None,
            monitoring_methods=[],
            recovery_actions=[],
            retry_policy=None
        )
        
        result = plugin.execute_recovery(node, 'service_failure')
        self.assertEqual(result.node_id, 'test-node')
        self.assertEqual(result.action_type, 'test_recovery')
        self.assertTrue(result.success)
    
    def test_recovery_plugin_supports_recovery_type(self):
        """Test recovery plugin recovery type support."""
        plugin = self.TestRecoveryPlugin()
        
        self.assertTrue(plugin.supports_recovery_type('service_restart'))
        self.assertFalse(plugin.supports_recovery_type('script_execution'))


class TestNotificationPlugin(unittest.TestCase):
    """Test cases for NotificationPlugin class."""
    
    def setUp(self):
        """Set up test fixtures."""
        class TestNotificationPlugin(NotificationPlugin):
            def validate_config(self):
                return True
            
            def initialize(self):
                return True
            
            def cleanup(self):
                pass
            
            def send_notification(self, message, subject, recipients):
                return True
            
            def supports_notification_type(self, notification_type):
                return notification_type == 'email'
        
        self.TestNotificationPlugin = TestNotificationPlugin
    
    def test_notification_plugin_send_notification(self):
        """Test notification plugin sending."""
        plugin = self.TestNotificationPlugin()
        
        result = plugin.send_notification(
            'Test message',
            'Test subject',
            ['test@example.com']
        )
        self.assertTrue(result)
    
    def test_notification_plugin_supports_notification_type(self):
        """Test notification plugin type support."""
        plugin = self.TestNotificationPlugin()
        
        self.assertTrue(plugin.supports_notification_type('email'))
        self.assertFalse(plugin.supports_notification_type('slack'))


class TestPluginManager(unittest.TestCase):
    """Test cases for PluginManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plugin_manager = PluginManager()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.plugin_manager.cleanup_plugins()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_plugin_manager_initialization(self):
        """Test plugin manager initialization."""
        plugin_dirs = ['/path/to/plugins']
        manager = PluginManager(plugin_dirs)
        
        self.assertEqual(manager.plugin_dirs, plugin_dirs)
        self.assertEqual(len(manager.monitoring_plugins), 0)
        self.assertEqual(len(manager.recovery_plugins), 0)
        self.assertEqual(len(manager.notification_plugins), 0)
    
    def test_add_plugin_directory(self):
        """Test adding plugin directory."""
        plugin_dir = '/path/to/plugins'
        self.plugin_manager.add_plugin_directory(plugin_dir)
        
        self.assertIn(plugin_dir, self.plugin_manager.plugin_dirs)
    
    def test_add_plugin_directory_duplicate(self):
        """Test adding duplicate plugin directory."""
        plugin_dir = '/path/to/plugins'
        self.plugin_manager.add_plugin_directory(plugin_dir)
        self.plugin_manager.add_plugin_directory(plugin_dir)
        
        self.assertEqual(self.plugin_manager.plugin_dirs.count(plugin_dir), 1)
    
    def test_load_plugins_nonexistent_directory(self):
        """Test loading plugins from nonexistent directory."""
        self.plugin_manager.add_plugin_directory('/nonexistent/path')
        
        # Should not raise exception
        self.plugin_manager.load_plugins()
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 0)
    
    def test_load_valid_monitoring_plugin(self):
        """Test loading a valid monitoring plugin."""
        # Create a valid monitoring plugin file
        plugin_content = '''
from src.kafka_self_healing.plugins import MonitoringPlugin
from src.kafka_self_healing.models import NodeStatus

class TestMonitoringPlugin(MonitoringPlugin):
    def validate_config(self):
        return True
    
    def initialize(self):
        return True
    
    def cleanup(self):
        pass
    
    def check_health(self, node):
        return NodeStatus(
            node_id=node.node_id,
            is_healthy=True,
            last_check_time=None,
            response_time_ms=100.0,
            error_message=None,
            monitoring_method='test'
        )
    
    def supports_node_type(self, node_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'test_monitoring_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 1)
        self.assertIn('TestMonitoringPlugin', self.plugin_manager.monitoring_plugins)
    
    def test_load_valid_recovery_plugin(self):
        """Test loading a valid recovery plugin."""
        plugin_content = '''
from src.kafka_self_healing.plugins import RecoveryPlugin
from src.kafka_self_healing.models import RecoveryResult

class TestRecoveryPlugin(RecoveryPlugin):
    def validate_config(self):
        return True
    
    def initialize(self):
        return True
    
    def cleanup(self):
        pass
    
    def execute_recovery(self, node, failure_type):
        return RecoveryResult(
            node_id=node.node_id,
            action_type='test',
            command_executed='test',
            exit_code=0,
            stdout='',
            stderr='',
            execution_time=None,
            success=True
        )
    
    def supports_recovery_type(self, recovery_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'test_recovery_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        self.assertEqual(len(self.plugin_manager.recovery_plugins), 1)
        self.assertIn('TestRecoveryPlugin', self.plugin_manager.recovery_plugins)
    
    def test_load_valid_notification_plugin(self):
        """Test loading a valid notification plugin."""
        plugin_content = '''
from src.kafka_self_healing.plugins import NotificationPlugin

class TestNotificationPlugin(NotificationPlugin):
    def validate_config(self):
        return True
    
    def initialize(self):
        return True
    
    def cleanup(self):
        pass
    
    def send_notification(self, message, subject, recipients):
        return True
    
    def supports_notification_type(self, notification_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'test_notification_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        self.assertEqual(len(self.plugin_manager.notification_plugins), 1)
        self.assertIn('TestNotificationPlugin', self.plugin_manager.notification_plugins)
    
    def test_load_plugin_with_validation_failure(self):
        """Test loading plugin that fails validation."""
        plugin_content = '''
from src.kafka_self_healing.plugins import MonitoringPlugin

class FailingValidationPlugin(MonitoringPlugin):
    def validate_config(self):
        return False
    
    def initialize(self):
        return True
    
    def cleanup(self):
        pass
    
    def check_health(self, node):
        pass
    
    def supports_node_type(self, node_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'failing_validation_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        # Plugin should not be loaded due to validation failure
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 0)
    
    def test_load_plugin_with_initialization_failure(self):
        """Test loading plugin that fails initialization."""
        plugin_content = '''
from src.kafka_self_healing.plugins import MonitoringPlugin

class FailingInitializationPlugin(MonitoringPlugin):
    def validate_config(self):
        return True
    
    def initialize(self):
        return False
    
    def cleanup(self):
        pass
    
    def check_health(self, node):
        pass
    
    def supports_node_type(self, node_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'failing_init_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        # Plugin should not be loaded due to initialization failure
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 0)
    
    def test_load_invalid_plugin_syntax(self):
        """Test loading plugin with syntax errors."""
        plugin_content = '''
from src.kafka_self_healing.plugins import MonitoringPlugin

class InvalidSyntaxPlugin(MonitoringPlugin):
    def validate_config(self):
        return True
    
    def initialize(self):
        return True
    
    def cleanup(self):
        pass
    
    def check_health(self, node):
        # Invalid syntax
        if True
            pass
    
    def supports_node_type(self, node_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'invalid_syntax_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        # Plugin should not be loaded due to syntax error
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 0)
        self.assertTrue(len(self.plugin_manager.plugin_errors) > 0)
    
    def test_get_plugin_methods(self):
        """Test plugin retrieval methods."""
        # Create and load test plugins
        self.test_load_valid_monitoring_plugin()
        self.test_load_valid_recovery_plugin()
        self.test_load_valid_notification_plugin()
        
        # Test get all plugins
        monitoring_plugins = self.plugin_manager.get_monitoring_plugins()
        recovery_plugins = self.plugin_manager.get_recovery_plugins()
        notification_plugins = self.plugin_manager.get_notification_plugins()
        
        self.assertEqual(len(monitoring_plugins), 1)
        self.assertEqual(len(recovery_plugins), 1)
        self.assertEqual(len(notification_plugins), 1)
        
        # Test get specific plugins
        monitoring_plugin = self.plugin_manager.get_monitoring_plugin('TestMonitoringPlugin')
        recovery_plugin = self.plugin_manager.get_recovery_plugin('TestRecoveryPlugin')
        notification_plugin = self.plugin_manager.get_notification_plugin('TestNotificationPlugin')
        
        self.assertIsNotNone(monitoring_plugin)
        self.assertIsNotNone(recovery_plugin)
        self.assertIsNotNone(notification_plugin)
        
        # Test get nonexistent plugins
        self.assertIsNone(self.plugin_manager.get_monitoring_plugin('NonexistentPlugin'))
        self.assertIsNone(self.plugin_manager.get_recovery_plugin('NonexistentPlugin'))
        self.assertIsNone(self.plugin_manager.get_notification_plugin('NonexistentPlugin'))
    
    def test_get_plugin_errors(self):
        """Test plugin error retrieval."""
        # Load invalid plugin to generate errors
        self.test_load_invalid_plugin_syntax()
        
        errors = self.plugin_manager.get_plugin_errors()
        self.assertTrue(len(errors) > 0)
        
        # Ensure it returns a copy
        errors['test'] = 'test'
        original_errors = self.plugin_manager.get_plugin_errors()
        self.assertNotIn('test', original_errors)
    
    def test_cleanup_plugins(self):
        """Test plugin cleanup."""
        # Load test plugins
        self.test_load_valid_monitoring_plugin()
        self.test_load_valid_recovery_plugin()
        self.test_load_valid_notification_plugin()
        
        # Verify plugins are loaded
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 1)
        self.assertEqual(len(self.plugin_manager.recovery_plugins), 1)
        self.assertEqual(len(self.plugin_manager.notification_plugins), 1)
        
        # Cleanup plugins
        self.plugin_manager.cleanup_plugins()
        
        # Verify plugins are cleaned up
        self.assertEqual(len(self.plugin_manager.monitoring_plugins), 0)
        self.assertEqual(len(self.plugin_manager.recovery_plugins), 0)
        self.assertEqual(len(self.plugin_manager.notification_plugins), 0)
        self.assertEqual(len(self.plugin_manager.loaded_modules), 0)
        self.assertEqual(len(self.plugin_manager.plugin_errors), 0)
    
    @patch('src.kafka_self_healing.plugins.logger')
    def test_plugin_cleanup_with_errors(self, mock_logger):
        """Test plugin cleanup with errors."""
        # Create a plugin that raises exception during cleanup
        plugin_content = '''
from src.kafka_self_healing.plugins import MonitoringPlugin

class ErrorCleanupPlugin(MonitoringPlugin):
    def validate_config(self):
        return True
    
    def initialize(self):
        return True
    
    def cleanup(self):
        raise Exception("Cleanup error")
    
    def check_health(self, node):
        pass
    
    def supports_node_type(self, node_type):
        return True
'''
        
        plugin_file = Path(self.temp_dir) / 'error_cleanup_plugin.py'
        plugin_file.write_text(plugin_content)
        
        self.plugin_manager.add_plugin_directory(self.temp_dir)
        self.plugin_manager.load_plugins()
        
        # Cleanup should handle errors gracefully
        self.plugin_manager.cleanup_plugins()
        
        # Verify error was logged
        mock_logger.error.assert_called()


if __name__ == '__main__':
    unittest.main()