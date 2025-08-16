"""
Integration tests for the main application entry point.

Tests application lifecycle, signal handling, and component integration.
"""

import os
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.main import KafkaSelfHealingApp, main
from src.kafka_self_healing.exceptions import ValidationError, SystemError
from src.kafka_self_healing.models import NodeConfig, RetryPolicy


class TestKafkaSelfHealingApp(unittest.TestCase):
    """Test cases for KafkaSelfHealingApp class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_config.yaml"
        
        # Create a minimal test configuration
        config_content = """
cluster:
  cluster_name: "test-cluster"
  nodes:
    - node_id: "kafka-1"
      node_type: "kafka_broker"
      host: "localhost"
      port: 9092
      jmx_port: 9999
      monitoring_methods: ["socket"]
      recovery_actions: ["service_restart"]
  monitoring_interval_seconds: 30
  default_retry_policy:
    max_attempts: 3
    initial_delay_seconds: 5
    backoff_multiplier: 2.0
    max_delay_seconds: 60

notification:
  smtp_host: "localhost"
  smtp_port: 587
  smtp_username: "test@example.com"
  smtp_password: "password"
  sender_email: "test@example.com"
  recipients: ["admin@example.com"]
  subject_prefix: "[Test]"

logging:
  log_dir: "test_logs"
  log_level: "INFO"
  console_logging: true
"""
        
        with open(self.config_file, 'w') as f:
            f.write(config_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_app_initialization_with_config(self):
        """Test application initialization with configuration file."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        
        # Should initialize without errors
        app.initialize()
        
        # Check that all components are initialized
        self.assertIsNotNone(app.config_manager)
        self.assertIsNotNone(app.logging_service)
        self.assertIsNotNone(app.monitoring_service)
        self.assertIsNotNone(app.recovery_engine)
        self.assertIsNotNone(app.notification_service)
        self.assertIsNotNone(app.plugin_manager)
        self.assertIsNotNone(app.logger)
    
    def test_app_initialization_without_config(self):
        """Test application initialization without configuration file."""
        app = KafkaSelfHealingApp()
        
        # Should raise ValidationError when no config file is found
        with self.assertRaises(ValidationError):
            app.initialize()
    
    def test_app_initialization_with_invalid_config(self):
        """Test application initialization with invalid configuration."""
        # Create invalid config file
        invalid_config = Path(self.temp_dir) / "invalid_config.yaml"
        with open(invalid_config, 'w') as f:
            f.write("invalid: yaml: content:")
        
        app = KafkaSelfHealingApp(config_path=str(invalid_config))
        
        # Should raise ValidationError for invalid YAML
        with self.assertRaises(SystemError):
            app.initialize()
    
    def test_app_start_stop_lifecycle(self):
        """Test application start and stop lifecycle."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Should start successfully
        app.start()
        self.assertTrue(app.running)
        
        # Should stop successfully
        app.stop()
        self.assertFalse(app.running)
    
    def test_app_start_when_already_running(self):
        """Test starting application when already running."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        # Should raise SystemError when trying to start again
        with self.assertRaises(SystemError):
            app.start()
        
        app.stop()
    
    def test_app_stop_when_not_running(self):
        """Test stopping application when not running."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Should not raise error when stopping non-running app
        app.stop()  # Should complete without error
    
    @patch('src.kafka_self_healing.main.signal.signal')
    def test_signal_handler_setup(self, mock_signal):
        """Test signal handler setup and restoration."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock original handlers
        mock_signal.return_value = Mock()
        
        app.start()
        
        # Should have set up signal handlers
        self.assertEqual(mock_signal.call_count, 2)  # SIGTERM and SIGINT
        
        app.stop()
        
        # Should have restored original handlers
        self.assertEqual(mock_signal.call_count, 4)  # 2 setup + 2 restore
    
    def test_component_integration(self):
        """Test that components are properly wired together."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Check that monitoring service has failure callbacks registered
        self.assertGreater(len(app.monitoring_service._failure_callbacks), 0)
        self.assertGreater(len(app.monitoring_service._recovery_callbacks), 0)
        
        # Check that recovery engine has escalation callbacks registered
        self.assertGreater(len(app.recovery_engine.escalation_callbacks), 0)
    
    def test_system_status(self):
        """Test system status reporting."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        status = app.get_system_status()
        
        # Should contain expected status fields
        self.assertIn('running', status)
        self.assertIn('uptime_seconds', status)
        self.assertIn('components', status)
        
        # Should contain component status
        self.assertIn('monitoring', status['components'])
        self.assertIn('recovery', status['components'])
        self.assertIn('notification', status['components'])
    
    def test_system_health_check(self):
        """Test periodic system health checking."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        # Mock logger to capture health check messages
        with patch.object(app.logger, 'warning') as mock_warning:
            # Stop monitoring to trigger health check warning
            app.monitoring_service.stop_monitoring()
            
            # Run health check
            app._check_system_health()
            
            # Should log warning about inactive monitoring
            mock_warning.assert_called()
        
        app.stop()
    
    def test_run_method_with_shutdown_event(self):
        """Test run method with shutdown event."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        # Set shutdown event after short delay
        def set_shutdown():
            time.sleep(0.1)
            app.shutdown_event.set()
        
        shutdown_thread = threading.Thread(target=set_shutdown)
        shutdown_thread.start()
        
        # Run should exit when shutdown event is set
        start_time = time.time()
        app.run()
        duration = time.time() - start_time
        
        # Should exit quickly due to shutdown event
        self.assertLess(duration, 1.0)
        
        shutdown_thread.join()
    
    def test_run_method_without_start(self):
        """Test run method when system is not started."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Should raise SystemError when running without starting
        with self.assertRaises(SystemError):
            app.run()
    
    @patch('src.kafka_self_healing.main.Path.exists')
    def test_default_config_file_discovery(self, mock_exists):
        """Test automatic discovery of default configuration files."""
        # Mock that config.yaml exists
        mock_exists.side_effect = lambda path: str(path) == 'config.yaml'
        
        with patch.object(KafkaSelfHealingApp, '_initialize_configuration') as mock_init:
            app = KafkaSelfHealingApp()
            app._initialize_configuration()
            
            # Should have found config.yaml
            self.assertEqual(app.config_path, 'config.yaml')


class TestMainFunction(unittest.TestCase):
    """Test cases for main function and CLI interface."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_config.yaml"
        
        # Create a minimal test configuration
        config_content = """
cluster:
  cluster_name: "test-cluster"
  nodes:
    - node_id: "kafka-1"
      node_type: "kafka_broker"
      host: "localhost"
      port: 9092
      monitoring_methods: ["socket"]
      recovery_actions: ["service_restart"]
  monitoring_interval_seconds: 30
  default_retry_policy:
    max_attempts: 3
    initial_delay_seconds: 5
    backoff_multiplier: 2.0
    max_delay_seconds: 60

notification:
  smtp_host: "localhost"
  smtp_port: 587
  smtp_username: "test@example.com"
  smtp_password: "password"
  sender_email: "test@example.com"
  recipients: ["admin@example.com"]
  subject_prefix: "[Test]"
"""
        
        with open(self.config_file, 'w') as f:
            f.write(config_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('sys.argv', ['main.py', '--config', 'test_config.yaml'])
    @patch('src.kafka_self_healing.main.KafkaSelfHealingApp')
    def test_main_with_config_argument(self, mock_app_class):
        """Test main function with config argument."""
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        
        # Mock app to avoid actual execution
        mock_app.initialize.return_value = None
        mock_app.start.return_value = None
        mock_app.run.side_effect = KeyboardInterrupt()  # Simulate Ctrl+C
        mock_app.running = False
        
        # Should not raise exception
        main()
        
        # Should have created app with config path
        mock_app_class.assert_called_once_with(config_path='test_config.yaml')
        mock_app.initialize.assert_called_once()
        mock_app.start.assert_called_once()
        mock_app.run.assert_called_once()
    
    @patch('sys.argv', ['main.py', '--version'])
    def test_main_with_version_argument(self):
        """Test main function with version argument."""
        with self.assertRaises(SystemExit):
            main()
    
    @patch('sys.argv', ['main.py'])
    @patch('src.kafka_self_healing.main.KafkaSelfHealingApp')
    def test_main_without_arguments(self, mock_app_class):
        """Test main function without arguments."""
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        
        # Mock app to avoid actual execution
        mock_app.initialize.return_value = None
        mock_app.start.return_value = None
        mock_app.run.side_effect = KeyboardInterrupt()
        mock_app.running = False
        
        main()
        
        # Should have created app without config path
        mock_app_class.assert_called_once_with(config_path=None)
    
    @patch('sys.argv', ['main.py'])
    @patch('src.kafka_self_healing.main.KafkaSelfHealingApp')
    def test_main_with_initialization_error(self, mock_app_class):
        """Test main function with initialization error."""
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        mock_app.initialize.side_effect = ValidationError("Config error")
        
        with self.assertRaises(SystemExit):
            main()
    
    @patch('sys.argv', ['main.py'])
    @patch('src.kafka_self_healing.main.KafkaSelfHealingApp')
    def test_main_with_runtime_error(self, mock_app_class):
        """Test main function with runtime error."""
        mock_app = Mock()
        mock_app_class.return_value = mock_app
        mock_app.initialize.return_value = None
        mock_app.start.return_value = None
        mock_app.run.side_effect = Exception("Runtime error")
        mock_app.running = True
        
        with self.assertRaises(SystemExit):
            main()
        
        # Should have called stop on error
        mock_app.stop.assert_called_once()


class TestApplicationIntegration(unittest.TestCase):
    """Integration tests for complete application workflows."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "integration_config.yaml"
        
        # Create a comprehensive test configuration
        config_content = """
cluster:
  cluster_name: "integration-test-cluster"
  nodes:
    - node_id: "kafka-1"
      node_type: "kafka_broker"
      host: "localhost"
      port: 9092
      jmx_port: 9999
      monitoring_methods: ["socket", "jmx"]
      recovery_actions: ["service_restart"]
    - node_id: "zk-1"
      node_type: "zookeeper"
      host: "localhost"
      port: 2181
      monitoring_methods: ["socket", "zookeeper"]
      recovery_actions: ["service_restart"]
  monitoring_interval_seconds: 5
  default_retry_policy:
    max_attempts: 2
    initial_delay_seconds: 1
    backoff_multiplier: 2.0
    max_delay_seconds: 10

notification:
  smtp_host: "localhost"
  smtp_port: 587
  smtp_username: "test@example.com"
  smtp_password: "password"
  sender_email: "test@example.com"
  recipients: ["admin@example.com"]
  subject_prefix: "[Integration Test]"

logging:
  log_dir: "{temp_dir}/logs"
  log_level: "DEBUG"
  console_logging: false
  structured_format: true
""".format(temp_dir=self.temp_dir)
        
        with open(self.config_file, 'w') as f:
            f.write(config_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_complete_monitoring_recovery_notification_flow(self):
        """Test complete flow from monitoring failure to notification."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        try:
            # Mock monitoring plugin to simulate failure
            with patch.object(app.monitoring_service.health_checker._monitoring_plugins['socket'], 
                            'check_health', return_value=False):
                
                # Mock recovery engine to simulate recovery failure
                with patch.object(app.recovery_engine, 'execute_recovery') as mock_recovery:
                    mock_recovery.side_effect = Exception("Recovery failed")
                    
                    # Mock notification service to capture notifications
                    with patch.object(app.notification_service, 'send_failure_alert') as mock_notify:
                        
                        # Trigger a single monitoring check
                        app.monitoring_service.check_all_nodes_once()
                        
                        # Give some time for callbacks to execute
                        time.sleep(0.1)
                        
                        # Should have attempted recovery
                        mock_recovery.assert_called()
                        
                        # Should have sent failure notification
                        mock_notify.assert_called()
        
        finally:
            app.stop()
    
    def test_monitoring_recovery_success_flow(self):
        """Test flow from monitoring failure to successful recovery."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        try:
            # Mock monitoring plugin to simulate failure then recovery
            health_results = [False, True]  # First unhealthy, then healthy
            health_iter = iter(health_results)
            
            def mock_health_check(*args, **kwargs):
                return next(health_iter)
            
            with patch.object(app.monitoring_service.health_checker._monitoring_plugins['socket'], 
                            'check_health', side_effect=mock_health_check):
                
                # Mock recovery engine to simulate successful recovery
                from src.kafka_self_healing.models import RecoveryResult
                from datetime import datetime
                
                mock_result = RecoveryResult(
                    node_id="kafka-1",
                    action_type="service_restart",
                    command_executed="systemctl restart kafka",
                    exit_code=0,
                    stdout="Service restarted",
                    stderr="",
                    execution_time=datetime.now(),
                    success=True
                )
                
                with patch.object(app.recovery_engine, 'execute_recovery', return_value=mock_result):
                    
                    # Mock notification service to capture recovery confirmation
                    with patch.object(app.notification_service, 'send_recovery_confirmation') as mock_notify:
                        
                        # First check - should detect failure and trigger recovery
                        app.monitoring_service.check_all_nodes_once()
                        time.sleep(0.1)
                        
                        # Second check - should detect recovery
                        app.monitoring_service.check_all_nodes_once()
                        time.sleep(0.1)
                        
                        # Should have sent recovery confirmation
                        mock_notify.assert_called()
        
        finally:
            app.stop()
    
    def test_system_resilience_with_component_failures(self):
        """Test system resilience when individual components fail."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        try:
            # Simulate notification service failure
            with patch.object(app.notification_service, 'send_failure_alert', 
                            side_effect=Exception("SMTP error")):
                
                # System should continue operating despite notification failure
                status = app.get_system_status()
                self.assertTrue(status['running'])
                
                # Monitoring should still work
                app.monitoring_service.check_all_nodes_once()
                
                # System should still be running
                self.assertTrue(app.running)
        
        finally:
            app.stop()
    
    def test_graceful_shutdown_during_operations(self):
        """Test graceful shutdown while operations are in progress."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        # Start a background thread to simulate ongoing operations
        def background_operations():
            for _ in range(10):
                if not app.running:
                    break
                app.monitoring_service.check_all_nodes_once()
                time.sleep(0.1)
        
        bg_thread = threading.Thread(target=background_operations)
        bg_thread.start()
        
        # Let operations run briefly
        time.sleep(0.2)
        
        # Shutdown should complete gracefully
        start_time = time.time()
        app.stop()
        shutdown_time = time.time() - start_time
        
        # Should shutdown quickly
        self.assertLess(shutdown_time, 2.0)
        
        bg_thread.join(timeout=1.0)
        self.assertFalse(app.running)


if __name__ == '__main__':
    unittest.main()