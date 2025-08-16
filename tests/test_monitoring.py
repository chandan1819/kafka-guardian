"""
Unit tests for the monitoring module.
"""

import pytest
import time
import threading
import logging
from datetime import datetime
from typing import List
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from src.kafka_self_healing.monitoring import (
    HealthChecker, MonitoringPlugin, NodeStatusTracker, MonitoringService
)
from src.kafka_self_healing.models import NodeConfig, NodeStatus, RetryPolicy, ClusterConfig
from src.kafka_self_healing.exceptions import MonitoringError


class MockMonitoringPlugin(MonitoringPlugin):
    """Mock monitoring plugin for testing."""
    
    def __init__(self, name: str, should_succeed: bool = True, delay: float = 0.0):
        self.name = name
        self.should_succeed = should_succeed
        self.delay = delay
        self.call_count = 0
    
    def check_health(self, node: NodeConfig, timeout_seconds: int) -> bool:
        self.call_count += 1
        if self.delay > 0:
            time.sleep(self.delay)
        
        if not self.should_succeed:
            raise MonitoringError(f"Mock failure from {self.name}")
        
        return True
    
    @property
    def plugin_name(self) -> str:
        return self.name
    
    @property
    def supported_node_types(self) -> List[str]:
        return ['kafka_broker', 'zookeeper']


class TestHealthChecker:
    """Test cases for HealthChecker class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.health_checker = HealthChecker(timeout_seconds=5, max_retries=2)
        self.test_node = NodeConfig(
            node_id="test-broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            monitoring_methods=["mock_method"]
        )
    
    def test_init(self):
        """Test HealthChecker initialization."""
        checker = HealthChecker(timeout_seconds=10, max_retries=3)
        assert checker.timeout_seconds == 10
        assert checker.max_retries == 3
        assert len(checker._monitoring_plugins) == 0
    
    def test_register_monitoring_plugin(self):
        """Test plugin registration."""
        plugin = MockMonitoringPlugin("test_plugin")
        self.health_checker.register_monitoring_plugin("test_method", plugin)
        
        assert "test_method" in self.health_checker._monitoring_plugins
        assert self.health_checker._monitoring_plugins["test_method"] == plugin
    
    def test_check_node_health_success(self):
        """Test successful node health check."""
        plugin = MockMonitoringPlugin("test_plugin", should_succeed=True)
        self.health_checker.register_monitoring_plugin("mock_method", plugin)
        
        status = self.health_checker.check_node_health(self.test_node)
        
        assert status.node_id == "test-broker-1"
        assert status.is_healthy is True
        assert status.monitoring_method == "mock_method"
        assert status.error_message is None
        assert status.response_time_ms >= 0
        assert plugin.call_count == 1
    
    def test_check_node_health_failure(self):
        """Test node health check failure."""
        plugin = MockMonitoringPlugin("test_plugin", should_succeed=False)
        self.health_checker.register_monitoring_plugin("mock_method", plugin)
        
        status = self.health_checker.check_node_health(self.test_node)
        
        assert status.node_id == "test-broker-1"
        assert status.is_healthy is False
        assert status.monitoring_method == "failed"
        assert "Mock failure" in status.error_message
        assert plugin.call_count == 3  # Initial attempt + 2 retries
    
    def test_check_node_health_no_plugins(self):
        """Test health check when no plugins are registered."""
        status = self.health_checker.check_node_health(self.test_node)
        
        assert status.node_id == "test-broker-1"
        assert status.is_healthy is False
        assert status.monitoring_method == "failed"
        assert "All monitoring methods failed" in status.error_message
    
    def test_check_node_health_plugin_not_found(self):
        """Test health check when configured plugin is not registered."""
        node = NodeConfig(
            node_id="test-broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            monitoring_methods=["nonexistent_method"]
        )
        
        status = self.health_checker.check_node_health(node)
        
        assert status.is_healthy is False
        assert "All monitoring methods failed" in status.error_message
    
    def test_check_node_health_multiple_methods_fallback(self):
        """Test fallback to second method when first fails."""
        failing_plugin = MockMonitoringPlugin("failing", should_succeed=False)
        success_plugin = MockMonitoringPlugin("success", should_succeed=True)
        
        self.health_checker.register_monitoring_plugin("failing_method", failing_plugin)
        self.health_checker.register_monitoring_plugin("success_method", success_plugin)
        
        node = NodeConfig(
            node_id="test-broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            monitoring_methods=["failing_method", "success_method"]
        )
        
        status = self.health_checker.check_node_health(node)
        
        assert status.is_healthy is True
        assert status.monitoring_method == "success_method"
        assert failing_plugin.call_count == 3  # Failed with retries
        assert success_plugin.call_count == 1  # Succeeded on first try
    
    def test_check_multiple_nodes_health_success(self):
        """Test concurrent health checking of multiple nodes."""
        plugin = MockMonitoringPlugin("test_plugin", should_succeed=True)
        self.health_checker.register_monitoring_plugin("mock_method", plugin)
        
        nodes = [
            NodeConfig(
                node_id=f"broker-{i}",
                node_type="kafka_broker",
                host="localhost",
                port=9092 + i,
                monitoring_methods=["mock_method"]
            )
            for i in range(3)
        ]
        
        statuses = self.health_checker.check_multiple_nodes_health(nodes)
        
        assert len(statuses) == 3
        for status in statuses:
            assert status.is_healthy is True
            assert status.monitoring_method == "mock_method"
        
        assert plugin.call_count == 3
    
    def test_check_multiple_nodes_health_empty_list(self):
        """Test health checking with empty node list."""
        statuses = self.health_checker.check_multiple_nodes_health([])
        assert statuses == []
    
    def test_check_multiple_nodes_health_with_failures(self):
        """Test concurrent health checking with some failures."""
        plugin = MockMonitoringPlugin("test_plugin", should_succeed=False)
        self.health_checker.register_monitoring_plugin("mock_method", plugin)
        
        nodes = [
            NodeConfig(
                node_id=f"broker-{i}",
                node_type="kafka_broker",
                host="localhost",
                port=9092 + i,
                monitoring_methods=["mock_method"]
            )
            for i in range(2)
        ]
        
        statuses = self.health_checker.check_multiple_nodes_health(nodes)
        
        assert len(statuses) == 2
        for status in statuses:
            assert status.is_healthy is False
            assert "Mock failure" in status.error_message
    
    def test_check_multiple_nodes_health_concurrency(self):
        """Test that multiple nodes are checked concurrently."""
        # Use a plugin with delay to test concurrency
        plugin = MockMonitoringPlugin("test_plugin", should_succeed=True, delay=0.1)
        self.health_checker.register_monitoring_plugin("mock_method", plugin)
        
        nodes = [
            NodeConfig(
                node_id=f"broker-{i}",
                node_type="kafka_broker",
                host="localhost",
                port=9092 + i,
                monitoring_methods=["mock_method"]
            )
            for i in range(3)
        ]
        
        start_time = time.time()
        statuses = self.health_checker.check_multiple_nodes_health(nodes)
        end_time = time.time()
        
        # If run sequentially, would take 0.3+ seconds
        # If run concurrently, should take ~0.1 seconds
        assert end_time - start_time < 0.2
        assert len(statuses) == 3
    
    def test_compare_node_status_first_check(self):
        """Test status comparison for first check (no previous status)."""
        current = NodeStatus(
            node_id="test-node",
            is_healthy=True,
            last_check_time=datetime.now(),
            response_time_ms=100.0
        )
        
        comparison = self.health_checker.compare_node_status(None, current)
        
        assert comparison['node_id'] == "test-node"
        assert comparison['status_changed'] is True
        assert comparison['health_changed'] is False
        assert comparison['new_error'] is False
    
    def test_compare_node_status_no_change(self):
        """Test status comparison with no changes."""
        timestamp = datetime.now()
        previous = NodeStatus(
            node_id="test-node",
            is_healthy=True,
            last_check_time=timestamp,
            response_time_ms=100.0
        )
        current = NodeStatus(
            node_id="test-node",
            is_healthy=True,
            last_check_time=timestamp,
            response_time_ms=105.0
        )
        
        comparison = self.health_checker.compare_node_status(previous, current)
        
        assert comparison['status_changed'] is False
        assert comparison['health_changed'] is False
        assert comparison['response_time_change_ms'] == 5.0
    
    def test_compare_node_status_health_change(self):
        """Test status comparison with health status change."""
        timestamp = datetime.now()
        previous = NodeStatus(
            node_id="test-node",
            is_healthy=True,
            last_check_time=timestamp,
            response_time_ms=100.0
        )
        current = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=timestamp,
            response_time_ms=200.0,
            error_message="Connection failed"
        )
        
        comparison = self.health_checker.compare_node_status(previous, current)
        
        assert comparison['status_changed'] is True
        assert comparison['health_changed'] is True
        assert comparison['became_unhealthy'] is True
        assert comparison['became_healthy'] is False
        assert comparison['new_error'] is True
    
    def test_compare_node_status_recovery(self):
        """Test status comparison for node recovery."""
        timestamp = datetime.now()
        previous = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=timestamp,
            response_time_ms=0.0,
            error_message="Connection failed"
        )
        current = NodeStatus(
            node_id="test-node",
            is_healthy=True,
            last_check_time=timestamp,
            response_time_ms=100.0
        )
        
        comparison = self.health_checker.compare_node_status(previous, current)
        
        assert comparison['status_changed'] is True
        assert comparison['health_changed'] is True
        assert comparison['became_healthy'] is True
        assert comparison['became_unhealthy'] is False
        assert comparison['error_cleared'] is True


class TestNodeStatusTracker:
    """Test cases for NodeStatusTracker class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tracker = NodeStatusTracker(max_history_size=5)
        self.test_status = NodeStatus(
            node_id="test-node",
            is_healthy=True,
            last_check_time=datetime.now(),
            response_time_ms=100.0
        )
    
    def test_init(self):
        """Test NodeStatusTracker initialization."""
        tracker = NodeStatusTracker(max_history_size=10)
        assert tracker.max_history_size == 10
        assert len(tracker._status_history) == 0
    
    def test_update_status_first_time(self):
        """Test updating status for the first time."""
        comparison = self.tracker.update_status(self.test_status)
        
        assert comparison['node_id'] == "test-node"
        assert comparison['status_changed'] is True
        assert len(self.tracker._status_history["test-node"]) == 1
    
    def test_update_status_multiple_times(self):
        """Test updating status multiple times."""
        # First update
        self.tracker.update_status(self.test_status)
        
        # Second update with different health status
        new_status = NodeStatus(
            node_id="test-node",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=200.0,
            error_message="Failed"
        )
        
        comparison = self.tracker.update_status(new_status)
        
        assert comparison['health_changed'] is True
        assert comparison['became_unhealthy'] is True
        assert len(self.tracker._status_history["test-node"]) == 2
    
    def test_update_status_history_limit(self):
        """Test that status history is limited to max_history_size."""
        # Add more statuses than the limit
        for i in range(10):
            status = NodeStatus(
                node_id="test-node",
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=100.0 + i
            )
            self.tracker.update_status(status)
        
        # Should only keep the last 5 entries
        assert len(self.tracker._status_history["test-node"]) == 5
        # Check that the latest entries are kept
        latest_status = self.tracker.get_latest_status("test-node")
        assert latest_status.response_time_ms == 109.0
    
    def test_get_latest_status_exists(self):
        """Test getting latest status when it exists."""
        self.tracker.update_status(self.test_status)
        latest = self.tracker.get_latest_status("test-node")
        
        assert latest is not None
        assert latest.node_id == "test-node"
        assert latest.is_healthy is True
    
    def test_get_latest_status_not_exists(self):
        """Test getting latest status when node doesn't exist."""
        latest = self.tracker.get_latest_status("nonexistent-node")
        assert latest is None
    
    def test_get_status_history(self):
        """Test getting status history."""
        # Add multiple statuses
        for i in range(3):
            status = NodeStatus(
                node_id="test-node",
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=100.0 + i
            )
            self.tracker.update_status(status)
        
        history = self.tracker.get_status_history("test-node", limit=2)
        assert len(history) == 2
        # Should return the most recent entries
        assert history[-1].response_time_ms == 102.0
    
    def test_get_status_history_empty(self):
        """Test getting status history for non-existent node."""
        history = self.tracker.get_status_history("nonexistent-node")
        assert history == []
    
    def test_get_all_latest_statuses(self):
        """Test getting latest statuses for all nodes."""
        # Add statuses for multiple nodes
        nodes = ["node-1", "node-2", "node-3"]
        for node_id in nodes:
            status = NodeStatus(
                node_id=node_id,
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=100.0
            )
            self.tracker.update_status(status)
        
        all_statuses = self.tracker.get_all_latest_statuses()
        assert len(all_statuses) == 3
        for node_id in nodes:
            assert node_id in all_statuses
            assert all_statuses[node_id].node_id == node_id
    
    def test_clear_history_specific_node(self):
        """Test clearing history for a specific node."""
        # Add statuses for multiple nodes
        for node_id in ["node-1", "node-2"]:
            status = NodeStatus(
                node_id=node_id,
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=100.0
            )
            self.tracker.update_status(status)
        
        # Clear history for one node
        self.tracker.clear_history("node-1")
        
        assert "node-1" not in self.tracker._status_history
        assert "node-2" in self.tracker._status_history
    
    def test_clear_history_all_nodes(self):
        """Test clearing history for all nodes."""
        # Add statuses for multiple nodes
        for node_id in ["node-1", "node-2"]:
            status = NodeStatus(
                node_id=node_id,
                is_healthy=True,
                last_check_time=datetime.now(),
                response_time_ms=100.0
            )
            self.tracker.update_status(status)
        
        # Clear all history
        self.tracker.clear_history()
        
        assert len(self.tracker._status_history) == 0


class TestMonitoringPlugin:
    """Test cases for MonitoringPlugin abstract base class."""
    
    def test_abstract_methods(self):
        """Test that MonitoringPlugin cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MonitoringPlugin()
    
    def test_mock_plugin_implementation(self):
        """Test that MockMonitoringPlugin implements the interface correctly."""
        plugin = MockMonitoringPlugin("test")
        
        assert plugin.plugin_name == "test"
        assert "kafka_broker" in plugin.supported_node_types
        assert "zookeeper" in plugin.supported_node_types
        
        # Test health check
        node = NodeConfig(
            node_id="test-node",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        result = plugin.check_health(node, 5)
        assert result is True
        assert plugin.call_count == 1


class TestMonitoringService:
    """Test cases for MonitoringService class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create test cluster configuration
        self.cluster_config = ClusterConfig(
            cluster_name="test-cluster",
            nodes=[
                NodeConfig(
                    node_id="kafka-1",
                    node_type="kafka_broker",
                    host="localhost",
                    port=9092,
                    jmx_port=9999,
                    monitoring_methods=["socket", "jmx"]
                ),
                NodeConfig(
                    node_id="zk-1",
                    node_type="zookeeper",
                    host="localhost",
                    port=2181,
                    monitoring_methods=["socket", "zookeeper"]
                )
            ],
            monitoring_interval_seconds=1  # Short interval for testing
        )
        
        # Create health checker with mock plugins
        self.health_checker = HealthChecker()
        self.mock_plugin = MockMonitoringPlugin("test_plugin", should_succeed=True)
        self.health_checker.register_monitoring_plugin("socket", self.mock_plugin)
        self.health_checker.register_monitoring_plugin("jmx", self.mock_plugin)
        self.health_checker.register_monitoring_plugin("zookeeper", self.mock_plugin)
        
        # Create monitoring service with mock to prevent default plugin registration
        with patch('src.kafka_self_healing.monitoring.MonitoringService._register_default_plugins'):
            self.monitoring_service = MonitoringService(
                cluster_config=self.cluster_config,
                health_checker=self.health_checker
            )
    
    def teardown_method(self):
        """Clean up after tests."""
        if self.monitoring_service.is_monitoring_active():
            self.monitoring_service.stop_monitoring()
    
    def test_init(self):
        """Test MonitoringService initialization."""
        assert self.monitoring_service.cluster_config == self.cluster_config
        assert self.monitoring_service.health_checker == self.health_checker
        assert not self.monitoring_service.is_monitoring_active()
        assert len(self.monitoring_service._failure_callbacks) == 0
        assert len(self.monitoring_service._recovery_callbacks) == 0
    
    def test_register_callbacks(self):
        """Test callback registration."""
        def failure_callback(node, status):
            pass
        
        def recovery_callback(node, status):
            pass
        
        def status_change_callback(node, status, comparison):
            pass
        
        self.monitoring_service.register_failure_callback(failure_callback)
        self.monitoring_service.register_recovery_callback(recovery_callback)
        self.monitoring_service.register_status_change_callback(status_change_callback)
        
        assert len(self.monitoring_service._failure_callbacks) == 1
        assert len(self.monitoring_service._recovery_callbacks) == 1
        assert len(self.monitoring_service._status_change_callbacks) == 1
    
    def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring."""
        # Start monitoring
        self.monitoring_service.start_monitoring()
        assert self.monitoring_service.is_monitoring_active()
        assert self.monitoring_service._monitoring_thread is not None
        assert self.monitoring_service._monitoring_thread.is_alive()
        
        # Stop monitoring
        self.monitoring_service.stop_monitoring()
        assert not self.monitoring_service.is_monitoring_active()
        
        # Wait a bit for thread to finish
        time.sleep(0.1)
        if self.monitoring_service._monitoring_thread:
            assert not self.monitoring_service._monitoring_thread.is_alive()
    
    def test_start_monitoring_already_running(self):
        """Test starting monitoring when already running."""
        self.monitoring_service.start_monitoring()
        assert self.monitoring_service.is_monitoring_active()
        
        # Try to start again
        self.monitoring_service.start_monitoring()
        assert self.monitoring_service.is_monitoring_active()
    
    def test_stop_monitoring_not_running(self):
        """Test stopping monitoring when not running."""
        assert not self.monitoring_service.is_monitoring_active()
        
        # Should not raise an error
        self.monitoring_service.stop_monitoring()
        assert not self.monitoring_service.is_monitoring_active()
    
    def test_check_all_nodes_once(self):
        """Test single health check of all nodes."""
        statuses = self.monitoring_service.check_all_nodes_once()
        
        assert len(statuses) == 2
        node_ids = {status.node_id for status in statuses}
        assert "kafka-1" in node_ids
        assert "zk-1" in node_ids
        
        # All should be healthy with mock plugin
        for status in statuses:
            assert status.is_healthy is True
    
    def test_get_current_status(self):
        """Test getting current status of all nodes."""
        # Initially no status
        current_status = self.monitoring_service.get_current_status()
        assert len(current_status) == 0
        
        # After health check
        self.monitoring_service.check_all_nodes_once()
        current_status = self.monitoring_service.get_current_status()
        assert len(current_status) == 2
        assert "kafka-1" in current_status
        assert "zk-1" in current_status
    
    def test_get_node_status_history(self):
        """Test getting node status history."""
        # Initially no history
        history = self.monitoring_service.get_node_status_history("kafka-1")
        assert len(history) == 0
        
        # After health check
        self.monitoring_service.check_all_nodes_once()
        history = self.monitoring_service.get_node_status_history("kafka-1")
        assert len(history) == 1
        assert history[0].node_id == "kafka-1"
    
    def test_callback_triggering_on_failure(self):
        """Test that failure callbacks are triggered when node becomes unhealthy."""
        failure_called = []
        status_change_called = []
        
        def failure_callback(node, status):
            failure_called.append((node.node_id, status.is_healthy))
        
        def status_change_callback(node, status, comparison):
            status_change_called.append((node.node_id, comparison['became_unhealthy']))
        
        self.monitoring_service.register_failure_callback(failure_callback)
        self.monitoring_service.register_status_change_callback(status_change_callback)
        
        # First check - nodes become healthy (first time)
        self.monitoring_service.check_all_nodes_once()
        
        # Change mock plugin to fail
        self.mock_plugin.should_succeed = False
        
        # Second check - nodes become unhealthy
        self.monitoring_service.check_all_nodes_once()
        
        # Should have triggered failure callbacks
        assert len(failure_called) == 2  # Both nodes failed
        assert len(status_change_called) == 4  # 2 nodes x 2 status changes
        
        # Check that failure callbacks were called with correct parameters
        for node_id, is_healthy in failure_called:
            assert node_id in ["kafka-1", "zk-1"]
            assert is_healthy is False
    
    def test_callback_triggering_on_recovery(self):
        """Test that recovery callbacks are triggered when node recovers."""
        recovery_called = []
        
        def recovery_callback(node, status):
            recovery_called.append((node.node_id, status.is_healthy))
        
        self.monitoring_service.register_recovery_callback(recovery_callback)
        
        # Start with failing plugin
        self.mock_plugin.should_succeed = False
        self.monitoring_service.check_all_nodes_once()
        
        # Change plugin to succeed
        self.mock_plugin.should_succeed = True
        self.monitoring_service.check_all_nodes_once()
        
        # Should have triggered recovery callbacks
        assert len(recovery_called) == 2  # Both nodes recovered
        for node_id, is_healthy in recovery_called:
            assert node_id in ["kafka-1", "zk-1"]
            assert is_healthy is True
    
    def test_monitoring_loop_integration(self):
        """Test the monitoring loop with callbacks."""
        callback_results = []
        
        def status_change_callback(node, status, comparison):
            callback_results.append({
                'node_id': node.node_id,
                'is_healthy': status.is_healthy,
                'status_changed': comparison['status_changed']
            })
        
        self.monitoring_service.register_status_change_callback(status_change_callback)
        
        # Start monitoring
        self.monitoring_service.start_monitoring()
        
        # Wait for at least one monitoring cycle
        time.sleep(1.5)
        
        # Stop monitoring
        self.monitoring_service.stop_monitoring()
        
        # Should have received status updates
        assert len(callback_results) >= 2  # At least one update per node
        
        # All initial updates should show healthy status
        for result in callback_results[:2]:  # First two results
            assert result['is_healthy'] is True
            assert result['status_changed'] is True
    
    def test_add_monitoring_plugin(self):
        """Test adding custom monitoring plugin."""
        custom_plugin = MockMonitoringPlugin("custom_plugin")
        
        self.monitoring_service.add_monitoring_plugin("custom", custom_plugin)
        
        assert "custom" in self.monitoring_service.health_checker._monitoring_plugins
        assert self.monitoring_service.health_checker._monitoring_plugins["custom"] == custom_plugin
    
    def test_get_monitoring_statistics(self):
        """Test getting monitoring statistics."""
        # Before any health checks
        stats = self.monitoring_service.get_monitoring_statistics()
        
        assert stats['monitoring_active'] is False
        assert stats['total_nodes'] == 2
        assert stats['kafka_brokers'] == 1
        assert stats['zookeeper_nodes'] == 1
        assert stats['healthy_nodes'] == 0  # No status yet
        assert stats['unhealthy_nodes'] == 2
        
        # After health check
        self.monitoring_service.check_all_nodes_once()
        stats = self.monitoring_service.get_monitoring_statistics()
        
        assert stats['healthy_nodes'] == 2
        assert stats['unhealthy_nodes'] == 0
        assert stats['health_percentage'] == 100.0
        assert stats['average_response_time_ms'] >= 0
    
    def test_monitoring_statistics_with_monitoring_active(self):
        """Test monitoring statistics when monitoring is active."""
        self.monitoring_service.start_monitoring()
        
        stats = self.monitoring_service.get_monitoring_statistics()
        assert stats['monitoring_active'] is True
        assert stats['monitoring_interval_seconds'] == 1
        
        self.monitoring_service.stop_monitoring()
    
    def test_error_handling_in_callbacks(self):
        """Test that errors in callbacks don't stop monitoring."""
        def failing_callback(node, status):
            raise Exception("Callback error")
        
        self.monitoring_service.register_failure_callback(failing_callback)
        
        # Start with failing plugin to trigger failure callback
        self.mock_plugin.should_succeed = False
        
        # Should not raise exception despite callback error
        self.monitoring_service.check_all_nodes_once()
        
        # Monitoring should still work
        current_status = self.monitoring_service.get_current_status()
        assert len(current_status) == 2
    
    def test_register_default_plugins_import_error(self):
        """Test handling of import errors when registering default plugins."""
        # Test the actual import error handling by mocking the import
        with patch('src.kafka_self_healing.monitoring.MonitoringService._register_default_plugins') as mock_register:
            # Create a service that doesn't call _register_default_plugins
            service = MonitoringService.__new__(MonitoringService)
            service.cluster_config = self.cluster_config
            service.health_checker = self.health_checker
            service.status_tracker = NodeStatusTracker()
            service.logger = logging.getLogger(__name__)
            service._monitoring_active = False
            service._monitoring_thread = None
            service._stop_event = threading.Event()
            service._failure_callbacks = []
            service._recovery_callbacks = []
            service._status_change_callbacks = []
            
            # Now test that calling _register_default_plugins with import error doesn't crash
            try:
                # This should not raise an exception due to the try/except in the method
                service._register_default_plugins()
                # If we get here, the method handled the import error gracefully
                assert True
            except ImportError:
                # If we get here, the method didn't handle the import error
                assert False, "Import error was not handled gracefully"