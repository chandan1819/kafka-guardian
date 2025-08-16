"""
Integration tests for system resilience and error handling.

Tests global exception handling, resource constraint handling,
graceful degradation, and system recovery scenarios.
"""

import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.main import KafkaSelfHealingApp
from src.kafka_self_healing.exceptions import SystemError


class TestSystemResilience(unittest.TestCase):
    """Test cases for system resilience features."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_config.yaml"
        
        # Create test configuration
        config_content = """
cluster:
  cluster_name: "resilience-test-cluster"
  nodes:
    - node_id: "kafka-1"
      node_type: "kafka_broker"
      host: "localhost"
      port: 9092
      monitoring_methods: ["socket"]
      recovery_actions: ["service_restart"]
  monitoring_interval_seconds: 10
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
  subject_prefix: "[Resilience Test]"

logging:
  log_dir: "{temp_dir}/logs"
  log_level: "INFO"
  console_logging: false
""".format(temp_dir=self.temp_dir)
        
        with open(self.config_file, 'w') as f:
            f.write(config_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_global_exception_handling(self):
        """Test global exception handler setup and error tracking."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Setup global exception handler
        app._setup_global_exception_handler()
        
        # Verify initial state
        self.assertEqual(app._error_count, 0)
        self.assertIsNone(app._last_error_time)
        
        # Simulate unhandled exception
        original_excepthook = app.logger.critical
        critical_calls = []
        
        def mock_critical(*args, **kwargs):
            critical_calls.append((args, kwargs))
        
        app.logger.critical = mock_critical
        
        # Trigger exception handler
        import sys
        try:
            sys.excepthook(ValueError, ValueError("Test error"), None)
        except:
            pass
        
        # Verify error was tracked
        self.assertEqual(app._error_count, 1)
        self.assertIsNotNone(app._last_error_time)
        self.assertEqual(len(critical_calls), 1)
    
    def test_degraded_mode_entry_and_exit(self):
        """Test entering and exiting degraded mode."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Verify initial state
        self.assertFalse(app._degraded_mode)
        
        # Simulate conditions for degraded mode
        app._error_count = 4
        app._last_error_time = datetime.now()
        
        # Check degraded mode
        app._check_degraded_mode()
        
        # Should enter degraded mode
        self.assertTrue(app._degraded_mode)
        
        # Verify degraded mode changes
        if app.integrator:
            # Should have reduced concurrent recoveries
            self.assertEqual(app.integrator.max_concurrent_recoveries, 2)
        
        # Simulate recovery conditions
        app._error_count = 0
        app._last_error_time = None
        
        # Check degraded mode again
        app._check_degraded_mode()
        
        # Should exit degraded mode
        self.assertFalse(app._degraded_mode)
        
        # Verify normal mode restoration
        if app.integrator:
            self.assertEqual(app.integrator.max_concurrent_recoveries, 5)
    
    @patch('psutil.virtual_memory')
    def test_high_memory_usage_handling(self, mock_memory):
        """Test handling of high memory usage."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock high memory usage
        mock_memory_obj = Mock()
        mock_memory_obj.percent = 90.0  # Above threshold
        mock_memory.return_value = mock_memory_obj
        
        # Mock cleanup methods
        cleanup_called = False
        
        def mock_cleanup_logs(*args, **kwargs):
            nonlocal cleanup_called
            cleanup_called = True
        
        if app.logging_service:
            app.logging_service.cleanup_old_logs = mock_cleanup_logs
        
        # Trigger memory check
        app._check_resource_constraints()
        
        # Verify cleanup was called
        self.assertTrue(cleanup_called)
    
    @patch('psutil.disk_usage')
    def test_high_disk_usage_handling(self, mock_disk):
        """Test handling of high disk usage."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock high disk usage
        mock_disk_obj = Mock()
        mock_disk_obj.total = 1000000000  # 1GB
        mock_disk_obj.used = 950000000    # 95% used
        mock_disk_obj.free = 50000000     # 5% free
        mock_disk.return_value = mock_disk_obj
        
        # Mock cleanup methods
        cleanup_called = False
        
        def mock_cleanup_logs(*args, **kwargs):
            nonlocal cleanup_called
            cleanup_called = True
        
        if app.logging_service:
            app.logging_service.cleanup_old_logs = mock_cleanup_logs
        
        # Trigger disk check
        app._check_resource_constraints()
        
        # Verify cleanup was called
        self.assertTrue(cleanup_called)
    
    @patch('psutil.cpu_percent')
    def test_high_cpu_usage_handling(self, mock_cpu):
        """Test handling of high CPU usage."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock high CPU usage
        mock_cpu.return_value = 98.0  # Above threshold
        
        # Store original monitoring interval
        original_interval = app.monitoring_service.cluster_config.monitoring_interval_seconds
        
        # Trigger CPU check
        app._check_resource_constraints()
        
        # Verify monitoring interval was increased
        current_interval = app.monitoring_service.cluster_config.monitoring_interval_seconds
        self.assertGreater(current_interval, original_interval)
        
        # Verify concurrent recoveries were reduced
        if app.integrator:
            self.assertEqual(app.integrator.max_concurrent_recoveries, 1)
    
    def test_service_restart_resilience(self):
        """Test system resilience when services fail and restart."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        try:
            # Verify monitoring is active
            self.assertTrue(app.monitoring_service.is_monitoring_active())
            
            # Stop monitoring service
            app.monitoring_service.stop_monitoring()
            self.assertFalse(app.monitoring_service.is_monitoring_active())
            
            # Trigger health check (should attempt restart)
            app._check_system_health()
            
            # Give time for restart attempt
            time.sleep(0.1)
            
            # Monitoring should be restarted
            self.assertTrue(app.monitoring_service.is_monitoring_active())
            
        finally:
            app.stop()
    
    def test_component_failure_isolation(self):
        """Test that failure in one component doesn't crash the system."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        try:
            # Mock notification service to fail
            app.notification_service.send_failure_alert = Mock(side_effect=Exception("SMTP error"))
            
            # System should continue operating despite notification failure
            status = app.get_system_status()
            self.assertTrue(status['running'])
            
            # Trigger notification through integration (should not crash)
            if app.integrator:
                for callback in app.integrator.escalation_callbacks:
                    try:
                        callback("test-node", [Mock()])
                    except Exception:
                        pass  # Should be handled gracefully
            
            # System should still be operational
            status = app.get_system_status()
            self.assertTrue(status['running'])
            
        finally:
            app.stop()
    
    def test_resource_status_reporting(self):
        """Test resource status reporting functionality."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Get resource status
        resource_status = app._get_resource_status()
        
        # Verify structure
        self.assertIn('memory', resource_status)
        self.assertIn('disk', resource_status)
        self.assertIn('cpu', resource_status)
        
        # Verify memory status
        memory_status = resource_status['memory']
        self.assertIn('percent', memory_status)
        self.assertIn('available_gb', memory_status)
        self.assertIn('threshold_percent', memory_status)
        self.assertIn('status', memory_status)
        
        # Verify disk status
        disk_status = resource_status['disk']
        self.assertIn('percent', disk_status)
        self.assertIn('free_gb', disk_status)
        self.assertIn('threshold_percent', disk_status)
        self.assertIn('status', disk_status)
        
        # Verify CPU status
        cpu_status = resource_status['cpu']
        self.assertIn('percent', cpu_status)
        self.assertIn('threshold_percent', cpu_status)
        self.assertIn('status', cpu_status)
    
    def test_system_status_with_resilience_info(self):
        """Test that system status includes resilience information."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Set some error state
        app._error_count = 2
        app._last_error_time = datetime.now()
        app._degraded_mode = True
        
        # Get system status
        status = app.get_system_status()
        
        # Verify resilience information is included
        self.assertIn('degraded_mode', status)
        self.assertIn('error_count', status)
        self.assertIn('last_error_time', status)
        self.assertIn('resources', status)
        
        # Verify values
        self.assertTrue(status['degraded_mode'])
        self.assertEqual(status['error_count'], 2)
        self.assertIsNotNone(status['last_error_time'])
    
    def test_graceful_shutdown_with_active_operations(self):
        """Test graceful shutdown while operations are in progress."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        # Start background operations
        operation_running = True
        
        def background_operation():
            while operation_running and app.running:
                try:
                    app.monitoring_service.check_all_nodes_once()
                    time.sleep(0.1)
                except Exception:
                    break
        
        bg_thread = threading.Thread(target=background_operation)
        bg_thread.start()
        
        # Let operations run briefly
        time.sleep(0.2)
        
        # Shutdown should complete gracefully
        start_time = time.time()
        app.stop()
        shutdown_time = time.time() - start_time
        
        # Should shutdown quickly
        self.assertLess(shutdown_time, 3.0)
        
        # Stop background operation
        operation_running = False
        bg_thread.join(timeout=1.0)
        
        self.assertFalse(app.running)
    
    def test_error_recovery_after_degraded_mode(self):
        """Test system recovery after being in degraded mode."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Force degraded mode
        app._enter_degraded_mode()
        self.assertTrue(app._degraded_mode)
        
        # Verify degraded state
        if app.integrator:
            self.assertEqual(app.integrator.max_concurrent_recoveries, 2)
        
        # Force exit from degraded mode
        app._exit_degraded_mode()
        self.assertFalse(app._degraded_mode)
        
        # Verify normal state restored
        if app.integrator:
            self.assertEqual(app.integrator.max_concurrent_recoveries, 5)
        
        # Error count should be reset
        self.assertEqual(app._error_count, 0)
        self.assertIsNone(app._last_error_time)


class TestSystemMonitoring(unittest.TestCase):
    """Test cases for system monitoring threads."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_config.yaml"
        
        # Create minimal test configuration
        config_content = """
cluster:
  cluster_name: "monitor-test-cluster"
  nodes:
    - node_id: "kafka-1"
      node_type: "kafka_broker"
      host: "localhost"
      port: 9092
      monitoring_methods: ["socket"]
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
  subject_prefix: "[Monitor Test]"
"""
        
        with open(self.config_file, 'w') as f:
            f.write(config_content)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_system_monitoring_threads_start_and_stop(self):
        """Test that system monitoring threads start and stop properly."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        app.start()
        
        try:
            # Verify monitoring threads are started
            self.assertIsNotNone(app._health_check_thread)
            self.assertIsNotNone(app._resource_monitor_thread)
            self.assertTrue(app._health_check_thread.is_alive())
            self.assertTrue(app._resource_monitor_thread.is_alive())
            
        finally:
            app.stop()
            
            # Verify threads are stopped
            if app._health_check_thread:
                app._health_check_thread.join(timeout=1)
                self.assertFalse(app._health_check_thread.is_alive())
            
            if app._resource_monitor_thread:
                app._resource_monitor_thread.join(timeout=1)
                self.assertFalse(app._resource_monitor_thread.is_alive())
    
    def test_health_monitor_detects_issues(self):
        """Test that health monitor detects and reports issues."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock logger to capture warnings
        warnings = []
        
        def mock_warning(msg, *args):
            warnings.append(msg % args if args else msg)
        
        app.logger.warning = mock_warning
        
        # Stop monitoring to create a health issue
        app.monitoring_service.stop_monitoring()
        
        # Run health check
        app._check_system_health()
        
        # Should detect monitoring service issue
        health_issues = [w for w in warnings if "Health issue" in w]
        self.assertGreater(len(health_issues), 0)
    
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_usage')
    @patch('psutil.cpu_percent')
    def test_resource_monitor_detects_constraints(self, mock_cpu, mock_disk, mock_memory):
        """Test that resource monitor detects resource constraints."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock high resource usage
        mock_memory_obj = Mock()
        mock_memory_obj.percent = 90.0
        mock_memory.return_value = mock_memory_obj
        
        mock_disk_obj = Mock()
        mock_disk_obj.total = 1000000000
        mock_disk_obj.used = 950000000
        mock_disk_obj.free = 50000000
        mock_disk.return_value = mock_disk_obj
        
        mock_cpu.return_value = 98.0
        
        # Mock logger to capture warnings
        warnings = []
        
        def mock_warning(msg, *args):
            warnings.append(msg % args if args else msg)
        
        app.logger.warning = mock_warning
        
        # Run resource check
        app._check_resource_constraints()
        
        # Should detect all resource issues
        memory_warnings = [w for w in warnings if "High memory usage" in w]
        disk_warnings = [w for w in warnings if "High disk usage" in w]
        cpu_warnings = [w for w in warnings if "High CPU usage" in w]
        
        self.assertGreater(len(memory_warnings), 0)
        self.assertGreater(len(disk_warnings), 0)
        self.assertGreater(len(cpu_warnings), 0)


if __name__ == '__main__':
    unittest.main()