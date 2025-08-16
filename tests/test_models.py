"""
Unit tests for core data models.
"""

import pytest
from datetime import datetime
from src.kafka_self_healing.models import (
    NodeConfig, NodeStatus, RecoveryResult, RetryPolicy
)
from src.kafka_self_healing.exceptions import ValidationError


class TestRetryPolicy:
    """Test cases for RetryPolicy model."""

    def test_default_values(self):
        """Test default retry policy values."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.initial_delay_seconds == 30
        assert policy.backoff_multiplier == 2.0
        assert policy.max_delay_seconds == 300

    def test_custom_values(self):
        """Test custom retry policy values."""
        policy = RetryPolicy(
            max_attempts=5,
            initial_delay_seconds=60,
            backoff_multiplier=1.5,
            max_delay_seconds=600
        )
        assert policy.max_attempts == 5
        assert policy.initial_delay_seconds == 60
        assert policy.backoff_multiplier == 1.5
        assert policy.max_delay_seconds == 600

    def test_validation_max_attempts_too_low(self):
        """Test validation fails when max_attempts is too low."""
        with pytest.raises(ValidationError, match="max_attempts must be at least 1"):
            RetryPolicy(max_attempts=0)

    def test_validation_negative_initial_delay(self):
        """Test validation fails when initial_delay_seconds is negative."""
        with pytest.raises(ValidationError, match="initial_delay_seconds must be non-negative"):
            RetryPolicy(initial_delay_seconds=-1)

    def test_validation_backoff_multiplier_too_low(self):
        """Test validation fails when backoff_multiplier is too low."""
        with pytest.raises(ValidationError, match="backoff_multiplier must be at least 1.0"):
            RetryPolicy(backoff_multiplier=0.5)

    def test_validation_max_delay_too_low(self):
        """Test validation fails when max_delay_seconds is less than initial_delay_seconds."""
        with pytest.raises(ValidationError, match="max_delay_seconds must be >= initial_delay_seconds"):
            RetryPolicy(initial_delay_seconds=100, max_delay_seconds=50)

    def test_serialization(self):
        """Test to_dict and from_dict methods."""
        policy = RetryPolicy(max_attempts=5, initial_delay_seconds=60)
        data = policy.to_dict()
        
        expected = {
            'max_attempts': 5,
            'initial_delay_seconds': 60,
            'backoff_multiplier': 2.0,
            'max_delay_seconds': 300
        }
        assert data == expected
        
        # Test round-trip
        restored_policy = RetryPolicy.from_dict(data)
        assert restored_policy == policy


class TestNodeConfig:
    """Test cases for NodeConfig model."""

    def test_kafka_broker_config(self):
        """Test valid Kafka broker configuration."""
        config = NodeConfig(
            node_id="broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        assert config.node_id == "broker-1"
        assert config.node_type == "kafka_broker"
        assert config.host == "localhost"
        assert config.port == 9092
        assert config.jmx_port == 9999

    def test_zookeeper_config(self):
        """Test valid Zookeeper configuration."""
        config = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="zk.example.com",
            port=2181
        )
        assert config.node_id == "zk-1"
        assert config.node_type == "zookeeper"
        assert config.host == "zk.example.com"
        assert config.port == 2181
        assert config.jmx_port is None

    def test_validation_empty_node_id(self):
        """Test validation fails when node_id is empty."""
        with pytest.raises(ValidationError, match="node_id cannot be empty"):
            NodeConfig(node_id="", node_type="kafka_broker", host="localhost", port=9092)

    def test_validation_invalid_node_type(self):
        """Test validation fails when node_type is invalid."""
        with pytest.raises(ValidationError, match="node_type must be 'kafka_broker' or 'zookeeper'"):
            NodeConfig(node_id="test", node_type="invalid", host="localhost", port=9092)

    def test_validation_empty_host(self):
        """Test validation fails when host is empty."""
        with pytest.raises(ValidationError, match="host cannot be empty"):
            NodeConfig(node_id="test", node_type="kafka_broker", host="", port=9092)

    def test_validation_invalid_port(self):
        """Test validation fails when port is invalid."""
        with pytest.raises(ValidationError, match="port must be between 1 and 65535"):
            NodeConfig(node_id="test", node_type="kafka_broker", host="localhost", port=0)
        
        with pytest.raises(ValidationError, match="port must be between 1 and 65535"):
            NodeConfig(node_id="test", node_type="kafka_broker", host="localhost", port=65536)

    def test_validation_invalid_jmx_port(self):
        """Test validation fails when jmx_port is invalid."""
        with pytest.raises(ValidationError, match="jmx_port must be between 1 and 65535"):
            NodeConfig(node_id="test", node_type="kafka_broker", host="localhost", port=9092, jmx_port=0)

    def test_serialization(self):
        """Test to_dict and from_dict methods."""
        config = NodeConfig(
            node_id="broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999,
            monitoring_methods=["jmx", "socket"],
            recovery_actions=["restart"]
        )
        data = config.to_dict()
        
        # Test round-trip
        restored_config = NodeConfig.from_dict(data)
        assert restored_config.node_id == config.node_id
        assert restored_config.node_type == config.node_type
        assert restored_config.host == config.host
        assert restored_config.port == config.port
        assert restored_config.jmx_port == config.jmx_port
        assert restored_config.monitoring_methods == config.monitoring_methods
        assert restored_config.recovery_actions == config.recovery_actions


class TestNodeStatus:
    """Test cases for NodeStatus model."""

    def test_healthy_status(self):
        """Test healthy node status."""
        now = datetime.now()
        status = NodeStatus(
            node_id="broker-1",
            is_healthy=True,
            last_check_time=now,
            response_time_ms=50.5,
            monitoring_method="jmx"
        )
        assert status.node_id == "broker-1"
        assert status.is_healthy is True
        assert status.last_check_time == now
        assert status.response_time_ms == 50.5
        assert status.error_message is None
        assert status.monitoring_method == "jmx"

    def test_unhealthy_status(self):
        """Test unhealthy node status."""
        now = datetime.now()
        status = NodeStatus(
            node_id="broker-1",
            is_healthy=False,
            last_check_time=now,
            response_time_ms=0.0,
            error_message="Connection timeout",
            monitoring_method="socket"
        )
        assert status.is_healthy is False
        assert status.error_message == "Connection timeout"

    def test_validation_empty_node_id(self):
        """Test validation fails when node_id is empty."""
        with pytest.raises(ValidationError, match="node_id cannot be empty"):
            NodeStatus(
                node_id="",
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=50.0
            )

    def test_validation_negative_response_time(self):
        """Test validation fails when response_time_ms is negative."""
        with pytest.raises(ValidationError, match="response_time_ms must be non-negative"):
            NodeStatus(
                node_id="test",
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=-1.0
            )

    def test_serialization(self):
        """Test to_dict and from_dict methods."""
        now = datetime.now()
        status = NodeStatus(
            node_id="broker-1",
            is_healthy=True,
            last_check_time=now,
            response_time_ms=50.5,
            error_message="Test error",
            monitoring_method="jmx"
        )
        data = status.to_dict()
        
        # Test round-trip
        restored_status = NodeStatus.from_dict(data)
        assert restored_status.node_id == status.node_id
        assert restored_status.is_healthy == status.is_healthy
        assert restored_status.last_check_time == status.last_check_time
        assert restored_status.response_time_ms == status.response_time_ms
        assert restored_status.error_message == status.error_message
        assert restored_status.monitoring_method == status.monitoring_method


class TestRecoveryResult:
    """Test cases for RecoveryResult model."""

    def test_successful_recovery(self):
        """Test successful recovery result."""
        now = datetime.now()
        result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=now,
            success=True
        )
        assert result.node_id == "broker-1"
        assert result.action_type == "restart"
        assert result.command_executed == "systemctl restart kafka"
        assert result.exit_code == 0
        assert result.success is True

    def test_failed_recovery(self):
        """Test failed recovery result."""
        now = datetime.now()
        result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=1,
            stdout="",
            stderr="Service not found",
            execution_time=now,
            success=False
        )
        assert result.exit_code == 1
        assert result.stderr == "Service not found"
        assert result.success is False

    def test_validation_empty_node_id(self):
        """Test validation fails when node_id is empty."""
        with pytest.raises(ValidationError, match="node_id cannot be empty"):
            RecoveryResult(
                node_id="",
                action_type="restart",
                command_executed="test",
                exit_code=0,
                stdout="",
                stderr="",
                execution_time=datetime.now(),
                success=True
            )

    def test_validation_empty_action_type(self):
        """Test validation fails when action_type is empty."""
        with pytest.raises(ValidationError, match="action_type cannot be empty"):
            RecoveryResult(
                node_id="test",
                action_type="",
                command_executed="test",
                exit_code=0,
                stdout="",
                stderr="",
                execution_time=datetime.now(),
                success=True
            )

    def test_validation_empty_command_executed(self):
        """Test validation fails when command_executed is empty."""
        with pytest.raises(ValidationError, match="command_executed cannot be empty"):
            RecoveryResult(
                node_id="test",
                action_type="restart",
                command_executed="",
                exit_code=0,
                stdout="",
                stderr="",
                execution_time=datetime.now(),
                success=True
            )

    def test_serialization(self):
        """Test to_dict and from_dict methods."""
        now = datetime.now()
        result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Success",
            stderr="",
            execution_time=now,
            success=True
        )
        data = result.to_dict()
        
        # Test round-trip
        restored_result = RecoveryResult.from_dict(data)
        assert restored_result.node_id == result.node_id
        assert restored_result.action_type == result.action_type
        assert restored_result.command_executed == result.command_executed
        assert restored_result.exit_code == result.exit_code
        assert restored_result.stdout == result.stdout
        assert restored_result.stderr == result.stderr
        assert restored_result.execution_time == result.execution_time
        assert restored_result.success == result.success

    def test_json_serialization(self):
        """Test to_json and from_json methods."""
        now = datetime.now()
        result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Success",
            stderr="",
            execution_time=now,
            success=True
        )
        
        # Test JSON round-trip
        json_str = result.to_json()
        restored_result = RecoveryResult.from_json(json_str)
        assert restored_result.node_id == result.node_id
        assert restored_result.execution_time == result.execution_time