"""
Core monitoring functionality for the Kafka self-healing system.
"""

import asyncio
import time
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
import logging

from .models import NodeConfig, NodeStatus, ClusterConfig
from .exceptions import MonitoringError


class HealthChecker:
    """
    Core health checking framework with timeout and retry logic.
    Supports concurrent health checking for multiple nodes.
    """
    
    def __init__(self, timeout_seconds: int = 10, max_retries: int = 2):
        """
        Initialize health checker.
        
        Args:
            timeout_seconds: Timeout for individual health checks
            max_retries: Maximum number of retries for failed checks
        """
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        self._monitoring_plugins: Dict[str, 'MonitoringPlugin'] = {}
    
    def register_monitoring_plugin(self, method_name: str, plugin: 'MonitoringPlugin') -> None:
        """Register a monitoring plugin for a specific method."""
        self._monitoring_plugins[method_name] = plugin
        self.logger.info(f"Registered monitoring plugin: {method_name}")
    
    def check_node_health(self, node: NodeConfig) -> NodeStatus:
        """
        Check health of a single node using configured monitoring methods.
        
        Args:
            node: Node configuration to check
            
        Returns:
            NodeStatus with health information
        """
        start_time = time.time()
        
        # Try each monitoring method until one succeeds or all fail
        last_error = None
        for method in node.monitoring_methods:
            if method not in self._monitoring_plugins:
                self.logger.warning(f"Monitoring method '{method}' not available for node {node.node_id}")
                continue
                
            plugin = self._monitoring_plugins[method]
            
            # Retry logic for each method
            for attempt in range(self.max_retries + 1):
                try:
                    self.logger.debug(f"Checking {node.node_id} using {method} (attempt {attempt + 1})")
                    
                    is_healthy = plugin.check_health(node, self.timeout_seconds)
                    response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                    
                    return NodeStatus(
                        node_id=node.node_id,
                        is_healthy=is_healthy,
                        last_check_time=datetime.now(),
                        response_time_ms=response_time,
                        monitoring_method=method
                    )
                    
                except Exception as e:
                    last_error = str(e)
                    self.logger.debug(f"Health check failed for {node.node_id} using {method}: {e}")
                    
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (attempt + 1))  # Brief backoff between retries
        
        # All methods failed
        response_time = (time.time() - start_time) * 1000
        return NodeStatus(
            node_id=node.node_id,
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=response_time,
            error_message=last_error or "All monitoring methods failed",
            monitoring_method="failed"
        )
    
    def check_multiple_nodes_health(self, nodes: List[NodeConfig], max_workers: int = 10) -> List[NodeStatus]:
        """
        Check health of multiple nodes concurrently.
        
        Args:
            nodes: List of node configurations to check
            max_workers: Maximum number of concurrent health checks
            
        Returns:
            List of NodeStatus results
        """
        if not nodes:
            return []
        
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all health check tasks
            future_to_node = {
                executor.submit(self.check_node_health, node): node 
                for node in nodes
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_node):
                node = future_to_node[future]
                try:
                    status = future.result()
                    results.append(status)
                    self.logger.debug(f"Health check completed for {node.node_id}: {status.is_healthy}")
                except Exception as e:
                    self.logger.error(f"Health check failed for {node.node_id}: {e}")
                    # Create a failed status
                    results.append(NodeStatus(
                        node_id=node.node_id,
                        is_healthy=False,
                        last_check_time=datetime.now(),
                        response_time_ms=0.0,
                        error_message=str(e),
                        monitoring_method="error"
                    ))
        
        return results
    
    def compare_node_status(self, previous: Optional[NodeStatus], current: NodeStatus) -> Dict[str, Any]:
        """
        Compare current node status with previous status to detect changes.
        
        Args:
            previous: Previous node status (can be None for first check)
            current: Current node status
            
        Returns:
            Dictionary with comparison results
        """
        comparison = {
            'node_id': current.node_id,
            'status_changed': False,
            'health_changed': False,
            'became_healthy': False,
            'became_unhealthy': False,
            'response_time_change_ms': 0.0,
            'error_cleared': False,
            'new_error': False
        }
        
        if previous is None:
            comparison['status_changed'] = True
            comparison['new_error'] = not current.is_healthy
            return comparison
        
        # Check for health status changes
        if previous.is_healthy != current.is_healthy:
            comparison['status_changed'] = True
            comparison['health_changed'] = True
            comparison['became_healthy'] = current.is_healthy
            comparison['became_unhealthy'] = not current.is_healthy
        
        # Check for error message changes
        if previous.error_message != current.error_message:
            comparison['status_changed'] = True
            if previous.error_message and not current.error_message:
                comparison['error_cleared'] = True
            elif not previous.error_message and current.error_message:
                comparison['new_error'] = True
        
        # Calculate response time change
        comparison['response_time_change_ms'] = current.response_time_ms - previous.response_time_ms
        
        return comparison


class MonitoringPlugin(ABC):
    """
    Abstract base class for monitoring plugins.
    All monitoring plugins must implement the check_health method.
    """
    
    @abstractmethod
    def check_health(self, node: NodeConfig, timeout_seconds: int) -> bool:
        """
        Check if a node is healthy.
        
        Args:
            node: Node configuration to check
            timeout_seconds: Timeout for the health check
            
        Returns:
            True if node is healthy, False otherwise
            
        Raises:
            MonitoringError: If health check cannot be performed
        """
        pass
    
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Return the name of this monitoring plugin."""
        pass
    
    @property
    @abstractmethod
    def supported_node_types(self) -> List[str]:
        """Return list of supported node types (e.g., ['kafka_broker', 'zookeeper'])."""
        pass


class NodeStatusTracker:
    """
    Tracks node status history and provides comparison functionality.
    """
    
    def __init__(self, max_history_size: int = 100):
        """
        Initialize status tracker.
        
        Args:
            max_history_size: Maximum number of status entries to keep per node
        """
        self.max_history_size = max_history_size
        self._status_history: Dict[str, List[NodeStatus]] = {}
        self.logger = logging.getLogger(__name__)
    
    def update_status(self, status: NodeStatus) -> Dict[str, Any]:
        """
        Update status for a node and return comparison with previous status.
        
        Args:
            status: New status to record
            
        Returns:
            Comparison results with previous status
        """
        node_id = status.node_id
        
        # Get previous status
        previous_status = self.get_latest_status(node_id)
        
        # Add new status to history
        if node_id not in self._status_history:
            self._status_history[node_id] = []
        
        self._status_history[node_id].append(status)
        
        # Trim history if needed
        if len(self._status_history[node_id]) > self.max_history_size:
            self._status_history[node_id] = self._status_history[node_id][-self.max_history_size:]
        
        # Create health checker instance to use comparison method
        health_checker = HealthChecker()
        comparison = health_checker.compare_node_status(previous_status, status)
        
        if comparison['status_changed']:
            self.logger.info(f"Status changed for {node_id}: healthy={status.is_healthy}")
        
        return comparison
    
    def get_latest_status(self, node_id: str) -> Optional[NodeStatus]:
        """Get the most recent status for a node."""
        if node_id not in self._status_history or not self._status_history[node_id]:
            return None
        return self._status_history[node_id][-1]
    
    def get_status_history(self, node_id: str, limit: int = 10) -> List[NodeStatus]:
        """Get recent status history for a node."""
        if node_id not in self._status_history:
            return []
        return self._status_history[node_id][-limit:]
    
    def get_all_latest_statuses(self) -> Dict[str, NodeStatus]:
        """Get the latest status for all tracked nodes."""
        result = {}
        for node_id in self._status_history:
            latest = self.get_latest_status(node_id)
            if latest:
                result[node_id] = latest
        return result
    
    def clear_history(self, node_id: Optional[str] = None) -> None:
        """Clear status history for a specific node or all nodes."""
        if node_id:
            if node_id in self._status_history:
                del self._status_history[node_id]
        else:
            self._status_history.clear()


class MonitoringService:
    """
    Main monitoring service that orchestrates all monitoring plugins.
    Provides failure detection logic, callback registration, and configurable monitoring intervals.
    """
    
    def __init__(self, cluster_config: ClusterConfig, health_checker: Optional[HealthChecker] = None):
        """
        Initialize monitoring service.
        
        Args:
            cluster_config: Cluster configuration with nodes and monitoring settings
            health_checker: Optional health checker instance (creates default if None)
        """
        self.cluster_config = cluster_config
        self.health_checker = health_checker or HealthChecker()
        self.status_tracker = NodeStatusTracker()
        self.logger = logging.getLogger(__name__)
        
        # Monitoring state
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Callback management
        self._failure_callbacks: List[Callable[[NodeConfig, NodeStatus], None]] = []
        self._recovery_callbacks: List[Callable[[NodeConfig, NodeStatus], None]] = []
        self._status_change_callbacks: List[Callable[[NodeConfig, NodeStatus, Dict[str, Any]], None]] = []
        
        # Register default monitoring plugins
        self._register_default_plugins()
    
    def _register_default_plugins(self) -> None:
        """Register default monitoring plugins."""
        try:
            from .monitoring_plugins import JMXMonitoringPlugin, SocketMonitoringPlugin, ZookeeperMonitoringPlugin
            
            # Register JMX monitoring for Kafka brokers
            jmx_plugin = JMXMonitoringPlugin()
            self.health_checker.register_monitoring_plugin("jmx", jmx_plugin)
            
            # Register socket monitoring for all node types
            socket_plugin = SocketMonitoringPlugin()
            self.health_checker.register_monitoring_plugin("socket", socket_plugin)
            
            # Register Zookeeper monitoring for Zookeeper nodes
            zk_plugin = ZookeeperMonitoringPlugin()
            self.health_checker.register_monitoring_plugin("zookeeper", zk_plugin)
            
            self.logger.info("Default monitoring plugins registered")
            
        except ImportError as e:
            self.logger.warning(f"Could not import monitoring plugins: {e}")
        except Exception as e:
            self.logger.error(f"Error registering default plugins: {e}")
    
    def register_failure_callback(self, callback: Callable[[NodeConfig, NodeStatus], None]) -> None:
        """
        Register a callback to be called when a node failure is detected.
        
        Args:
            callback: Function to call with (node_config, node_status) when failure detected
        """
        self._failure_callbacks.append(callback)
        self.logger.info(f"Registered failure callback: {callback.__name__}")
    
    def register_recovery_callback(self, callback: Callable[[NodeConfig, NodeStatus], None]) -> None:
        """
        Register a callback to be called when a node recovers.
        
        Args:
            callback: Function to call with (node_config, node_status) when recovery detected
        """
        self._recovery_callbacks.append(callback)
        self.logger.info(f"Registered recovery callback: {callback.__name__}")
    
    def register_status_change_callback(self, callback: Callable[[NodeConfig, NodeStatus, Dict[str, Any]], None]) -> None:
        """
        Register a callback to be called when any node status changes.
        
        Args:
            callback: Function to call with (node_config, node_status, comparison) when status changes
        """
        self._status_change_callbacks.append(callback)
        self.logger.info(f"Registered status change callback: {callback.__name__}")
    
    def start_monitoring(self) -> None:
        """Start the monitoring service."""
        if self._monitoring_active:
            self.logger.warning("Monitoring service is already running")
            return
        
        self.logger.info("Starting monitoring service")
        self._monitoring_active = True
        self._stop_event.clear()
        
        # Start monitoring thread
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()
        
        self.logger.info(f"Monitoring service started for {len(self.cluster_config.nodes)} nodes")
    
    def stop_monitoring(self) -> None:
        """Stop the monitoring service."""
        if not self._monitoring_active:
            self.logger.warning("Monitoring service is not running")
            return
        
        self.logger.info("Stopping monitoring service")
        self._monitoring_active = False
        self._stop_event.set()
        
        # Wait for monitoring thread to finish
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=10)
            if self._monitoring_thread.is_alive():
                self.logger.warning("Monitoring thread did not stop gracefully")
        
        self.logger.info("Monitoring service stopped")
    
    def is_monitoring_active(self) -> bool:
        """Check if monitoring is currently active."""
        return self._monitoring_active
    
    def get_current_status(self) -> Dict[str, NodeStatus]:
        """Get current status of all monitored nodes."""
        return self.status_tracker.get_all_latest_statuses()
    
    def get_node_status_history(self, node_id: str, limit: int = 10) -> List[NodeStatus]:
        """Get status history for a specific node."""
        return self.status_tracker.get_status_history(node_id, limit)
    
    def check_all_nodes_once(self) -> List[NodeStatus]:
        """
        Perform a single health check of all nodes.
        
        Returns:
            List of current node statuses
        """
        self.logger.debug("Performing single health check of all nodes")
        
        # Check all nodes concurrently
        statuses = self.health_checker.check_multiple_nodes_health(
            self.cluster_config.nodes,
            max_workers=min(len(self.cluster_config.nodes), 10)
        )
        
        # Process each status
        for status in statuses:
            node = self.cluster_config.get_node_by_id(status.node_id)
            if node:
                self._process_node_status(node, status)
        
        return statuses
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs in a separate thread."""
        self.logger.info("Monitoring loop started")
        
        while self._monitoring_active and not self._stop_event.is_set():
            try:
                # Perform health checks
                self.check_all_nodes_once()
                
                # Wait for next monitoring interval
                if self._stop_event.wait(timeout=self.cluster_config.monitoring_interval_seconds):
                    break  # Stop event was set
                    
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                # Continue monitoring even if there's an error
                time.sleep(5)  # Brief pause before retrying
        
        self.logger.info("Monitoring loop stopped")
    
    def _process_node_status(self, node: NodeConfig, status: NodeStatus) -> None:
        """
        Process a node status update and trigger appropriate callbacks.
        
        Args:
            node: Node configuration
            status: Current node status
        """
        try:
            # Update status tracker and get comparison
            comparison = self.status_tracker.update_status(status)
            
            # Trigger status change callbacks if status changed
            if comparison['status_changed']:
                for callback in self._status_change_callbacks:
                    try:
                        callback(node, status, comparison)
                    except Exception as e:
                        self.logger.error(f"Error in status change callback: {e}")
            
            # Trigger specific callbacks based on status changes
            if comparison['became_unhealthy']:
                self.logger.warning(f"Node {node.node_id} became unhealthy: {status.error_message}")
                for callback in self._failure_callbacks:
                    try:
                        callback(node, status)
                    except Exception as e:
                        self.logger.error(f"Error in failure callback: {e}")
            
            elif comparison['became_healthy']:
                self.logger.info(f"Node {node.node_id} recovered")
                for callback in self._recovery_callbacks:
                    try:
                        callback(node, status)
                    except Exception as e:
                        self.logger.error(f"Error in recovery callback: {e}")
        
        except Exception as e:
            self.logger.error(f"Error processing status for node {node.node_id}: {e}")
    
    def add_monitoring_plugin(self, method_name: str, plugin: MonitoringPlugin) -> None:
        """
        Add a custom monitoring plugin.
        
        Args:
            method_name: Name to register the plugin under
            plugin: Monitoring plugin instance
        """
        self.health_checker.register_monitoring_plugin(method_name, plugin)
        self.logger.info(f"Added custom monitoring plugin: {method_name}")
    
    def get_monitoring_statistics(self) -> Dict[str, Any]:
        """
        Get monitoring statistics and health summary.
        
        Returns:
            Dictionary with monitoring statistics
        """
        current_statuses = self.get_current_status()
        
        total_nodes = len(self.cluster_config.nodes)
        healthy_nodes = sum(1 for status in current_statuses.values() if status.is_healthy)
        unhealthy_nodes = total_nodes - healthy_nodes
        
        # Calculate average response times
        response_times = [status.response_time_ms for status in current_statuses.values()]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Count nodes by type
        kafka_brokers = len(self.cluster_config.get_kafka_brokers())
        zookeeper_nodes = len(self.cluster_config.get_zookeeper_nodes())
        
        return {
            'monitoring_active': self._monitoring_active,
            'monitoring_interval_seconds': self.cluster_config.monitoring_interval_seconds,
            'total_nodes': total_nodes,
            'healthy_nodes': healthy_nodes,
            'unhealthy_nodes': unhealthy_nodes,
            'health_percentage': (healthy_nodes / total_nodes * 100) if total_nodes > 0 else 0,
            'average_response_time_ms': avg_response_time,
            'kafka_brokers': kafka_brokers,
            'zookeeper_nodes': zookeeper_nodes,
            'registered_plugins': list(self.health_checker._monitoring_plugins.keys()),
            'callback_counts': {
                'failure_callbacks': len(self._failure_callbacks),
                'recovery_callbacks': len(self._recovery_callbacks),
                'status_change_callbacks': len(self._status_change_callbacks)
            }
        }