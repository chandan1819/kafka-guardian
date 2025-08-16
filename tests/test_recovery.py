"""
Unit tests for the recovery engine system.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.kafka_self_healing.recovery import (
    RecoveryAction, RetryManager, RecoveryEngine, PluginRecoveryAction
)
from src.kafka_self_healing.models import NodeConfig, RecoveryResult, RetryPolicy
from src.kafka_self_healing.plugins import RecoveryPlugin
from src.kafka_self_healing.exceptions import RecoveryError, ValidationError


class MockRecoveryAction(RecoveryAction):
    """Mock recovery action for testing."""
    
    def __init__(self, action_type: str = "mock_action", should_succeed: bool = True, 
                 execution_time: float = 0.1, config: dict = None):
        super().__init__(action_type, config)
        self.should_succeed = should_succeed
        self.execution_time = execution_time
        self.execute_called = False
        self.validate_called = False
    
    def execute(self, node: NodeConfig) -> RecoveryResult:
        self.execute_called = True
        if self.execution_time > 0:
            time.sleep(self.execution_time)
        
        if not self.should_succeed:
            raise RecoveryError("Mock recovery action failed")
        
        return RecoveryResult(
            node_id=node.node_id,
            action_type=self.action_type,
            command_executed="mock command",
            exit_code=0 if self.should_succeed else 1,
            stdout="Mock success output" if self.should_succeed else "",
            stderr="" if self.should_succeed else "Mock error output",
            execution_time=datetime.now(),
            success=self.should_succeed
        )
    
    def validate_config(self) -> bool:
        self.validate_called = True
        return True
    
    def supports_node_type(self, node_type: str) -> bool:
        return node_type in ["kafka_broker", "zookeeper"]


class MockRecoveryPlugin(RecoveryPlugin):
    """Mock recovery plugin for testing."""
    
    def __init__(self, name: str = "MockPlugin", should_succeed: bool = True):
        super().__init__()
        self.name = name
        self.should_succeed = should_succeed
        self.execute_called = False
        self.validate_called = False
        self.initialize_called = False
        self.cleanup_called = False
    
    def execute_recovery(self, node: NodeConfig, failure_type: str) -> RecoveryResult:
        self.execute_called = True
        return RecoveryResult(
            node_id=node.node_id,
            action_type=f"plugin_{self.name}",
            command_executed="mock plugin command",
            exit_code=0 if self.should_succeed else 1,
            stdout="Plugin success" if self.should_succeed else "",
            stderr="" if self.should_succeed else "Plugin error",
            execution_time=datetime.now(),
            success=self.should_succeed
        )
    
    def supports_recovery_type(self, recovery_type: str) -> bool:
        return recovery_type in ["connection_failure", "service_down"]
    
    def validate_config(self) -> bool:
        self.validate_called = True
        return True
    
    def initialize(self) -> bool:
        self.initialize_called = True
        return True
    
    def cleanup(self) -> None:
        self.cleanup_called = True


class TestRetryManager:
    """Test cases for RetryManager."""
    
    def test_retry_manager_initialization(self):
        """Test retry manager initialization."""
        retry_policy = RetryPolicy(max_attempts=3, initial_delay_seconds=10, 
                                 backoff_multiplier=2.0, max_delay_seconds=60)
        manager = RetryManager(retry_policy)
        
        assert manager.retry_policy == retry_policy
        assert manager.attempt_count == 0
        assert manager.last_attempt_time is None
    
    def test_should_retry_logic(self):
        """Test retry logic."""
        retry_policy = RetryPolicy(max_attempts=3)
        manager = RetryManager(retry_policy)
        
        # Should retry for first 3 attempts
        assert manager.should_retry() is True
        manager.record_attempt()
        
        assert manager.should_retry() is True
        manager.record_attempt()
        
        assert manager.should_retry() is True
        manager.record_attempt()
        
        # Should not retry after max attempts
        assert manager.should_retry() is False
    
    def test_exponential_backoff_delay(self):
        """Test exponential backoff delay calculation."""
        retry_policy = RetryPolicy(initial_delay_seconds=2, backoff_multiplier=2.0, max_delay_seconds=16)
        manager = RetryManager(retry_policy)
        
        # First attempt has no delay
        assert manager.get_next_delay() == 0
        manager.record_attempt()
        
        # Second attempt: 2 seconds
        assert manager.get_next_delay() == 2
        manager.record_attempt()
        
        # Third attempt: 4 seconds
        assert manager.get_next_delay() == 4
        manager.record_attempt()
        
        # Fourth attempt: 8 seconds
        assert manager.get_next_delay() == 8
        manager.record_attempt()
        
        # Fifth attempt: should be capped at max_delay_seconds (16)
        assert manager.get_next_delay() == 16
    
    def test_record_attempt(self):
        """Test recording attempts."""
        retry_policy = RetryPolicy()
        manager = RetryManager(retry_policy)
        
        assert manager.attempt_count == 0
        assert manager.last_attempt_time is None
        
        before_time = datetime.now()
        manager.record_attempt()
        after_time = datetime.now()
        
        assert manager.attempt_count == 1
        assert before_time <= manager.last_attempt_time <= after_time
    
    def test_reset(self):
        """Test resetting retry manager."""
        retry_policy = RetryPolicy()
        manager = RetryManager(retry_policy)
        
        manager.record_attempt()
        manager.record_attempt()
        
        assert manager.attempt_count == 2
        assert manager.last_attempt_time is not None
        
        manager.reset()
        
        assert manager.attempt_count == 0
        assert manager.last_attempt_time is None
    
    def test_get_attempt_info(self):
        """Test getting attempt information."""
        retry_policy = RetryPolicy(max_attempts=5, initial_delay_seconds=10)
        manager = RetryManager(retry_policy)
        
        info = manager.get_attempt_info()
        assert info['attempt_count'] == 0
        assert info['max_attempts'] == 5
        assert info['last_attempt_time'] is None
        assert info['next_delay_seconds'] == 0
        
        manager.record_attempt()
        info = manager.get_attempt_info()
        assert info['attempt_count'] == 1
        assert info['next_delay_seconds'] == 10


class TestRecoveryAction:
    """Test cases for RecoveryAction base class."""
    
    def test_recovery_action_initialization(self):
        """Test recovery action initialization."""
        config = {"param1": "value1"}
        action = MockRecoveryAction("test_action", config=config)
        
        assert action.action_type == "test_action"
        assert action.config == config
        assert action.name == "MockRecoveryAction"
    
    def test_recovery_action_execution(self):
        """Test recovery action execution."""
        action = MockRecoveryAction("test_action", should_succeed=True)
        node = NodeConfig(node_id="test_node", node_type="kafka_broker", host="localhost", port=9092)
        
        result = action.execute(node)
        
        assert action.execute_called is True
        assert result.node_id == "test_node"
        assert result.action_type == "test_action"
        assert result.success is True
        assert result.exit_code == 0
    
    def test_recovery_action_failure(self):
        """Test recovery action failure."""
        action = MockRecoveryAction("test_action", should_succeed=False)
        node = NodeConfig(node_id="test_node", node_type="kafka_broker", host="localhost", port=9092)
        
        with pytest.raises(RecoveryError):
            action.execute(node)
    
    def test_recovery_action_validation(self):
        """Test recovery action validation."""
        action = MockRecoveryAction("test_action")
        
        assert action.validate_config() is True
        assert action.validate_called is True
    
    def test_recovery_action_node_type_support(self):
        """Test recovery action node type support."""
        action = MockRecoveryAction("test_action")
        
        assert action.supports_node_type("kafka_broker") is True
        assert action.supports_node_type("zookeeper") is True
        assert action.supports_node_type("unknown") is False
    
    def test_recovery_action_estimated_duration(self):
        """Test recovery action estimated duration."""
        action = MockRecoveryAction("test_action")
        
        assert action.get_estimated_duration() == 30  # Default value


class TestRecoveryEngine:
    """Test cases for RecoveryEngine."""
    
    def test_recovery_engine_initialization(self):
        """Test recovery engine initialization."""
        retry_policy = RetryPolicy(max_attempts=5)
        engine = RecoveryEngine(retry_policy)
        
        assert engine.default_retry_policy == retry_policy
        assert len(engine.recovery_actions) == 0
        assert len(engine.recovery_plugins) == 0
        assert len(engine.recovery_history) == 0
        assert len(engine.active_recoveries) == 0
        assert len(engine.escalation_callbacks) == 0
    
    def test_register_recovery_action(self):
        """Test registering recovery actions."""
        engine = RecoveryEngine()
        action = MockRecoveryAction("test_action")
        
        engine.register_recovery_action("test_action", action)
        
        assert "test_action" in engine.recovery_actions
        assert engine.recovery_actions["test_action"] == action
        assert action.validate_called is True
    
    def test_register_invalid_recovery_action(self):
        """Test registering invalid recovery action."""
        engine = RecoveryEngine()
        action = MockRecoveryAction("test_action")
        action.validate_config = Mock(return_value=False)
        
        with pytest.raises(ValidationError):
            engine.register_recovery_action("test_action", action)
    
    def test_register_recovery_plugin(self):
        """Test registering recovery plugins."""
        engine = RecoveryEngine()
        plugin = MockRecoveryPlugin("TestPlugin")
        
        engine.register_recovery_plugin(plugin)
        
        assert "TestPlugin" in engine.recovery_plugins
        assert engine.recovery_plugins["TestPlugin"] == plugin
    
    def test_register_escalation_callback(self):
        """Test registering escalation callbacks."""
        engine = RecoveryEngine()
        callback = Mock()
        
        engine.register_escalation_callback(callback)
        
        assert callback in engine.escalation_callbacks
    
    def test_successful_recovery_execution(self):
        """Test successful recovery execution."""
        engine = RecoveryEngine()
        action = MockRecoveryAction("test_action", should_succeed=True)
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"]
        )
        
        result = engine.execute_recovery(node, "connection_failure")
        
        assert result.success is True
        assert result.node_id == "test_node"
        assert action.execute_called is True
        
        # Check history was recorded
        history = engine.get_recovery_history("test_node")
        assert len(history) == 1
        assert history[0] == result
        
        # Check active recovery was cleared
        assert "test_node" not in engine.active_recoveries
    
    def test_failed_recovery_with_retries(self):
        """Test failed recovery with retry attempts."""
        retry_policy = RetryPolicy(max_attempts=2, initial_delay_seconds=0.1)
        engine = RecoveryEngine(retry_policy)
        action = MockRecoveryAction("test_action", should_succeed=False, execution_time=0.01)
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # First attempt should fail but not raise exception
        result1 = engine.execute_recovery(node, "connection_failure")
        assert result1.success is False
        
        # Second attempt should also fail but not raise exception
        result2 = engine.execute_recovery(node, "connection_failure")
        assert result2.success is False
        
        # Third attempt should raise RecoveryError (max attempts reached)
        with pytest.raises(RecoveryError, match="Maximum retry attempts reached"):
            engine.execute_recovery(node, "connection_failure")
        
        # Check history
        history = engine.get_recovery_history("test_node")
        assert len(history) == 2
    
    @patch('src.kafka_self_healing.recovery.time.sleep')
    def test_retry_delay(self, mock_sleep):
        """Test retry delay is applied."""
        retry_policy = RetryPolicy(max_attempts=2, initial_delay_seconds=5, backoff_multiplier=2.0)
        engine = RecoveryEngine(retry_policy)
        action = MockRecoveryAction("test_action", should_succeed=False, execution_time=0)  # No execution time to avoid sleep
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # First attempt (no delay)
        engine.execute_recovery(node, "connection_failure")
        mock_sleep.assert_not_called()
        
        # Second attempt (should have delay)
        engine.execute_recovery(node, "connection_failure")
        mock_sleep.assert_called_once_with(5)
    
    def test_recovery_with_plugin(self):
        """Test recovery using plugin."""
        engine = RecoveryEngine()
        plugin = MockRecoveryPlugin("TestPlugin", should_succeed=True)
        engine.register_recovery_plugin(plugin)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092
        )
        
        result = engine.execute_recovery(node, "connection_failure")
        
        assert result.success is True
        assert plugin.execute_called is True
        assert result.action_type == "plugin_TestPlugin"
    
    def test_escalation_callback(self):
        """Test escalation callback is called."""
        retry_policy = RetryPolicy(max_attempts=1)
        engine = RecoveryEngine(retry_policy)
        action = MockRecoveryAction("test_action", should_succeed=False, execution_time=0.01)
        engine.register_recovery_action("test_action", action)
        
        callback = Mock()
        engine.register_escalation_callback(callback)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # First attempt fails
        engine.execute_recovery(node, "connection_failure")
        
        # Second attempt should trigger escalation
        with pytest.raises(RecoveryError):
            engine.execute_recovery(node, "connection_failure")
        
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == "test_node"  # node_id
        assert len(args[1]) == 1  # recovery history
    
    def test_no_suitable_recovery_action(self):
        """Test when no suitable recovery action is found."""
        engine = RecoveryEngine()
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092
        )
        
        with pytest.raises(RecoveryError, match="No suitable recovery action found"):
            engine.execute_recovery(node, "connection_failure")
    
    def test_get_active_recoveries(self):
        """Test getting active recovery information."""
        retry_policy = RetryPolicy(max_attempts=3)
        engine = RecoveryEngine(retry_policy)
        action = MockRecoveryAction("test_action", should_succeed=False, execution_time=0.01)
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # No active recoveries initially
        active = engine.get_active_recoveries()
        assert len(active) == 0
        
        # After failed attempt, should have active recovery
        engine.execute_recovery(node, "connection_failure")
        active = engine.get_active_recoveries()
        assert "test_node" in active
        assert active["test_node"]["attempt_count"] == 1
        assert active["test_node"]["max_attempts"] == 3
    
    def test_cancel_recovery(self):
        """Test cancelling active recovery."""
        retry_policy = RetryPolicy(max_attempts=3)
        engine = RecoveryEngine(retry_policy)
        action = MockRecoveryAction("test_action", should_succeed=False, execution_time=0.01)
        engine.register_recovery_action("test_action", action)
        
        node = NodeConfig(
            node_id="test_node", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"],
            retry_policy=retry_policy
        )
        
        # Start recovery
        engine.execute_recovery(node, "connection_failure")
        assert "test_node" in engine.active_recoveries
        
        # Cancel recovery
        result = engine.cancel_recovery("test_node")
        assert result is True
        assert "test_node" not in engine.active_recoveries
        
        # Try to cancel non-existent recovery
        result = engine.cancel_recovery("non_existent")
        assert result is False
    
    def test_reset_recovery_history(self):
        """Test resetting recovery history."""
        engine = RecoveryEngine()
        action = MockRecoveryAction("test_action", should_succeed=True)
        engine.register_recovery_action("test_action", action)
        
        node1 = NodeConfig(
            node_id="test_node1", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9092,
            recovery_actions=["test_action"]
        )
        
        node2 = NodeConfig(
            node_id="test_node2", 
            node_type="kafka_broker", 
            host="localhost", 
            port=9093,
            recovery_actions=["test_action"]
        )
        
        # Execute recoveries
        engine.execute_recovery(node1, "connection_failure")
        engine.execute_recovery(node2, "connection_failure")
        
        assert len(engine.get_recovery_history("test_node1")) == 1
        assert len(engine.get_recovery_history("test_node2")) == 1
        
        # Reset specific node history
        engine.reset_recovery_history("test_node1")
        assert len(engine.get_recovery_history("test_node1")) == 0
        assert len(engine.get_recovery_history("test_node2")) == 1
        
        # Reset all history
        engine.reset_recovery_history()
        assert len(engine.get_recovery_history("test_node1")) == 0
        assert len(engine.get_recovery_history("test_node2")) == 0


class TestPluginRecoveryAction:
    """Test cases for PluginRecoveryAction."""
    
    def test_plugin_recovery_action_initialization(self):
        """Test plugin recovery action initialization."""
        plugin = MockRecoveryPlugin("TestPlugin")
        action = PluginRecoveryAction(plugin, "connection_failure")
        
        assert action.action_type == "plugin_TestPlugin"
        assert action.plugin == plugin
        assert action.failure_type == "connection_failure"
    
    def test_plugin_recovery_action_execution(self):
        """Test plugin recovery action execution."""
        plugin = MockRecoveryPlugin("TestPlugin", should_succeed=True)
        action = PluginRecoveryAction(plugin, "connection_failure")
        
        node = NodeConfig(node_id="test_node", node_type="kafka_broker", host="localhost", port=9092)
        
        result = action.execute(node)
        
        assert plugin.execute_called is True
        assert result.success is True
        assert result.action_type == "plugin_TestPlugin"
    
    def test_plugin_recovery_action_validation(self):
        """Test plugin recovery action validation."""
        plugin = MockRecoveryPlugin("TestPlugin")
        action = PluginRecoveryAction(plugin, "connection_failure")
        
        assert action.validate_config() is True
        assert plugin.validate_called is True
    
    def test_plugin_recovery_action_node_type_support(self):
        """Test plugin recovery action node type support."""
        plugin = MockRecoveryPlugin("TestPlugin")
        action = PluginRecoveryAction(plugin, "connection_failure")
        
        # Plugin actions assume they handle their own node type checking
        assert action.supports_node_type("kafka_broker") is True
        assert action.supports_node_type("zookeeper") is True
        assert action.supports_node_type("unknown") is True


if __name__ == "__main__":
    pytest.main([__file__])