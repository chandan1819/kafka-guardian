"""
Unit tests for the notification system.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import threading
import time
import queue

from src.kafka_self_healing.notification import (
    NotificationService, NotificationTemplate, DeliveryQueue,
    NotificationMessage, NotificationResult, Notifier, EmailNotifier
)
from src.kafka_self_healing.models import NodeConfig, RecoveryResult, NotificationConfig, RetryPolicy
from src.kafka_self_healing.exceptions import NotificationError


class TestNotificationResult(unittest.TestCase):
    """Test NotificationResult data model."""

    def test_notification_result_creation(self):
        """Test creating a notification result."""
        result = NotificationResult(
            notification_id="test_001",
            recipient="admin@example.com",
            delivery_time=datetime.now(),
            success=True,
            retry_count=1
        )
        
        self.assertEqual(result.notification_id, "test_001")
        self.assertEqual(result.recipient, "admin@example.com")
        self.assertTrue(result.success)
        self.assertEqual(result.retry_count, 1)
        self.assertIsNone(result.error_message)

    def test_notification_result_to_dict(self):
        """Test converting notification result to dictionary."""
        delivery_time = datetime.now()
        result = NotificationResult(
            notification_id="test_001",
            recipient="admin@example.com",
            delivery_time=delivery_time,
            success=False,
            error_message="SMTP connection failed",
            retry_count=2
        )
        
        result_dict = result.to_dict()
        
        self.assertEqual(result_dict['notification_id'], "test_001")
        self.assertEqual(result_dict['recipient'], "admin@example.com")
        self.assertEqual(result_dict['delivery_time'], delivery_time.isoformat())
        self.assertFalse(result_dict['success'])
        self.assertEqual(result_dict['error_message'], "SMTP connection failed")
        self.assertEqual(result_dict['retry_count'], 2)


class TestNotificationMessage(unittest.TestCase):
    """Test NotificationMessage data model."""

    def test_notification_message_creation(self):
        """Test creating a notification message."""
        message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )
        
        self.assertEqual(message.notification_id, "test_001")
        self.assertEqual(message.notification_type, "failure_alert")
        self.assertEqual(message.recipients, ["admin@example.com"])
        self.assertEqual(message.subject, "Test Alert")
        self.assertEqual(message.body_text, "Test message body")
        self.assertEqual(message.retry_count, 0)
        self.assertEqual(message.max_retries, 3)

    def test_should_retry_logic(self):
        """Test retry logic for notification messages."""
        message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body",
            max_retries=2
        )
        
        # Should retry initially
        self.assertTrue(message.should_retry())
        
        # Should retry after first attempt
        message.retry_count = 1
        self.assertTrue(message.should_retry())
        
        # Should not retry after max attempts
        message.retry_count = 2
        self.assertFalse(message.should_retry())

    def test_schedule_retry(self):
        """Test scheduling retry attempts."""
        message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )
        
        # Schedule retry
        before_time = datetime.now()
        message.schedule_retry(60)
        after_time = datetime.now()
        
        self.assertEqual(message.retry_count, 1)
        self.assertIsNotNone(message.next_retry_time)
        self.assertGreater(message.next_retry_time, before_time + timedelta(seconds=59))
        self.assertLess(message.next_retry_time, after_time + timedelta(seconds=61))

    def test_should_retry_with_scheduled_time(self):
        """Test retry logic with scheduled retry time."""
        message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )
        
        # Schedule retry in the future
        message.next_retry_time = datetime.now() + timedelta(seconds=60)
        self.assertFalse(message.should_retry())
        
        # Schedule retry in the past
        message.next_retry_time = datetime.now() - timedelta(seconds=60)
        self.assertTrue(message.should_retry())


class TestNotificationTemplate(unittest.TestCase):
    """Test NotificationTemplate functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.template_engine = NotificationTemplate()
        self.node = NodeConfig(
            node_id="kafka-broker-1",
            node_type="kafka_broker",
            host="kafka1.example.com",
            port=9092,
            jmx_port=9999
        )
        self.recovery_result = RecoveryResult(
            node_id="kafka-broker-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )

    def test_render_failure_alert(self):
        """Test rendering failure alert notification."""
        recovery_history = [
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="",
                stderr="Service failed to restart",
                execution_time=datetime.now(),
                success=False
            )
        ]
        
        content = self.template_engine.render_failure_alert(
            self.node, recovery_history, "Connection timeout", "[Test]"
        )
        
        self.assertIn("subject", content)
        self.assertIn("text", content)
        self.assertIn("html", content)
        
        # Check subject
        self.assertIn("[Test]", content["subject"])
        self.assertIn("kafka-broker-1", content["subject"])
        
        # Check text content
        self.assertIn("kafka-broker-1", content["text"])
        self.assertIn("kafka1.example.com", content["text"])
        self.assertIn("Port: 9092", content["text"])
        self.assertIn("Connection timeout", content["text"])
        self.assertIn("service_restart", content["text"])
        self.assertIn("FAILED", content["text"])
        self.assertIn("systemctl restart kafka", content["text"])
        self.assertIn("Service failed to restart", content["text"])
        
        # Check HTML content
        self.assertIn("<html>", content["html"])
        self.assertIn("kafka-broker-1", content["html"])
        self.assertIn("kafka1.example.com", content["html"])
        self.assertIn("Connection timeout", content["html"])
        self.assertIn("recovery-attempt", content["html"])

    def test_render_failure_alert_no_recovery_history(self):
        """Test rendering failure alert with no recovery history."""
        content = self.template_engine.render_failure_alert(
            self.node, [], "Connection timeout", "[Test]"
        )
        
        self.assertIn("No recovery attempts made", content["text"])
        self.assertIn("No recovery attempts made", content["html"])

    def test_render_recovery_confirmation(self):
        """Test rendering recovery confirmation notification."""
        content = self.template_engine.render_recovery_confirmation(
            self.node, self.recovery_result, "5 minutes", "[Test]"
        )
        
        self.assertIn("subject", content)
        self.assertIn("text", content)
        self.assertIn("html", content)
        
        # Check subject
        self.assertIn("[Test]", content["subject"])
        self.assertIn("Recovery Success", content["subject"])
        self.assertIn("kafka-broker-1", content["subject"])
        
        # Check text content
        self.assertIn("kafka-broker-1", content["text"])
        self.assertIn("RECOVERED", content["text"])
        self.assertIn("5 minutes", content["text"])
        self.assertIn("service_restart", content["text"])
        self.assertIn("systemctl restart kafka", content["text"])
        
        # Check HTML content
        self.assertIn("<html>", content["html"])
        self.assertIn("kafka-broker-1", content["html"])
        self.assertIn("RECOVERED", content["html"])
        self.assertIn("5 minutes", content["html"])

    def test_custom_templates(self):
        """Test using custom templates."""
        custom_templates = {
            'failure_alert_subject': 'CUSTOM: $node_id failed'
        }
        
        template_engine = NotificationTemplate(custom_templates)
        content = template_engine.render_failure_alert(
            self.node, [], "Connection timeout", "[Test]"
        )
        
        self.assertEqual(content["subject"], "CUSTOM: kafka-broker-1 failed")

    def test_render_failure_alert_with_log_excerpts(self):
        """Test rendering failure alert with log excerpts."""
        recovery_history = [
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="Attempting restart...",
                stderr="Service failed to restart: Connection refused",
                execution_time=datetime.now(),
                success=False
            )
        ]
        
        log_excerpts = [
            "2023-01-01 10:00:00 ERROR: Connection to broker failed",
            "2023-01-01 10:00:01 WARN: Retrying connection...",
            "2023-01-01 10:00:02 ERROR: Max retries exceeded"
        ]
        
        last_success = datetime.now() - timedelta(minutes=30)
        
        content = self.template_engine.render_failure_alert(
            self.node, recovery_history, "Connection timeout", "[Test]",
            last_success, log_excerpts
        )
        
        # Check that log excerpts are included
        self.assertIn("Recent Log Excerpts", content["text"])
        self.assertIn("Connection to broker failed", content["text"])
        self.assertIn("Recent Log Excerpts", content["html"])
        self.assertIn("Connection to broker failed", content["html"])
        
        # Check that last success time is included
        self.assertIn(last_success.strftime('%Y-%m-%d %H:%M:%S'), content["text"])
        
        # Check detailed recovery information
        self.assertIn("Attempting restart...", content["text"])
        self.assertIn("Connection refused", content["text"])

    def test_render_recovery_confirmation_with_failed_attempts(self):
        """Test rendering recovery confirmation with failed attempts."""
        failed_attempts = [
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="",
                stderr="Service failed to restart",
                execution_time=datetime.now() - timedelta(minutes=5),
                success=False
            ),
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="process_kill",
                command_executed="pkill -f kafka",
                exit_code=1,
                stdout="",
                stderr="No matching processes found",
                execution_time=datetime.now() - timedelta(minutes=3),
                success=False
            )
        ]
        
        content = self.template_engine.render_recovery_confirmation(
            self.node, self.recovery_result, "8 minutes", "[Test]", failed_attempts
        )
        
        # Check that failed attempts are included
        self.assertIn("Previous Failed Attempts", content["text"])
        self.assertIn("service_restart", content["text"])
        self.assertIn("process_kill", content["text"])
        self.assertIn("Service failed to restart", content["text"])
        self.assertIn("No matching processes found", content["text"])
        
        # Check HTML version
        self.assertIn("Previous Failed Attempts", content["html"])
        self.assertIn("failed-attempt", content["html"])
        
        # Check total attempts count
        self.assertIn("Total Recovery Attempts: 3", content["text"])

    def test_render_failure_alert_multiple_recovery_attempts(self):
        """Test rendering failure alert with multiple recovery attempts."""
        recovery_history = [
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="service_restart",
                command_executed="systemctl restart kafka",
                exit_code=1,
                stdout="Starting service...",
                stderr="Service failed to start: Port already in use",
                execution_time=datetime.now() - timedelta(minutes=10),
                success=False
            ),
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="process_kill",
                command_executed="pkill -f kafka && systemctl start kafka",
                exit_code=1,
                stdout="Killed process 1234",
                stderr="Service still failed to start",
                execution_time=datetime.now() - timedelta(minutes=5),
                success=False
            ),
            RecoveryResult(
                node_id="kafka-broker-1",
                action_type="script_execution",
                command_executed="/opt/kafka/scripts/cleanup.sh",
                exit_code=1,
                stdout="Cleaning up temporary files...",
                stderr="Cleanup failed: Permission denied",
                execution_time=datetime.now() - timedelta(minutes=2),
                success=False
            )
        ]
        
        content = self.template_engine.render_failure_alert(
            self.node, recovery_history, "Multiple recovery failures", "[Test]"
        )
        
        # Check that all attempts are included with details
        self.assertIn("3 total", content["text"])
        self.assertIn("service_restart", content["text"])
        self.assertIn("process_kill", content["text"])
        self.assertIn("script_execution", content["text"])
        
        # Check specific error messages
        self.assertIn("Port already in use", content["text"])
        self.assertIn("Service still failed to start", content["text"])
        self.assertIn("Permission denied", content["text"])
        
        # Check HTML formatting
        self.assertIn("recovery-attempt", content["html"])
        self.assertIn("status-failed", content["html"])

    def test_render_templates_with_special_characters(self):
        """Test rendering templates with special characters in data."""
        # Create node with special characters
        node = NodeConfig(
            node_id="kafka-broker-test",
            node_type="kafka_broker",
            host="test.example.com",
            port=9092
        )
        
        recovery_result = RecoveryResult(
            node_id="kafka-broker-test",
            action_type="script_execution",
            command_executed="echo 'test with \"quotes\" and $variables'",
            exit_code=0,
            stdout="Output with <html> tags and & symbols",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        
        # Test failure alert
        content = self.template_engine.render_failure_alert(
            node, [recovery_result], "Error with <script>alert('xss')</script>", "[Test]"
        )
        
        # Should handle special characters safely
        self.assertIn("quotes", content["text"])
        self.assertIn("variables", content["text"])
        self.assertIn("html", content["text"])
        self.assertIn("script", content["text"])
        
        # Test recovery confirmation
        content = self.template_engine.render_recovery_confirmation(
            node, recovery_result, "2 minutes", "[Test]"
        )
        
        self.assertIn("quotes", content["text"])
        self.assertIn("html", content["text"])


class TestDeliveryQueue(unittest.TestCase):
    """Test DeliveryQueue functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.delivery_queue = DeliveryQueue(max_queue_size=10)
        self.test_message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.delivery_queue.running:
            self.delivery_queue.stop()

    def test_queue_initialization(self):
        """Test delivery queue initialization."""
        self.assertFalse(self.delivery_queue.running)
        self.assertIsNone(self.delivery_queue.worker_thread)
        self.assertIsNone(self.delivery_queue.retry_thread)

    def test_start_stop_queue(self):
        """Test starting and stopping the delivery queue."""
        # Start queue
        self.delivery_queue.start()
        self.assertTrue(self.delivery_queue.running)
        self.assertIsNotNone(self.delivery_queue.worker_thread)
        self.assertIsNotNone(self.delivery_queue.retry_thread)
        self.assertTrue(self.delivery_queue.worker_thread.is_alive())
        self.assertTrue(self.delivery_queue.retry_thread.is_alive())
        
        # Stop queue
        self.delivery_queue.stop()
        self.assertFalse(self.delivery_queue.running)

    def test_enqueue_message(self):
        """Test enqueueing messages."""
        # Should succeed with empty queue
        self.assertTrue(self.delivery_queue.enqueue(self.test_message))
        self.assertEqual(self.delivery_queue.queue.qsize(), 1)
        
        # Fill up the queue
        for i in range(9):  # Queue size is 10, already has 1
            message = NotificationMessage(
                notification_id=f"test_{i:03d}",
                notification_type="failure_alert",
                recipients=["admin@example.com"],
                subject="Test Alert",
                body_text="Test message body"
            )
            self.assertTrue(self.delivery_queue.enqueue(message))
        
        # Should fail when queue is full
        overflow_message = NotificationMessage(
            notification_id="overflow",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )
        self.assertFalse(self.delivery_queue.enqueue(overflow_message))

    def test_enqueue_retry(self):
        """Test enqueueing retry messages."""
        self.assertTrue(self.delivery_queue.enqueue_retry(self.test_message))
        self.assertEqual(self.delivery_queue.retry_queue.qsize(), 1)

    def test_get_queue_sizes(self):
        """Test getting queue sizes."""
        sizes = self.delivery_queue.get_queue_sizes()
        self.assertEqual(sizes['delivery_queue'], 0)
        self.assertEqual(sizes['retry_queue'], 0)
        
        # Add messages
        self.delivery_queue.enqueue(self.test_message)
        self.delivery_queue.enqueue_retry(self.test_message)
        
        sizes = self.delivery_queue.get_queue_sizes()
        self.assertEqual(sizes['delivery_queue'], 1)
        self.assertEqual(sizes['retry_queue'], 1)


class MockNotifier(Notifier):
    """Mock notifier for testing."""

    def __init__(self, should_succeed: bool = True, delay: float = 0):
        self.should_succeed = should_succeed
        self.delay = delay
        self.sent_messages = []
        self.connection_test_result = True

    def send(self, message: NotificationMessage) -> NotificationResult:
        """Mock send implementation."""
        if self.delay > 0:
            time.sleep(self.delay)
        
        self.sent_messages.append(message)
        
        if self.should_succeed:
            return NotificationResult(
                notification_id=message.notification_id,
                recipient=message.recipients[0] if message.recipients else "unknown",
                delivery_time=datetime.now(),
                success=True
            )
        else:
            return NotificationResult(
                notification_id=message.notification_id,
                recipient=message.recipients[0] if message.recipients else "unknown",
                delivery_time=datetime.now(),
                success=False,
                error_message="Mock delivery failure"
            )

    def test_connection(self) -> bool:
        """Mock connection test."""
        return self.connection_test_result


class MockSMTP:
    """Mock SMTP server for testing."""
    
    def __init__(self, host, port, should_fail=False):
        self.host = host
        self.port = port
        self.should_fail = should_fail
        self.sent_messages = []
        self.authenticated = False
        self.tls_started = False
        
    def __enter__(self):
        if self.should_fail:
            raise Exception("SMTP connection failed")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
        
    def starttls(self, context=None):
        self.tls_started = True
        
    def login(self, username, password):
        self.authenticated = True
        
    def send_message(self, msg):
        if self.should_fail:
            raise Exception("Failed to send message")
        self.sent_messages.append(msg)
        
    def noop(self):
        if self.should_fail:
            raise Exception("NOOP failed")


class MockSMTPSSL(MockSMTP):
    """Mock SMTP SSL server for testing."""
    
    def __init__(self, host, port, context=None, should_fail=False):
        super().__init__(host, port, should_fail)
        self.ssl_context = context


class TestNotificationService(unittest.TestCase):
    """Test NotificationService functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender_email="noreply@example.com",
            recipients=["admin@example.com", "ops@example.com"]
        )
        self.service = NotificationService(self.config)
        self.node = NodeConfig(
            node_id="kafka-broker-1",
            node_type="kafka_broker",
            host="kafka1.example.com",
            port=9092
        )
        self.recovery_result = RecoveryResult(
            node_id="kafka-broker-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.service.delivery_queue.running:
            self.service.stop()

    def test_service_initialization(self):
        """Test notification service initialization."""
        self.assertEqual(self.service.config, self.config)
        self.assertIsInstance(self.service.template_engine, NotificationTemplate)
        self.assertIsInstance(self.service.delivery_queue, DeliveryQueue)
        self.assertEqual(len(self.service.notifiers), 0)
        self.assertEqual(len(self.service.delivery_callbacks), 0)

    def test_start_stop_service(self):
        """Test starting and stopping the notification service."""
        self.service.start()
        self.assertTrue(self.service.delivery_queue.running)
        
        self.service.stop()
        self.assertFalse(self.service.delivery_queue.running)

    def test_register_notifier(self):
        """Test registering notifiers."""
        mock_notifier = MockNotifier()
        self.service.register_notifier("email", mock_notifier)
        
        self.assertIn("email", self.service.notifiers)
        self.assertEqual(self.service.notifiers["email"], mock_notifier)

    def test_register_delivery_callback(self):
        """Test registering delivery callbacks."""
        callback = Mock()
        self.service.register_delivery_callback(callback)
        
        self.assertIn(callback, self.service.delivery_callbacks)

    def test_send_failure_alert(self):
        """Test sending failure alert."""
        recovery_history = [self.recovery_result]
        
        notification_id = self.service.send_failure_alert(
            self.node, recovery_history, "Connection timeout"
        )
        
        self.assertIsNotNone(notification_id)
        self.assertTrue(notification_id.startswith("notif_"))
        
        # Check that message was queued
        self.assertEqual(self.service.delivery_queue.queue.qsize(), 1)

    def test_send_recovery_confirmation(self):
        """Test sending recovery confirmation."""
        notification_id = self.service.send_recovery_confirmation(
            self.node, self.recovery_result, "5 minutes"
        )
        
        self.assertIsNotNone(notification_id)
        self.assertTrue(notification_id.startswith("notif_"))
        
        # Check that message was queued
        self.assertEqual(self.service.delivery_queue.queue.qsize(), 1)

    def test_get_status(self):
        """Test getting service status."""
        mock_notifier = MockNotifier()
        self.service.register_notifier("email", mock_notifier)
        
        status = self.service.get_status()
        
        self.assertIn('running', status)
        self.assertIn('queue_sizes', status)
        self.assertIn('registered_notifiers', status)
        self.assertIn('config', status)
        
        self.assertFalse(status['running'])
        self.assertEqual(status['registered_notifiers'], ['email'])
        self.assertEqual(status['config']['smtp_host'], 'smtp.example.com')
        self.assertEqual(status['config']['recipient_count'], 2)

    def test_generate_notification_id(self):
        """Test notification ID generation."""
        id1 = self.service._generate_notification_id()
        id2 = self.service._generate_notification_id()
        
        self.assertNotEqual(id1, id2)
        self.assertTrue(id1.startswith("notif_"))
        self.assertTrue(id2.startswith("notif_"))

    def test_notify_delivery_result(self):
        """Test notifying delivery result callbacks."""
        callback1 = Mock()
        callback2 = Mock()
        
        self.service.register_delivery_callback(callback1)
        self.service.register_delivery_callback(callback2)
        
        result = NotificationResult(
            notification_id="test_001",
            recipient="admin@example.com",
            delivery_time=datetime.now(),
            success=True
        )
        
        self.service._notify_delivery_result(result)
        
        callback1.assert_called_once_with(result)
        callback2.assert_called_once_with(result)

    def test_notify_delivery_result_with_exception(self):
        """Test handling exceptions in delivery result callbacks."""
        callback_error = Mock(side_effect=Exception("Callback error"))
        callback_ok = Mock()
        
        self.service.register_delivery_callback(callback_error)
        self.service.register_delivery_callback(callback_ok)
        
        result = NotificationResult(
            notification_id="test_001",
            recipient="admin@example.com",
            delivery_time=datetime.now(),
            success=True
        )
        
        # Should not raise exception
        self.service._notify_delivery_result(result)
        
        callback_error.assert_called_once_with(result)
        callback_ok.assert_called_once_with(result)


class TestNotifier(unittest.TestCase):
    """Test Notifier abstract base class."""

    def test_notifier_is_abstract(self):
        """Test that Notifier cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            Notifier()

    def test_mock_notifier_implementation(self):
        """Test mock notifier implementation."""
        notifier = MockNotifier()
        
        message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )
        
        result = notifier.send(message)
        
        self.assertTrue(result.success)
        self.assertEqual(result.notification_id, "test_001")
        self.assertEqual(result.recipient, "admin@example.com")
        self.assertEqual(len(notifier.sent_messages), 1)
        
        self.assertTrue(notifier.test_connection())


class TestEmailNotifier(unittest.TestCase):
    """Test EmailNotifier functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="user@example.com",
            smtp_password="password",
            use_tls=True,
            sender_email="noreply@example.com",
            recipients=["admin@example.com", "ops@example.com"]
        )
        self.notifier = EmailNotifier(self.config)
        self.test_message = NotificationMessage(
            notification_id="test_001",
            notification_type="failure_alert",
            recipients=["admin@example.com"],
            subject="Test Alert",
            body_text="Test message body",
            body_html="<html><body>Test message body</body></html>"
        )

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp_class):
        """Test successful email sending."""
        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp_class.return_value = mock_smtp
        
        results = self.notifier.send(self.test_message)
        
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].notification_id, "test_001")
        self.assertEqual(results[0].recipient, "admin@example.com")
        self.assertEqual(len(mock_smtp.sent_messages), 1)
        self.assertTrue(mock_smtp.authenticated)
        self.assertTrue(mock_smtp.tls_started)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_send_email_multiple_recipients(self, mock_smtp_class):
        """Test sending email to multiple recipients."""
        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp_class.return_value = mock_smtp
        
        message = NotificationMessage(
            notification_id="test_002",
            notification_type="failure_alert",
            recipients=["admin@example.com", "ops@example.com"],
            subject="Test Alert",
            body_text="Test message body"
        )
        
        results = self.notifier.send(message)
        
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))
        self.assertEqual(results[0].recipient, "admin@example.com")
        self.assertEqual(results[1].recipient, "ops@example.com")
        self.assertEqual(len(mock_smtp.sent_messages), 2)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_send_email_failure(self, mock_smtp_class):
        """Test email sending failure."""
        mock_smtp = MockSMTP("smtp.example.com", 587, should_fail=True)
        mock_smtp_class.return_value = mock_smtp
        
        results = self.notifier.send(self.test_message)
        
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIsNotNone(results[0].error_message)
        self.assertIn("Failed to send email", results[0].error_message)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP_SSL')
    def test_send_email_ssl(self, mock_smtp_ssl_class):
        """Test email sending with SSL."""
        config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_port=465,
            use_tls=False,  # SSL and TLS are mutually exclusive
            use_ssl=True,
            sender_email="noreply@example.com",
            recipients=["admin@example.com"]
        )
        notifier = EmailNotifier(config)
        
        mock_smtp = MockSMTPSSL("smtp.example.com", 465)
        mock_smtp_ssl_class.return_value = mock_smtp
        
        results = notifier.send(self.test_message)
        
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        mock_smtp_ssl_class.assert_called_once()

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_send_email_no_auth(self, mock_smtp_class):
        """Test email sending without authentication."""
        config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_port=25,
            use_tls=False,
            sender_email="noreply@example.com",
            recipients=["admin@example.com"]
        )
        notifier = EmailNotifier(config)
        
        mock_smtp = MockSMTP("smtp.example.com", 25)
        mock_smtp_class.return_value = mock_smtp
        
        results = notifier.send(self.test_message)
        
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertFalse(mock_smtp.authenticated)
        self.assertFalse(mock_smtp.tls_started)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_test_connection_success(self, mock_smtp_class):
        """Test successful connection test."""
        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp_class.return_value = mock_smtp
        
        result = self.notifier.test_connection()
        
        self.assertTrue(result)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_test_connection_failure(self, mock_smtp_class):
        """Test connection test failure."""
        mock_smtp = MockSMTP("smtp.example.com", 587, should_fail=True)
        mock_smtp_class.return_value = mock_smtp
        
        result = self.notifier.test_connection()
        
        self.assertFalse(result)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_send_test_email(self, mock_smtp_class):
        """Test sending test email."""
        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp_class.return_value = mock_smtp
        
        result = self.notifier.send_test_email("test@example.com")
        
        self.assertTrue(result)
        self.assertEqual(len(mock_smtp.sent_messages), 1)
        
        # Check message content
        sent_msg = mock_smtp.sent_messages[0]
        self.assertIn("Test Email", sent_msg['Subject'])
        self.assertEqual(sent_msg['To'], "test@example.com")

    def test_send_test_email_no_recipient(self):
        """Test sending test email without recipient."""
        # Create config with minimal recipients to pass validation
        config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender_email="noreply@example.com",
            recipients=["dummy@example.com"]  # Need at least one for validation
        )
        notifier = EmailNotifier(config)
        
        # Clear recipients after creation to test the no-recipient scenario
        config.recipients = []
        
        result = notifier.send_test_email()
        
        self.assertFalse(result)

    @patch('src.kafka_self_healing.notification.smtplib.SMTP')
    def test_send_test_email_default_recipient(self, mock_smtp_class):
        """Test sending test email to default recipient."""
        mock_smtp = MockSMTP("smtp.example.com", 587)
        mock_smtp_class.return_value = mock_smtp
        
        result = self.notifier.send_test_email()  # No recipient specified
        
        self.assertTrue(result)
        self.assertEqual(len(mock_smtp.sent_messages), 1)
        
        # Should use first recipient from config
        sent_msg = mock_smtp.sent_messages[0]
        self.assertEqual(sent_msg['To'], "admin@example.com")

    def test_email_message_structure(self):
        """Test email message structure and content."""
        with patch('src.kafka_self_healing.notification.smtplib.SMTP') as mock_smtp_class:
            mock_smtp = MockSMTP("smtp.example.com", 587)
            mock_smtp_class.return_value = mock_smtp
            
            results = self.notifier.send(self.test_message)
            
            self.assertTrue(results[0].success)
            self.assertEqual(len(mock_smtp.sent_messages), 1)
            
            sent_msg = mock_smtp.sent_messages[0]
            self.assertEqual(sent_msg['Subject'], "Test Alert")
            self.assertEqual(sent_msg['From'], "noreply@example.com")
            self.assertEqual(sent_msg['To'], "admin@example.com")
            self.assertIn('Date', sent_msg)
            
            # Check multipart structure
            self.assertTrue(sent_msg.is_multipart())
            parts = sent_msg.get_payload()
            self.assertEqual(len(parts), 2)  # Text and HTML parts
            
            # Check text part
            text_part = parts[0]
            self.assertEqual(text_part.get_content_type(), 'text/plain')
            # Decode the payload to check content
            text_content = text_part.get_payload(decode=True).decode('utf-8')
            self.assertIn("Test message body", text_content)
            
            # Check HTML part
            html_part = parts[1]
            self.assertEqual(html_part.get_content_type(), 'text/html')
            # Decode the payload to check content
            html_content = html_part.get_payload(decode=True).decode('utf-8')
            self.assertIn("<html>", html_content)


class TestNotificationIntegration(unittest.TestCase):
    """Integration tests for notification delivery and retry functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = NotificationConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="user@example.com",
            smtp_password="password",
            use_tls=True,
            sender_email="noreply@example.com",
            recipients=["admin@example.com", "ops@example.com"]
        )
        self.service = NotificationService(self.config)
        self.node = NodeConfig(
            node_id="kafka-broker-1",
            node_type="kafka_broker",
            host="kafka1.example.com",
            port=9092
        )

    def tearDown(self):
        """Clean up after tests."""
        if self.service.delivery_queue.running:
            self.service.stop()

    def test_delivery_statistics_tracking(self):
        """Test delivery statistics tracking."""
        # Create mixed success/failure notifier
        class MixedNotifier(Notifier):
            def __init__(self):
                self.call_count = 0
                
            def send(self, message):
                self.call_count += 1
                success = self.call_count % 2 == 0  # Every other call succeeds
                return NotificationResult(
                    notification_id=message.notification_id,
                    recipient=message.recipients[0],
                    delivery_time=datetime.now(),
                    success=success,
                    error_message=None if success else "Simulated failure"
                )
                    
            def test_connection(self):
                return True

        self.service.register_notifier("mixed", MixedNotifier())
        
        # Track delivery results
        results = []
        self.service.register_delivery_callback(lambda r: results.append(r))
        
        self.service.start()
        
        # Send multiple notifications
        for i in range(4):
            self.service.send_failure_alert(
                self.node, [], f"Test failure {i}"
            )
        
        # Wait for processing
        import time
        timeout = 5
        start_time = time.time()
        
        while len(results) < 4 and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        
        self.service.stop()
        
        # Check statistics
        stats = self.service.get_delivery_statistics()
        self.assertEqual(stats['total_sent'], 4)
        self.assertGreater(stats['total_delivered'], 0)
        self.assertGreater(stats['total_failed'], 0)
        self.assertGreaterEqual(stats['success_rate'], 0.0)
        self.assertLessEqual(stats['success_rate'], 1.0)

    def test_notifier_connection_testing(self):
        """Test notifier connection testing functionality."""
        # Create notifiers with different connection states
        class GoodNotifier(Notifier):
            def send(self, message):
                return NotificationResult(
                    notification_id=message.notification_id,
                    recipient=message.recipients[0],
                    delivery_time=datetime.now(),
                    success=True
                )
                    
            def test_connection(self):
                return True

        class BadNotifier(Notifier):
            def send(self, message):
                return NotificationResult(
                    notification_id=message.notification_id,
                    recipient=message.recipients[0],
                    delivery_time=datetime.now(),
                    success=False,
                    error_message="Connection failed"
                )
                    
            def test_connection(self):
                return False

        self.service.register_notifier("good", GoodNotifier())
        self.service.register_notifier("bad", BadNotifier())
        
        # Test all notifiers
        results = self.service.test_all_notifiers()
        
        self.assertTrue(results["good"])
        self.assertFalse(results["bad"])

    def test_send_test_notifications(self):
        """Test sending test notifications."""
        # Create mock notifier
        class TestNotifier(Notifier):
            def __init__(self):
                self.sent_messages = []
                
            def send(self, message):
                self.sent_messages.append(message)
                return NotificationResult(
                    notification_id=message.notification_id,
                    recipient=message.recipients[0],
                    delivery_time=datetime.now(),
                    success=True
                )
                    
            def test_connection(self):
                return True

        notifier = TestNotifier()
        self.service.register_notifier("test", notifier)
        
        # Send test notifications
        results = self.service.send_test_notifications(["test@example.com"])
        
        self.assertTrue(results["test"])
        self.assertEqual(len(notifier.sent_messages), 1)
        
        # Verify test message content
        test_message = notifier.sent_messages[0]
        self.assertEqual(test_message.notification_type, "test")
        self.assertIn("Test Notification", test_message.subject)
        self.assertIn("test notification", test_message.body_text.lower())

    def test_delivery_failure_handling(self):
        """Test handling of delivery failures."""
        # Create notifier that always fails
        class FailingNotifier(Notifier):
            def __init__(self):
                self.attempt_count = 0
                
            def send(self, message):
                self.attempt_count += 1
                return NotificationResult(
                    notification_id=message.notification_id,
                    recipient=message.recipients[0],
                    delivery_time=datetime.now(),
                    success=False,
                    error_message=f"Simulated failure {self.attempt_count}",
                    retry_count=message.retry_count
                )
                    
            def test_connection(self):
                return True

        notifier = FailingNotifier()
        self.service.register_notifier("failing", notifier)
        
        # Track delivery results
        results = []
        self.service.register_delivery_callback(lambda r: results.append(r))
        
        self.service.start()
        
        # Send a notification that will fail
        notification_id = self.service.send_failure_alert(
            self.node, [], "Test failure"
        )
        
        # Wait for initial processing
        import time
        time.sleep(2)
        
        self.service.stop()
        
        # Verify we got at least one result
        self.assertGreater(len(results), 0)
        
        # First attempt should fail
        self.assertFalse(results[0].success)
        self.assertIn("Simulated failure", results[0].error_message)
        
        # Verify that the notifier was called
        self.assertGreater(notifier.attempt_count, 0)

    def test_statistics_reset(self):
        """Test resetting delivery statistics."""
        # Create simple notifier
        class SimpleNotifier(Notifier):
            def send(self, message):
                return NotificationResult(
                    notification_id=message.notification_id,
                    recipient=message.recipients[0],
                    delivery_time=datetime.now(),
                    success=True
                )
                    
            def test_connection(self):
                return True

        self.service.register_notifier("simple", SimpleNotifier())
        self.service.start()
        
        # Send a notification
        self.service.send_failure_alert(self.node, [], "Test failure")
        
        # Wait for processing
        import time
        time.sleep(1)
        
        # Check initial statistics
        stats = self.service.get_delivery_statistics()
        self.assertGreater(stats['total_sent'], 0)
        
        # Reset statistics
        self.service.reset_delivery_statistics()
        
        # Check that statistics are reset
        stats = self.service.get_delivery_statistics()
        self.assertEqual(stats['total_sent'], 0)
        self.assertEqual(stats['total_delivered'], 0)
        self.assertEqual(stats['total_failed'], 0)
        
        self.service.stop()

    def test_no_notifiers_registered(self):
        """Test behavior when no notifiers are registered."""
        # Don't register any notifiers
        results = []
        self.service.register_delivery_callback(lambda r: results.append(r))
        
        self.service.start()
        
        # Send notification
        notification_id = self.service.send_failure_alert(self.node, [], "Test failure")
        
        # Wait for processing
        import time
        time.sleep(2)
        
        self.service.stop()
        
        # Should have received error result eventually
        self.assertGreater(len(results), 0)
        self.assertFalse(results[0].success)
        # The error message should indicate the problem
        self.assertTrue(
            "Max retries exceeded" in results[0].error_message or 
            "No notifiers available" in results[0].error_message
        )


if __name__ == '__main__':
    unittest.main()