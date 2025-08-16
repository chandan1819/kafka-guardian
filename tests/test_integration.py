"""
Integration tests for monitoring-recovery workflow coordination.

Tests the complete flow from monitoring failure detection to recovery execution,
including failure classification and callback management.
"""

import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.integration import (
    MonitoringRecoveryIntegrator,
    FailureClassifier,
    FailureType,
    FailureEvent,
    RecoveryEvent
)
from src.kafka_self_healing.models import NodeConfig, NodeStatus, RecoveryResult, RetryPolicy
from src.kafka_self_healing.monitoring import MonitoringService
from src.kafka_self_healing.recovery import RecoveryEngine


class TestFailureClassifier(unittest.TestCase):
    """Test cases for failure classification."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.classifier = FailureClassifier()
        self.node_config = NodeConfig(
            node_id="test-node",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
    
    def test_classify_timeout_failure(self):
        """Test classification of timeout failures."""
        node_status = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=15000.0,
            error_message="Connection timeout occurred",
            monitoring_method="socket"
        )
        
        failure_type = self.classifier.classify_failure(self.node_config, node_status)
        self.assertEqual(failure_type, FailureType.CONNECTION_TIMEOUT)
    
    def test_classify_authentication_failure(self):
        """Test classification of authentication failures."""
        node_status = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=1000.0,
            error_message="Authentication failed: invalid credentials",
            monitoring_method="jmx"
        )
        
        failure_type = self.classifier.classify_failure(self.node_config, node_status)
        self.assertEqual(failure_type, FailureType.AUTHENTICATION_FAILURE)
    
    def test_classify_service_unavailable(self):
        """Test classification of service unavailable failures."""
        node_status = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=2000.0,
            error_message="Connection refused by server",
            monitoring_method="socket"
        )
        
        failure_type = self.classifier.classify_failure(self.node_config, node_status)
        self.assertEqual(failure_type, FailureType.SERVICE_UNAVAILABLE)
    
    def test_classify_jmx_failure(self):
        """Test classification of JMX-specific failures."""
        node_status = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=3000.0,
            error_message="JMX connection failed",
            monitoring_method="jmx"
        )
        
        failure_type = self.classifier.classify_failure(self.node_config, node_status)
        self.assertEqual(failure_type, FailureType.JMX_CONNECTION_FAILURE)
    
    def test_classify_zookeeper_failure(self):
        """Test classification of Zookeeper failures."""
        zk_node = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="localhost",
            port=2181
        )
        
        node_status = NodeStatus(
            node_id="zk-1",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=2000.0,
            error_message="Zookeeper ensemble not available",
            monitoring_method="zookeeper"
        )
        
        failure_type = self.classifier.classify_failure(zk_node, node_status)
        self.assertEqual(failure_type, FailureType.ZOOKEEPER_FAILURE)
    
    def test_classify_unknown_failure(self):
        """Test classification of unknown failures."""
        node_status = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=1000.0,
            error_message="Some unknown error occurred",
            monitoring_method="socket"
        )
        
        failure_type = self.classifier.classify_failure(self.node_config, node_status)
        self.assertEqual(failure_type, FailureType.HEALTH_CHECK_FAILURE)
    
    def test_get_recovery_priority(self):
        """Test recovery priority assignment."""
        # High priority failures
        self.assertEqual(self.classifier.get_recovery_priority(FailureType.SERVICE_UNAVAILABLE), 1)
        self.assertEqual(self.classifier.get_recovery_priority(FailureType.RESOURCE_EXHAUSTION), 1)
        
        # Medium priority failures
        self.assertEqual(self.classifier.get_recovery_priority(FailureType.HEALTH_CHECK_FAILURE), 2)
        self.assertEqual(self.classifier.get_recovery_priority(FailureType.ZOOKEEPER_FAILURE), 2)
        
        # Lower priority failures
        self.assertEqual(self.classifier.get_recovery_priority(FailureType.AUTHENTICATION_FAILURE), 8)
    
    def test_get_recommended_actions_kafka(self):
        """Test recommended actions for Kafka broker failures."""
        actions = self.classifier.get_recommended_actions(
            FailureType.SERVICE_UNAVAILABLE, 
            "kafka_broker"
        )
        
        self.assertIn("kafka_restart", actions)
        self.assertGreater(len(actions), 0)
    
    def test_get_recommended_actions_zookeeper(self):
        """Test recommended actions for Zookeeper failures."""
        actions = self.classifier.get_recommended_actions(
            FailureType.ZOOKEEPER_FAILURE, 
            "zookeeper"
        )
        
        self.assertIn("zk_restart", actions)
        self.assertGreater(len(actions), 0)


class TestMonitoringRecoveryIntegrator(unittest.TestCase):
    """Test cases for monitoring-recovery integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock services
        self.mock_monitoring = Mock(spec=MonitoringService)
        self.mock_recovery = Mock(spec=RecoveryEngine)
        
        # Create integrator
        self.integrator = MonitoringRecoveryIntegrator(
            self.mock_monitoring,
            self.mock_recovery
        )
        
        # Test node configuration
        self.node_config = NodeConfig(
            node_id="test-kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["service_restart"]
        )
        
        # Test node status (unhealthy)
        self.unhealthy_status = NodeStatus(
            node_id="test-kafka-1",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=5000.0,
            error_message="Connection timeout",
            monitoring_method="socket"
        )
        
        # Test node status (healthy)
        self.healthy_status = NodeStatus(
            node_id="test-kafka-1",
            is_healthy=True,
            last_check_time=datetime.now(),
            response_time_ms=100.0,
            monitoring_method="socket"
        )
    
    def test_integration_setup(self):
        """Test that integration is properly set up."""
        # Verify callbacks were registered
        self.mock_monitoring.register_failure_callback.assert_called()
        self.mock_monitoring.register_recovery_callback.assert_called()
        self.mock_recovery.register_escalation_callback.assert_called()
    
    def test_handle_node_failure(self):
        """Test handling of node failure events."""
        # Mock recovery engine response
        mock_result = RecoveryResult(
            node_id="test-kafka-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        self.mock_recovery.execute_recovery.return_value = mock_result
        
        # Trigger failure handling
        self.integrator._handle_node_failure(self.node_config, self.unhealthy_status)
        
        # Verify recovery was initiated
        self.mock_recovery.execute_recovery.assert_called_once()
        
        # Verify failure event was recorded
        self.assertIn("test-kafka-1", self.integrator.failure_events)
        self.assertEqual(len(self.integrator.failure_events["test-kafka-1"]), 1)
        
        # Verify node is in active recoveries
        self.assertIn("test-kafka-1", self.integrator.active_recoveries)
    
    def test_handle_node_recovery(self):
        """Test handling of node recovery events."""
        # First trigger a failure to set up active recovery
        self.integrator._handle_node_failure(self.node_config, self.unhealthy_status)
        
        # Mock recovery history
        mock_result = RecoveryResult(
            node_id="test-kafka-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        self.mock_recovery.get_recovery_history.return_value = [mock_result]
        
        # Trigger recovery handling
        self.integrator._handle_node_recovery(self.node_config, self.healthy_status)
        
        # Verify recovery event was recorded
        self.assertIn("test-kafka-1", self.integrator.recovery_events)
        self.assertEqual(len(self.integrator.recovery_events["test-kafka-1"]), 1)
        
        # Verify node is no longer in active recoveries
        self.assertNotIn("test-kafka-1", self.integrator.active_recoveries)
        
        # Verify cooldown was set
        self.assertIn("test-kafka-1", self.integrator.recovery_cooldown)
    
    def test_handle_recovery_escalation(self):
        """Test handling of recovery escalation."""
        # Set up active recovery
        failure_event = FailureEvent(
            node_config=self.node_config,
            node_status=self.unhealthy_status,
            failure_type=FailureType.SERVICE_UNAVAILABLE
        )
        self.integrator.active_recoveries["test-kafka-1"] = failure_event
        
        # Mock recovery history
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
        
        # Trigger escalation
        self.integrator._handle_recovery_escalation("test-kafka-1", failed_results)
        
        # Verify node is no longer in active recoveries
        self.assertNotIn("test-kafka-1", self.integrator.active_recoveries)
        
        # Verify extended cooldown was set
        self.assertIn("test-kafka-1", self.integrator.recovery_cooldown)
        cooldown_time = self.integrator.recovery_cooldown["test-kafka-1"]
        expected_cooldown = datetime.now() + timedelta(seconds=self.integrator.cooldown_period_seconds * 3)
        self.assertAlmostEqual(cooldown_time.timestamp(), expected_cooldown.timestamp(), delta=5)
    
    def test_cooldown_period(self):
        """Test cooldown period functionality."""
        # Set a node in cooldown
        cooldown_time = datetime.now() + timedelta(seconds=300)
        self.integrator.recovery_cooldown["test-kafka-1"] = cooldown_time
        
        # Should be in cooldown
        self.assertTrue(self.integrator._is_in_cooldown("test-kafka-1"))
        
        # Clear cooldown
        self.assertTrue(self.integrator.clear_cooldown("test-kafka-1"))
        self.assertFalse(self.integrator._is_in_cooldown("test-kafka-1"))
    
    def test_concurrent_recovery_limit(self):
        """Test concurrent recovery limit enforcement."""
        # Set low limit for testing
        self.integrator.set_max_concurrent_recoveries(1)
        
        # Create multiple nodes
        node1 = NodeConfig(node_id="node-1", node_type="kafka_broker", host="host1", port=9092)
        node2 = NodeConfig(node_id="node-2", node_type="kafka_broker", host="host2", port=9092)
        
        status1 = NodeStatus(node_id="node-1", is_healthy=False, last_check_time=datetime.now(), response_time_ms=1000.0)
        status2 = NodeStatus(node_id="node-2", is_healthy=False, last_check_time=datetime.now(), response_time_ms=1000.0)
        
        # First failure should be processed
        self.integrator._handle_node_failure(node1, status1)
        self.assertIn("node-1", self.integrator.active_recoveries)
        
        # Second failure should be skipped due to limit
        with patch.object(self.integrator.logger, 'warning') as mock_warning:
            self.integrator._handle_node_failure(node2, status2)
            mock_warning.assert_called()
        
        self.assertNotIn("node-2", self.integrator.active_recoveries)
    
    def test_failure_callbacks(self):
        """Test failure event callbacks."""
        callback_called = False
        received_event = None
        
        def test_callback(failure_event):
            nonlocal callback_called, received_event
            callback_called = True
            received_event = failure_event
        
        # Register callback
        self.integrator.register_failure_callback(test_callback)
        
        # Trigger failure
        self.integrator._handle_node_failure(self.node_config, self.unhealthy_status)
        
        # Verify callback was called
        self.assertTrue(callback_called)
        self.assertIsNotNone(received_event)
        self.assertEqual(received_event.node_config.node_id, "test-kafka-1")
    
    def test_recovery_callbacks(self):
        """Test recovery event callbacks."""
        callback_called = False
        received_event = None
        
        def test_callback(recovery_event):
            nonlocal callback_called, received_event
            callback_called = True
            received_event = recovery_event
        
        # Register callback
        self.integrator.register_recovery_callback(test_callback)
        
        # Set up failure and recovery
        self.integrator._handle_node_failure(self.node_config, self.unhealthy_status)
        
        mock_result = RecoveryResult(
            node_id="test-kafka-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        self.mock_recovery.get_recovery_history.return_value = [mock_result]
        
        # Trigger recovery
        self.integrator._handle_node_recovery(self.node_config, self.healthy_status)
        
        # Verify callback was called
        self.assertTrue(callback_called)
        self.assertIsNotNone(received_event)
        self.assertEqual(received_event.node_config.node_id, "test-kafka-1")
    
    def test_escalation_callbacks(self):
        """Test escalation event callbacks."""
        callback_called = False
        received_node_id = None
        received_history = None
        
        def test_callback(node_id, recovery_history):
            nonlocal callback_called, received_node_id, received_history
            callback_called = True
            received_node_id = node_id
            received_history = recovery_history
        
        # Register callback
        self.integrator.register_escalation_callback(test_callback)
        
        # Set up active recovery
        failure_event = FailureEvent(
            node_config=self.node_config,
            node_status=self.unhealthy_status,
            failure_type=FailureType.SERVICE_UNAVAILABLE
        )
        self.integrator.active_recoveries["test-kafka-1"] = failure_event
        
        # Trigger escalation
        failed_results = [Mock()]
        self.integrator._handle_recovery_escalation("test-kafka-1", failed_results)
        
        # Verify callback was called
        self.assertTrue(callback_called)
        self.assertEqual(received_node_id, "test-kafka-1")
        self.assertEqual(received_history, failed_results)
    
    def test_failure_statistics(self):
        """Test failure statistics collection."""
        # Generate some test events
        self.integrator._handle_node_failure(self.node_config, self.unhealthy_status)
        
        # Get statistics
        stats = self.integrator.get_failure_statistics()
        
        # Verify statistics structure
        self.assertIn('total_failures', stats)
        self.assertIn('total_recoveries', stats)
        self.assertIn('active_recoveries', stats)
        self.assertIn('nodes_in_cooldown', stats)
        self.assertIn('failure_types', stats)
        self.assertIn('recovery_success_rate', stats)
        
        # Verify counts
        self.assertEqual(stats['total_failures'], 1)
        self.assertEqual(stats['active_recoveries'], 1)
    
    def test_node_history_retrieval(self):
        """Test retrieval of node-specific history."""
        # Generate failure event
        self.integrator._handle_node_failure(self.node_config, self.unhealthy_status)
        
        # Get failure history
        failure_history = self.integrator.get_node_failure_history("test-kafka-1")
        self.assertEqual(len(failure_history), 1)
        self.assertEqual(failure_history[0]['node_id'], "test-kafka-1")
        
        # Set up recovery event
        mock_result = RecoveryResult(
            node_id="test-kafka-1",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        self.mock_recovery.get_recovery_history.return_value = [mock_result]
        self.integrator._handle_node_recovery(self.node_config, self.healthy_status)
        
        # Get recovery history
        recovery_history = self.integrator.get_node_recovery_history("test-kafka-1")
        self.assertEqual(len(recovery_history), 1)
        self.assertEqual(recovery_history[0]['node_id'], "test-kafka-1")


class TestCompleteWorkflow(unittest.TestCase):
    """Integration tests for complete monitoring-recovery workflows."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create real services with mocked dependencies
        self.mock_cluster_config = Mock()
        self.mock_cluster_config.nodes = []
        
        self.monitoring_service = MonitoringService(self.mock_cluster_config)
        self.recovery_engine = RecoveryEngine()
        
        # Create integrator
        self.integrator = MonitoringRecoveryIntegrator(
            self.monitoring_service,
            self.recovery_engine
        )
        
        # Test node
        self.node_config = NodeConfig(
            node_id="integration-test-node",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["service_restart"]
        )
    
    def test_complete_failure_to_recovery_workflow(self):
        """Test complete workflow from failure detection to successful recovery."""
        # Mock recovery action
        mock_action = Mock()
        mock_action.execute.return_value = RecoveryResult(
            node_id="integration-test-node",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        mock_action.supports_node_type.return_value = True
        mock_action.validate_config.return_value = True
        
        self.recovery_engine.register_recovery_action("service_restart", mock_action)
        
        # Track callback invocations
        failure_callbacks = []
        recovery_callbacks = []
        
        def failure_callback(event):
            failure_callbacks.append(event)
        
        def recovery_callback(event):
            recovery_callbacks.append(event)
        
        self.integrator.register_failure_callback(failure_callback)
        self.integrator.register_recovery_callback(recovery_callback)
        
        # Simulate failure detection
        unhealthy_status = NodeStatus(
            node_id="integration-test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=8000.0,
            error_message="Service unavailable",
            monitoring_method="socket"
        )
        
        # Trigger failure workflow
        self.integrator._handle_node_failure(self.node_config, unhealthy_status)
        
        # Verify failure was processed
        self.assertEqual(len(failure_callbacks), 1)
        self.assertEqual(failure_callbacks[0].failure_type, FailureType.SERVICE_UNAVAILABLE)
        
        # Simulate recovery detection
        healthy_status = NodeStatus(
            node_id="integration-test-node",
            is_healthy=True,
            last_check_time=datetime.now(),
            response_time_ms=100.0,
            monitoring_method="socket"
        )
        
        # Trigger recovery workflow
        self.integrator._handle_node_recovery(self.node_config, healthy_status)
        
        # Verify recovery was processed
        self.assertEqual(len(recovery_callbacks), 1)
        self.assertTrue(recovery_callbacks[0].recovery_result.success)
    
    def test_failure_escalation_workflow(self):
        """Test workflow when recovery fails and escalates."""
        # Mock failing recovery action
        mock_action = Mock()
        mock_action.execute.return_value = RecoveryResult(
            node_id="integration-test-node",
            action_type="service_restart",
            command_executed="systemctl restart kafka",
            exit_code=1,
            stdout="",
            stderr="Service failed to restart",
            execution_time=datetime.now(),
            success=False
        )
        mock_action.supports_node_type.return_value = True
        mock_action.validate_config.return_value = True
        
        self.recovery_engine.register_recovery_action("service_restart", mock_action)
        
        # Track escalation callbacks
        escalation_callbacks = []
        
        def escalation_callback(node_id, history):
            escalation_callbacks.append((node_id, history))
        
        self.integrator.register_escalation_callback(escalation_callback)
        
        # Simulate failure
        unhealthy_status = NodeStatus(
            node_id="integration-test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=5000.0,
            error_message="Connection timeout",
            monitoring_method="socket"
        )
        
        # Trigger failure (this will attempt recovery and fail)
        self.integrator._handle_node_failure(self.node_config, unhealthy_status)
        
        # Manually trigger escalation (normally done by recovery engine)
        failed_results = [mock_action.execute.return_value]
        self.integrator._handle_recovery_escalation("integration-test-node", failed_results)
        
        # Verify escalation was processed
        self.assertEqual(len(escalation_callbacks), 1)
        self.assertEqual(escalation_callbacks[0][0], "integration-test-node")
        self.assertEqual(len(escalation_callbacks[0][1]), 1)


if __name__ == '__main__':
    unittest.main()