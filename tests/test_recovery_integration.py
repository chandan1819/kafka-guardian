"""
Integration tests for the recovery engine system.

These tests verify complete recovery workflows including coordination between
the recovery engine, recovery actions, and plugins.
"""

import pytest
import time
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.recovery import RecoveryEngine, RecoveryAction, RetryManager
from src.kafka_self_healing.recovery_plugins import ServiceRestartPlugin, ScriptRecoveryPlugin, AnsibleRecoveryPlugin
from src.kafka_self_healing.models import NodeConfig, RecoveryResult, RetryPolicy
from src.kafka_self_healing.exceptions import RecoveryError, ValidationError


class MockRecoveryAction(RecoveryAction):
    """Mock recovery action for integration testing."""
    
    def __init__(self, action_type: str = "mock_action", should_succeed: bool = True, 
                 execution_delay: float = 0.01, fail_count: int = 0):
        super().__init__(action_type)
        self.should_succeed = should_succeed
        self.execution_delay = execution_delay
        self.fail_count = fail_count  # Number of times to fail before succeeding
        self.execution_count = 0
        self.execute_called = False
    
    def execute(self, node: NodeConfig) -> RecoveryResult:
        self.execute_called = True
        self.execution_count += 1
        
        if self.execution_delay > 0:
            time.sleep(self.execution_delay)
        
        # Fail for the first fail_count attempts, then succeed
        success = self.execution_count > self.fail_count if self.should_succeed else False
        
        return RecoveryResult(
            node_id=node.node_id,
            action_type=self.action_type,
            command_executed=f"mock command {self.execution_count}",
            exit_code=0 if success else 1,
            stdout=f"Mock output {self.execution_count}" if success else "",
            stderr="" if success else f"Mock error {self.execution_count}",
            execution_time=datetime.now(),
            success=success
        )
    
    def validate_config(self) -> bool:
        return True


class TestRecoveryEngineIntegration:
    """Integration tests for RecoveryEngine."""
    
    def test_complete_successful_recovery_workflow(self):
        """Test complete successful recovery workflow."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=3, initial_delay_seconds=0.1)
        engine = RecoveryEngine(retry_policy)
        
        action = MockRecoveryAction("test_action", should_succeed=True)
        engine.register_recovery_action("test_action", action)
        
        escalation_callback = Mock()
        engine.register_escalation_callback(escalation_callback)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Execute recovery
        result = engine.execute_recovery(node, "connection_failure")
        
        # Verify results
        assert result.success is True
        assert result.node_id == "kafka-1"
        assert result.action_type == "test_action"
        assert action.execute_called is True
        assert action.execution_count == 1
        
        # Verify history
        history = engine.get_recovery_history("kafka-1")
        assert len(history) == 1
        assert history[0] == result
        
        # Verify no active recoveries (cleared after success)
        active = engine.get_active_recoveries()
        assert "kafka-1" not in active
        
        # Verify escalation callback was not called
        escalation_callback.assert_not_called()
    
    def test_recovery_with_retries_eventual_success(self):
        """Test recovery that fails initially but succeeds after retries."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=3, initial_delay_seconds=0.01)
        engine = RecoveryEngine(retry_policy)
        
        # Action that fails once then succeeds
        action = MockRecoveryAction("test_action", should_succeed=True, fail_count=1)
        engine.register_recovery_action("test_action", action)
        
        escalation_callback = Mock()
        engine.register_escalation_callback(escalation_callback)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Execute recovery attempts
        result1 = engine.execute_recovery(node, "connection_failure")
        assert result1.success is False
        assert action.execution_count == 1
        
        result2 = engine.execute_recovery(node, "connection_failure")
        assert result2.success is True  # Succeeds on second attempt (fail_count=1)
        assert action.execution_count == 2
        
        # Verify history
        history = engine.get_recovery_history("kafka-1")
        assert len(history) == 2
        assert history[0].success is False
        assert history[1].success is True
        
        # Verify no active recoveries (cleared after success)
        active = engine.get_active_recoveries()
        assert "kafka-1" not in active
        
        # Verify escalation callback was not called
        escalation_callback.assert_not_called()
    
    def test_recovery_with_max_retries_and_escalation(self):
        """Test recovery that fails all retries and triggers escalation."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.01)
        engine = RecoveryEngine(retry_policy)
        
        action = MockRecoveryAction("test_action", should_succeed=False)
        engine.register_recovery_action("test_action", action)
        
        escalation_callback = Mock()
        engine.register_escalation_callback(escalation_callback)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Execute recovery attempts
        result1 = engine.execute_recovery(node, "connection_failure")
        assert result1.success is False
        assert action.execution_count == 1
        
        result2 = engine.execute_recovery(node, "connection_failure")
        assert result2.success is False
        assert action.execution_count == 2
        
        # Third attempt should trigger escalation
        with pytest.raises(RecoveryError, match="Maximum retry attempts reached"):
            engine.execute_recovery(node, "connection_failure")
        
        # Verify history
        history = engine.get_recovery_history("kafka-1")
        assert len(history) == 2
        assert all(not result.success for result in history)
        
        # Verify escalation callback was called
        escalation_callback.assert_called_once()
        call_args = escalation_callback.call_args[0]
        assert call_args[0] == "kafka-1"  # node_id
        assert len(call_args[1]) == 2  # recovery history
        
        # Verify no active recoveries (cleared after escalation)
        active = engine.get_active_recoveries()
        assert "kafka-1" not in active
    
    def test_multiple_nodes_concurrent_recovery(self):
        """Test recovery for multiple nodes concurrently."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.01)
        engine = RecoveryEngine(retry_policy)
        
        action1 = MockRecoveryAction("action1", should_succeed=True)
        action2 = MockRecoveryAction("action2", should_succeed=True, fail_count=1)
        
        engine.register_recovery_action("action1", action1)
        engine.register_recovery_action("action2", action2)
        
        node1 = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["action1"],
            retry_policy=retry_policy
        )
        
        node2 = NodeConfig(
            node_id="kafka-2",
            node_type="kafka_broker",
            host="localhost",
            port=9093,
            recovery_actions=["action2"],
            retry_policy=retry_policy
        )
        
        # Execute recovery for both nodes
        result1 = engine.execute_recovery(node1, "connection_failure")
        result2_attempt1 = engine.execute_recovery(node2, "connection_failure")
        result2_attempt2 = engine.execute_recovery(node2, "connection_failure")
        
        # Verify results
        assert result1.success is True
        assert result1.node_id == "kafka-1"
        
        assert result2_attempt1.success is False
        assert result2_attempt2.success is True
        assert result2_attempt2.node_id == "kafka-2"
        
        # Verify separate histories
        history1 = engine.get_recovery_history("kafka-1")
        history2 = engine.get_recovery_history("kafka-2")
        
        assert len(history1) == 1
        assert len(history2) == 2
        assert history1[0].success is True
        assert history2[0].success is False
        assert history2[1].success is True
    
    def test_recovery_action_priority_and_fallback(self):
        """Test recovery action priority and fallback mechanisms."""
        # Setup
        engine = RecoveryEngine()
        
        # Register multiple actions
        primary_action = MockRecoveryAction("primary", should_succeed=False)
        fallback_action = MockRecoveryAction("fallback", should_succeed=True)
        
        engine.register_recovery_action("primary", primary_action)
        engine.register_recovery_action("fallback", fallback_action)
        
        # Node configured with primary action first
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["primary"]  # Only primary configured
        )
        
        # Execute recovery - should use primary action
        result = engine.execute_recovery(node, "connection_failure")
        
        assert result.success is False
        assert result.action_type == "primary"
        assert primary_action.execute_called is True
        assert fallback_action.execute_called is False
    
    def test_recovery_with_plugin_integration(self):
        """Test recovery using plugins."""
        # Setup
        engine = RecoveryEngine()
        
        # Create a mock plugin
        mock_plugin = Mock()
        mock_plugin.name = "MockPlugin"
        mock_plugin.supports_recovery_type.return_value = True
        mock_plugin.execute_recovery.return_value = RecoveryResult(
            node_id="kafka-1",
            action_type="plugin_MockPlugin",
            command_executed="mock plugin command",
            exit_code=0,
            stdout="Plugin success",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        
        engine.register_recovery_plugin(mock_plugin)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        # Execute recovery
        result = engine.execute_recovery(node, "connection_failure")
        
        # Verify plugin was used
        assert result.success is True
        assert result.action_type == "plugin_MockPlugin"
        mock_plugin.execute_recovery.assert_called_once_with(node, "connection_failure")
    
    def test_recovery_history_management(self):
        """Test recovery history management and limits."""
        # Setup
        engine = RecoveryEngine()
        action = MockRecoveryAction("test_action", should_succeed=True)
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"]
        )
        
        # Execute many recovery attempts to test history limits
        for i in range(150):  # More than the 100 limit
            engine.execute_recovery(node, "connection_failure")
        
        # Verify history is limited to 100 entries
        history = engine.get_recovery_history("kafka-1")
        assert len(history) == 100
        
        # Verify most recent entries are kept
        assert all(result.success for result in history)
    
    def test_recovery_cancellation(self):
        """Test recovery cancellation functionality."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=3, initial_delay_seconds=0.01)
        engine = RecoveryEngine(retry_policy)
        
        action = MockRecoveryAction("test_action", should_succeed=False)
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Start recovery (first attempt)
        result1 = engine.execute_recovery(node, "connection_failure")
        assert result1.success is False
        
        # Verify active recovery exists
        active = engine.get_active_recoveries()
        assert "kafka-1" in active
        
        # Cancel recovery
        cancelled = engine.cancel_recovery("kafka-1")
        assert cancelled is True
        
        # Verify no active recovery
        active = engine.get_active_recoveries()
        assert "kafka-1" not in active
        
        # Next attempt should start fresh
        result2 = engine.execute_recovery(node, "connection_failure")
        assert result2.success is False
        
        # Should be back to attempt 1 (reset)
        active = engine.get_active_recoveries()
        assert active["kafka-1"]["attempt_count"] == 1
    
    def test_recovery_history_reset(self):
        """Test recovery history reset functionality."""
        # Setup
        engine = RecoveryEngine()
        action = MockRecoveryAction("test_action", should_succeed=True)
        engine.register_recovery_action("test_action", action)
        
        node1 = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"]
        )
        
        node2 = NodeConfig(
            node_id="kafka-2",
            node_type="kafka_broker",
            host="localhost",
            port=9093,
            recovery_actions=["test_action"]
        )
        
        # Execute recoveries
        engine.execute_recovery(node1, "connection_failure")
        engine.execute_recovery(node2, "connection_failure")
        
        # Verify histories exist
        assert len(engine.get_recovery_history("kafka-1")) == 1
        assert len(engine.get_recovery_history("kafka-2")) == 1
        
        # Reset specific node history
        engine.reset_recovery_history("kafka-1")
        assert len(engine.get_recovery_history("kafka-1")) == 0
        assert len(engine.get_recovery_history("kafka-2")) == 1
        
        # Reset all history
        engine.reset_recovery_history()
        assert len(engine.get_recovery_history("kafka-1")) == 0
        assert len(engine.get_recovery_history("kafka-2")) == 0
    
    def test_multiple_escalation_callbacks(self):
        """Test multiple escalation callbacks are called."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=1, initial_delay_seconds=0.01)
        engine = RecoveryEngine(retry_policy)
        
        action = MockRecoveryAction("test_action", should_succeed=False)
        engine.register_recovery_action("test_action", action)
        
        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock()
        
        engine.register_escalation_callback(callback1)
        engine.register_escalation_callback(callback2)
        engine.register_escalation_callback(callback3)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Execute recovery that will fail and escalate
        engine.execute_recovery(node, "connection_failure")
        
        with pytest.raises(RecoveryError):
            engine.execute_recovery(node, "connection_failure")
        
        # Verify all callbacks were called
        callback1.assert_called_once()
        callback2.assert_called_once()
        callback3.assert_called_once()
    
    def test_escalation_callback_error_handling(self):
        """Test that escalation callback errors don't break the system."""
        # Setup
        retry_policy = RetryPolicy(max_attempts=1, initial_delay_seconds=0.01)
        engine = RecoveryEngine(retry_policy)
        
        action = MockRecoveryAction("test_action", should_succeed=False)
        engine.register_recovery_action("test_action", action)
        
        # Callback that raises an exception
        failing_callback = Mock(side_effect=Exception("Callback failed"))
        working_callback = Mock()
        
        engine.register_escalation_callback(failing_callback)
        engine.register_escalation_callback(working_callback)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Execute recovery that will fail and escalate
        engine.execute_recovery(node, "connection_failure")
        
        # Should not raise exception despite callback failure
        with pytest.raises(RecoveryError):
            engine.execute_recovery(node, "connection_failure")
        
        # Verify both callbacks were called
        failing_callback.assert_called_once()
        working_callback.assert_called_once()


class TestRecoveryPluginIntegration:
    """Integration tests for recovery plugins."""
    
    @patch('subprocess.run')
    def test_service_restart_plugin_integration(self, mock_run):
        """Test ServiceRestartPlugin integration with RecoveryEngine."""
        mock_run.return_value = Mock(returncode=0, stdout="Service restarted", stderr="")
        
        # Setup
        engine = RecoveryEngine()
        plugin = ServiceRestartPlugin()
        engine.register_recovery_plugin(plugin)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        # Execute recovery
        result = engine.execute_recovery(node, "service_restart")
        
        # Verify plugin was used
        assert result.success is True
        assert result.action_type == "service_restart"
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('os.access')
    def test_script_recovery_plugin_integration(self, mock_access, mock_exists, mock_run):
        """Test ScriptRecoveryPlugin integration with RecoveryEngine."""
        mock_exists.return_value = True
        mock_access.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="Script executed", stderr="")
        
        # Setup
        config = {
            'scripts': {
                'connection_failure': 'restart_kafka.sh'
            }
        }
        engine = RecoveryEngine()
        plugin = ScriptRecoveryPlugin(config)
        engine.register_recovery_plugin(plugin)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        # Execute recovery
        result = engine.execute_recovery(node, "connection_failure")
        
        # Verify plugin was used
        assert result.success is True
        assert result.action_type == "script_recovery"
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_ansible_recovery_plugin_integration(self, mock_exists, mock_run):
        """Test AnsibleRecoveryPlugin integration with RecoveryEngine."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0, stdout="Playbook executed", stderr="")
        
        # Setup
        config = {
            'playbooks': {
                'connection_failure': 'restart.yml'
            }
        }
        engine = RecoveryEngine()
        plugin = AnsibleRecoveryPlugin(config)
        engine.register_recovery_plugin(plugin)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        # Execute recovery
        result = engine.execute_recovery(node, "connection_failure")
        
        # Verify plugin was used
        assert result.success is True
        assert result.action_type == "ansible_recovery"
        mock_run.assert_called_once()
    
    def test_multiple_plugins_priority(self):
        """Test priority when multiple plugins support the same recovery type."""
        # Setup
        engine = RecoveryEngine()
        
        # Create mock plugins
        plugin1 = Mock()
        plugin1.name = "Plugin1"
        plugin1.supports_recovery_type.return_value = True
        plugin1.execute_recovery.return_value = RecoveryResult(
            node_id="kafka-1",
            action_type="plugin_Plugin1",
            command_executed="plugin1 command",
            exit_code=0,
            stdout="Plugin1 success",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        
        plugin2 = Mock()
        plugin2.name = "Plugin2"
        plugin2.supports_recovery_type.return_value = True
        plugin2.execute_recovery.return_value = RecoveryResult(
            node_id="kafka-1",
            action_type="plugin_Plugin2",
            command_executed="plugin2 command",
            exit_code=0,
            stdout="Plugin2 success",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
        
        # Register plugins (first registered has priority)
        engine.register_recovery_plugin(plugin1)
        engine.register_recovery_plugin(plugin2)
        
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        # Execute recovery
        result = engine.execute_recovery(node, "connection_failure")
        
        # Verify first plugin was used
        assert result.action_type == "plugin_Plugin1"
        plugin1.execute_recovery.assert_called_once()
        plugin2.execute_recovery.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])