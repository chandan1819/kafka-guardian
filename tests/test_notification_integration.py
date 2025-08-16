"""
Integration tests for notification system integration.

Tests notification triggering for escalation scenarios and recovery confirmations.
"""

import time
import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.main import KafkaSelfHealingApp
from src.kafka_self_healing.integration import (
    MonitoringRecoveryIntegrator,
    FailureEvent,
    RecoveryEvent,
    FailureType
)
from src.kafka_self_healing.models import NodeConfig, NodeStatus, RecoveryResult
from src.kafka_self_healing.notification import NotificationService


class TestNotificationIntegration(unittest.TestCase):
    """Test cases for notification system integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create test node configuration
        self.node_config = NodeConfig(
            node_id="test-kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["service_restart"]
        )
        
        # Create test failure event
        self.failure_event = FailureEvent(
            node_config=self.node_config,
            node_status=NodeStatus(
                node_id="test-kafka-1",
                is_healthy=False,
                last_check_time=datetime.now(),
                response_time_ms=5000.0,
                error_message="Service unavailable",
                monitoring_method="socket"
            ),
            failure_type=FailureType.SERVICE_UNAVAILABLE
        )
        
        # Create test recovery result
        self.recovery_result = RecoveryResult(
            node_id="test-kafka-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
    
    def test_escalation_notification_callback(self):
        """Test that escalation triggers failure alert notification."""
        # Mock notification service
        mock_notification_service = Mock(spec=NotificationService)
        
        # Mock cluster config
        mock_cluster_config = Mock()
        mock_cluster_config.get_node_by_id.return_value = self.node_config
        
        # Mock config manager
        mock_config_manager = Mock()
        mock_config_manager.get_cluster_config.return_value = mock_cluster_config
        
        # Create the escalation callback (similar to what's in main.py)
        def on_recovery_escalation(node_id, recovery_history):
            """Handle recovery escalation by sending notifications."""
            try:
                node = mock_cluster_config.get_node_by_id(node_id)
                if node and recovery_history:
                    last_error = recovery_history[-1].stderr if recovery_history[-1].stderr else "Unknown error"
                    mock_notification_service.send_failure_alert(node, recovery_history, last_error)
            except Exception as e:
                pass  # Would normally log error
        
        # Create failed recovery results
        failed_results = [
            RecoveryResult(
                node_id="test-kafka-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="",
                stderr="Service failed to restart",
                execution_time=datetime.now(),
                success=False
            )
        ]
        
        # Trigger escalation callback
        on_recovery_escalation("test-kafka-1", failed_results)
        
        # Verify notification was sent
        mock_notification_service.send_failure_alert.assert_called_once()
        call_args = mock_notification_service.send_failure_alert.call_args
        self.assertEqual(call_args[0][0], self.node_config)  # node config
        self.assertEqual(call_args[0][1], failed_results)    # recovery history
        self.assertEqual(call_args[0][2], "Service failed to restart")  # error message
    
    def test_recovery_success_notification_callback(self):
        """Test that successful recovery triggers confirmation notification."""
        # Mock notification service
        mock_notification_service = Mock(spec=NotificationService)
        
        # Mock recovery engine
        mock_recovery_engine = Mock()
        mock_recovery_engine.get_recovery_history.return_value = [
            RecoveryResult(
                node_id="test-kafka-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="",
                stderr="First attempt failed",
                execution_time=datetime.now(),
                success=False
            ),
            self.recovery_result  # Successful result
        ]
        
        # Create recovery event
        recovery_event = RecoveryEvent(
            node_config=self.node_config,
            recovery_result=self.recovery_result,
            failure_event=self.failure_event
        )
        
        # Create the recovery success callback (similar to what's in main.py)
        def on_recovery_success(recovery_event):
            """Handle successful recovery by sending confirmation."""
            try:
                node_config = recovery_event.node_config
                successful_action = recovery_event.recovery_result
                
                # Get failed attempts from recovery history
                recovery_history = mock_recovery_engine.get_recovery_history(node_config.node_id)
                failed_attempts = [r for r in recovery_history[:-1] if not r.success]
                
                # Calculate downtime duration
                failure_time = recovery_event.failure_event.timestamp
                recovery_time = recovery_event.timestamp
                downtime = recovery_time - failure_time
                downtime_str = f"{int(downtime.total_seconds())} seconds"
                
                mock_notification_service.send_recovery_confirmation(
                    node_config, successful_action, downtime_str, failed_attempts
                )
            except Exception as e:
                pass  # Would normally log error
        
        # Trigger recovery success callback
        on_recovery_success(recovery_event)
        
        # Verify notification was sent
        mock_notification_service.send_recovery_confirmation.assert_called_once()
        call_args = mock_notification_service.send_recovery_confirmation.call_args
        self.assertEqual(call_args[0][0], self.node_config)  # node config
        self.assertEqual(call_args[0][1], self.recovery_result)  # successful action
        self.assertIn("seconds", call_args[0][2])  # downtime string
        self.assertEqual(len(call_args[0][3]), 1)  # failed attempts
    
    def test_integration_with_monitoring_recovery_integrator(self):
        """Test notification integration with MonitoringRecoveryIntegrator."""
        # Mock services
        mock_monitoring = Mock()
        mock_recovery = Mock()
        mock_notification = Mock(spec=NotificationService)
        
        # Create integrator
        integrator = MonitoringRecoveryIntegrator(mock_monitoring, mock_recovery)
        
        # Track notification calls
        escalation_calls = []
        recovery_calls = []
        
        def mock_escalation_callback(node_id, recovery_history):
            escalation_calls.append((node_id, recovery_history))
            # Simulate sending notification
            mock_notification.send_failure_alert(self.node_config, recovery_history, "Test error")
        
        def mock_recovery_callback(recovery_event):
            recovery_calls.append(recovery_event)
            # Simulate sending notification
            mock_notification.send_recovery_confirmation(
                recovery_event.node_config,
                recovery_event.recovery_result,
                "30 seconds",
                []
            )
        
        # Register callbacks
        integrator.register_escalation_callback(mock_escalation_callback)
        integrator.register_recovery_callback(mock_recovery_callback)
        
        # Simulate escalation
        failed_results = [Mock()]
        integrator._handle_recovery_escalation("test-kafka-1", failed_results)
        
        # Verify escalation notification
        self.assertEqual(len(escalation_calls), 1)
        mock_notification.send_failure_alert.assert_called_once()
        
        # Simulate recovery success
        recovery_event = RecoveryEvent(
            node_config=self.node_config,
            recovery_result=self.recovery_result,
            failure_event=self.failure_event
        )
        
        # Manually trigger recovery callback
        for callback in integrator.recovery_callbacks:
            callback(recovery_event)
        
        # Verify recovery notification
        self.assertEqual(len(recovery_calls), 1)
        mock_notification.send_recovery_confirmation.assert_called_once()
    
    def test_notification_content_generation(self):
        """Test that notification content is properly generated."""
        from src.kafka_self_healing.notification import NotificationTemplate
        
        template_engine = NotificationTemplate()
        
        # Test failure alert content
        recovery_history = [
            RecoveryResult(
                node_id="test-kafka-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="",
                stderr="Service failed to restart",
                execution_time=datetime.now(),
                success=False
            )
        ]
        
        failure_content = template_engine.render_failure_alert(
            self.node_config,
            recovery_history,
            "Service unavailable",
            "[Test]"
        )
        
        # Verify content structure
        self.assertIn('subject', failure_content)
        self.assertIn('text', failure_content)
        self.assertIn('html', failure_content)
        
        # Verify content includes node information
        self.assertIn("test-kafka-1", failure_content['text'])
        self.assertIn("Service unavailable", failure_content['text'])
        self.assertIn("service_restart", failure_content['text'])
        
        # Test recovery confirmation content
        recovery_content = template_engine.render_recovery_confirmation(
            self.node_config,
            self.recovery_result,
            "30 seconds",
            "[Test]"
        )
        
        # Verify content structure
        self.assertIn('subject', recovery_content)
        self.assertIn('text', recovery_content)
        self.assertIn('html', recovery_content)
        
        # Verify content includes recovery information
        self.assertIn("test-kafka-1", recovery_content['text'])
        self.assertIn("30 seconds", recovery_content['text'])
        self.assertIn("service_restart", recovery_content['text'])
    
    def test_notification_delivery_queue_integration(self):
        """Test integration with notification delivery queue."""
        from src.kafka_self_healing.notification import DeliveryQueue, NotificationMessage
        from src.kafka_self_healing.models import NotificationConfig
        
        # Create notification config
        notification_config = NotificationConfig(
            smtp_host="localhost",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="password",
            sender_email="test@example.com",
            recipients=["admin@example.com"],
            subject_prefix="[Test]"
        )
        
        # Create notification service
        notification_service = NotificationService(notification_config)
        
        # Mock the delivery queue processing
        processed_messages = []
        
        def mock_process_message(message):
            processed_messages.append(message)
        
        notification_service.delivery_queue._process_message = mock_process_message
        
        # Start the service
        notification_service.start()
        
        try:
            # Send failure alert
            notification_id = notification_service.send_failure_alert(
                self.node_config,
                [Mock()],
                "Test error"
            )
            
            # Give time for queue processing
            time.sleep(0.1)
            
            # Verify message was queued
            self.assertIsNotNone(notification_id)
            
            # Send recovery confirmation
            notification_id2 = notification_service.send_recovery_confirmation(
                self.node_config,
                self.recovery_result,
                "30 seconds"
            )
            
            # Give time for queue processing
            time.sleep(0.1)
            
            # Verify second message was queued
            self.assertIsNotNone(notification_id2)
            self.assertNotEqual(notification_id, notification_id2)
            
        finally:
            notification_service.stop()
    
    def test_notification_error_handling(self):
        """Test notification error handling and resilience."""
        # Mock notification service that fails
        mock_notification = Mock(spec=NotificationService)
        mock_notification.send_failure_alert.side_effect = Exception("SMTP error")
        mock_notification.send_recovery_confirmation.side_effect = Exception("SMTP error")
        
        # Create callbacks that handle errors gracefully
        def safe_escalation_callback(node_id, recovery_history):
            try:
                mock_notification.send_failure_alert(self.node_config, recovery_history, "Test error")
            except Exception:
                # Should handle error gracefully
                pass
        
        def safe_recovery_callback(recovery_event):
            try:
                mock_notification.send_recovery_confirmation(
                    recovery_event.node_config,
                    recovery_event.recovery_result,
                    "30 seconds",
                    []
                )
            except Exception:
                # Should handle error gracefully
                pass
        
        # Test that callbacks don't crash on notification errors
        safe_escalation_callback("test-kafka-1", [Mock()])
        safe_recovery_callback(RecoveryEvent(
            node_config=self.node_config,
            recovery_result=self.recovery_result,
            failure_event=self.failure_event
        ))
        
        # Verify notification methods were called despite errors
        mock_notification.send_failure_alert.assert_called_once()
        mock_notification.send_recovery_confirmation.assert_called_once()


class TestEndToEndNotificationFlow(unittest.TestCase):
    """End-to-end tests for complete notification workflows."""
    
    def setUp(self):
        """Set up test fixtures."""
        import tempfile
        from pathlib import Path
        
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "test_config.yaml"
        
        # Create test configuration
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
  subject_prefix: "[Test]"

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
    
    def test_complete_notification_workflow(self):
        """Test complete notification workflow from failure to recovery."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Track notifications
        failure_notifications = []
        recovery_notifications = []
        
        def mock_send_failure_alert(*args, **kwargs):
            failure_notifications.append(args)
            return "failure-123"
        
        def mock_send_recovery_confirmation(*args, **kwargs):
            recovery_notifications.append(args)
            return "recovery-123"
        
        # Mock notification service methods
        app.notification_service.send_failure_alert = mock_send_failure_alert
        app.notification_service.send_recovery_confirmation = mock_send_recovery_confirmation
        
        # Get the node config
        cluster_config = app.config_manager.get_cluster_config()
        node_config = cluster_config.nodes[0]
        
        # Simulate escalation scenario
        failed_results = [
            RecoveryResult(
                node_id="kafka-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="",
                stderr="Service failed to restart",
                execution_time=datetime.now(),
                success=False
            )
        ]
        
        # Trigger escalation through integrator
        for callback in app.integrator.escalation_callbacks:
            callback("kafka-1", failed_results)
        
        # Verify failure notification was sent
        self.assertEqual(len(failure_notifications), 1)
        self.assertEqual(failure_notifications[0][0].node_id, "kafka-1")
        self.assertEqual(failure_notifications[0][1], failed_results)
        
        # Simulate recovery scenario
        successful_result = RecoveryResult(
            node_id="kafka-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        
        recovery_event = RecoveryEvent(
            node_config=node_config,
            recovery_result=successful_result,
            failure_event=FailureEvent(
                node_config=node_config,
                node_status=NodeStatus(
                    node_id="kafka-1",
                    is_healthy=False,
                    last_check_time=datetime.now(),
                    response_time_ms=5000.0,
                    error_message="Service unavailable",
                    monitoring_method="socket"
                ),
                failure_type=FailureType.SERVICE_UNAVAILABLE
            )
        )
        
        # Trigger recovery through integrator
        for callback in app.integrator.recovery_callbacks:
            callback(recovery_event)
        
        # Verify recovery notification was sent
        self.assertEqual(len(recovery_notifications), 1)
        self.assertEqual(recovery_notifications[0][0].node_id, "kafka-1")
        self.assertEqual(recovery_notifications[0][1], successful_result)
    
    def test_notification_integration_resilience(self):
        """Test that notification integration is resilient to failures."""
        app = KafkaSelfHealingApp(config_path=str(self.config_file))
        app.initialize()
        
        # Mock notification service to fail
        app.notification_service.send_failure_alert = Mock(side_effect=Exception("SMTP error"))
        app.notification_service.send_recovery_confirmation = Mock(side_effect=Exception("SMTP error"))
        
        # Get the node config
        cluster_config = app.config_manager.get_cluster_config()
        node_config = cluster_config.nodes[0]
        
        # Test that escalation callback handles notification errors gracefully
        failed_results = [Mock()]
        
        # This should not raise an exception
        for callback in app.integrator.escalation_callbacks:
            callback("kafka-1", failed_results)
        
        # Verify notification was attempted
        app.notification_service.send_failure_alert.assert_called_once()
        
        # Test that recovery callback handles notification errors gracefully
        recovery_event = RecoveryEvent(
            node_config=node_config,
            recovery_result=Mock(),
            failure_event=Mock()
        )
        
        # This should not raise an exception
        for callback in app.integrator.recovery_callbacks:
            callback(recovery_event)
        
        # Verify notification was attempted
        app.notification_service.send_recovery_confirmation.assert_called_once()


if __name__ == '__main__':
    unittest.main()