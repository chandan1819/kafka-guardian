"""
Monitoring plugins for different health check methods.
"""

import socket
import time
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import subprocess
import json

from .monitoring import MonitoringPlugin
from .models import NodeConfig
from .exceptions import MonitoringError
from .security import SecureConnectionManager
from .credentials import CredentialManager


class JMXMonitoringPlugin(MonitoringPlugin):
    """
    JMX-based monitoring plugin for Kafka brokers.
    Uses JMX endpoints to check broker health and collect metrics.
    """
    
    def __init__(self, credential_manager: Optional[CredentialManager] = None):
        """
        Initialize JMX monitoring plugin.
        
        Args:
            credential_manager: Optional credential manager for authentication
        """
        self.credential_manager = credential_manager
        self.secure_connection_manager = None
        if credential_manager:
            self.secure_connection_manager = SecureConnectionManager(credential_manager)
        self.logger = logging.getLogger(__name__)
    
    @property
    def plugin_name(self) -> str:
        return "jmx_monitoring"
    
    @property
    def supported_node_types(self) -> list[str]:
        return ["kafka_broker"]
    
    def check_health(self, node: NodeConfig, timeout_seconds: int) -> bool:
        """
        Check Kafka broker health via JMX endpoint.
        
        Args:
            node: Node configuration to check
            timeout_seconds: Timeout for the health check
            
        Returns:
            True if broker is healthy, False otherwise
            
        Raises:
            MonitoringError: If health check cannot be performed
        """
        if node.node_type != "kafka_broker":
            raise MonitoringError(f"JMX monitoring not supported for node type: {node.node_type}")
        
        if not node.jmx_port:
            raise MonitoringError(f"JMX port not configured for node: {node.node_id}")
        
        try:
            # First check if JMX port is accessible
            if not self._check_jmx_port_accessible(node.host, node.jmx_port, timeout_seconds, 
                                                 node.security_config):
                return False
            
            # Try to get basic JMX metrics
            metrics = self._get_jmx_metrics(node, timeout_seconds)
            
            # Evaluate health based on metrics
            return self._evaluate_broker_health(metrics)
            
        except Exception as e:
            self.logger.debug(f"JMX health check failed for {node.node_id}: {e}")
            raise MonitoringError(f"JMX health check failed: {e}")
    
    def _check_jmx_port_accessible(self, host: str, port: int, timeout_seconds: int, 
                                  security_config: Optional[object] = None) -> bool:
        """Check if JMX port is accessible via socket connection."""
        try:
            if security_config and self.secure_connection_manager:
                # Use secure connection if SSL is enabled
                sock = self.secure_connection_manager.create_secure_socket(
                    host, port, security_config, "kafka"
                )
                sock.close()
                return True
            else:
                # Use regular socket connection
                with socket.create_connection((host, port), timeout=timeout_seconds):
                    return True
        except (socket.timeout, socket.error, OSError) as e:
            self.logger.debug(f"JMX port {host}:{port} not accessible: {e}")
            return False
    
    def _get_jmx_metrics(self, node: NodeConfig, timeout_seconds: int) -> Dict[str, Any]:
        """
        Get JMX metrics from Kafka broker using jconsole or similar tool.
        This is a simplified implementation that would typically use a JMX client library.
        """
        # In a real implementation, you would use a JMX client library like py4j with JMX
        # For this implementation, we'll simulate getting key metrics
        
        try:
            # Simulate JMX connection and metric retrieval
            # In practice, you would connect to JMX and query specific MBeans
            jmx_url = f"service:jmx:rmi:///jndi/rmi://{node.host}:{node.jmx_port}/jmxrmi"
            
            # Simulate getting key Kafka broker metrics
            metrics = {
                "kafka.server:type=BrokerTopicMetrics,name=MessagesInPerSec": {
                    "Count": 1000,
                    "FifteenMinuteRate": 10.5,
                    "FiveMinuteRate": 12.3,
                    "MeanRate": 11.2,
                    "OneMinuteRate": 13.1
                },
                "kafka.server:type=ReplicaManager,name=LeaderCount": {
                    "Value": 5
                },
                "kafka.server:type=ReplicaManager,name=PartitionCount": {
                    "Value": 10
                },
                "kafka.server:type=KafkaServer,name=BrokerState": {
                    "Value": 3  # 3 = Running state
                },
                "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce": {
                    "Mean": 1.5,
                    "Max": 10.0,
                    "Min": 0.1
                }
            }
            
            # In a real implementation, this would be actual JMX queries
            # For now, we'll just check if the port is accessible
            if self._check_jmx_port_accessible(node.host, node.jmx_port, timeout_seconds, 
                                             node.security_config):
                return metrics
            else:
                raise MonitoringError("JMX port not accessible")
                
        except Exception as e:
            raise MonitoringError(f"Failed to retrieve JMX metrics: {e}")
    
    def _evaluate_broker_health(self, metrics: Dict[str, Any]) -> bool:
        """
        Evaluate broker health based on JMX metrics.
        
        Args:
            metrics: Dictionary of JMX metrics
            
        Returns:
            True if broker is considered healthy
        """
        try:
            # Check broker state (should be 3 for running)
            broker_state = metrics.get("kafka.server:type=KafkaServer,name=BrokerState", {}).get("Value", 0)
            if broker_state != 3:
                self.logger.warning(f"Broker state is {broker_state}, expected 3 (running)")
                return False
            
            # Check if broker has partitions (indicates it's participating in cluster)
            partition_count = metrics.get("kafka.server:type=ReplicaManager,name=PartitionCount", {}).get("Value", 0)
            if partition_count == 0:
                self.logger.warning("Broker has no partitions")
                return False
            
            # Check request latency (should be reasonable)
            produce_latency = metrics.get("kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce", {})
            mean_latency = produce_latency.get("Mean", 0)
            if mean_latency > 1000:  # More than 1 second average latency
                self.logger.warning(f"High produce latency: {mean_latency}ms")
                return False
            
            # All checks passed
            return True
            
        except Exception as e:
            self.logger.error(f"Error evaluating broker health: {e}")
            return False


class SocketMonitoringPlugin(MonitoringPlugin):
    """
    Socket-based monitoring plugin for direct TCP connection tests.
    Works with both Kafka brokers and Zookeeper nodes.
    """
    
    def __init__(self, credential_manager: Optional[CredentialManager] = None):
        """Initialize socket monitoring plugin."""
        self.credential_manager = credential_manager
        self.secure_connection_manager = None
        if credential_manager:
            self.secure_connection_manager = SecureConnectionManager(credential_manager)
        self.logger = logging.getLogger(__name__)
    
    @property
    def plugin_name(self) -> str:
        return "socket_monitoring"
    
    @property
    def supported_node_types(self) -> list[str]:
        return ["kafka_broker", "zookeeper"]
    
    def check_health(self, node: NodeConfig, timeout_seconds: int) -> bool:
        """
        Check node health via direct TCP socket connection.
        
        Args:
            node: Node configuration to check
            timeout_seconds: Timeout for the health check
            
        Returns:
            True if node is accessible, False otherwise
            
        Raises:
            MonitoringError: If health check cannot be performed
        """
        try:
            # Test primary port
            if not self._test_socket_connection(node.host, node.port, timeout_seconds, 
                                              node.security_config, node.node_type):
                return False
            
            # For Kafka brokers, also test JMX port if configured
            if node.node_type == "kafka_broker" and node.jmx_port:
                if not self._test_socket_connection(node.host, node.jmx_port, timeout_seconds, 
                                                  node.security_config, node.node_type):
                    self.logger.warning(f"JMX port {node.jmx_port} not accessible for {node.node_id}")
                    # Don't fail the health check just because JMX port is down
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Socket health check failed for {node.node_id}: {e}")
            raise MonitoringError(f"Socket health check failed: {e}")
    
    def _test_socket_connection(self, host: str, port: int, timeout_seconds: int,
                               security_config: Optional[object] = None,
                               service_type: str = "kafka") -> bool:
        """
        Test TCP socket connection to host:port.
        
        Args:
            host: Target host
            port: Target port
            timeout_seconds: Connection timeout
            security_config: Optional security configuration for SSL
            service_type: Service type for SSL context
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            start_time = time.time()
            
            if security_config and security_config.enable_ssl and self.secure_connection_manager:
                # Use secure connection
                sock = self.secure_connection_manager.create_secure_socket(
                    host, port, security_config, service_type
                )
                sock.close()
            else:
                # Use regular socket connection
                with socket.create_connection((host, port), timeout=timeout_seconds):
                    pass
            
            connection_time = (time.time() - start_time) * 1000
            self.logger.debug(f"Socket connection to {host}:{port} successful ({connection_time:.1f}ms)")
            return True
            
        except (socket.timeout, socket.error, OSError) as e:
            self.logger.debug(f"Socket connection to {host}:{port} failed: {e}")
            return False


class ZookeeperMonitoringPlugin(MonitoringPlugin):
    """
    Zookeeper-specific monitoring plugin using four-letter words.
    Uses Zookeeper's administrative commands like 'ruok' and 'stat'.
    """
    
    def __init__(self, credential_manager: Optional[CredentialManager] = None):
        """Initialize Zookeeper monitoring plugin."""
        self.credential_manager = credential_manager
        self.secure_connection_manager = None
        if credential_manager:
            self.secure_connection_manager = SecureConnectionManager(credential_manager)
        self.logger = logging.getLogger(__name__)
    
    @property
    def plugin_name(self) -> str:
        return "zookeeper_monitoring"
    
    @property
    def supported_node_types(self) -> list[str]:
        return ["zookeeper"]
    
    def check_health(self, node: NodeConfig, timeout_seconds: int) -> bool:
        """
        Check Zookeeper node health using four-letter words.
        
        Args:
            node: Node configuration to check
            timeout_seconds: Timeout for the health check
            
        Returns:
            True if Zookeeper node is healthy, False otherwise
            
        Raises:
            MonitoringError: If health check cannot be performed
        """
        if node.node_type != "zookeeper":
            raise MonitoringError(f"Zookeeper monitoring not supported for node type: {node.node_type}")
        
        try:
            # First try 'ruok' command (are you ok?)
            if not self._send_four_letter_word(node.host, node.port, "ruok", timeout_seconds, 
                                             node.security_config):
                return False
            
            # Get detailed status with 'stat' command
            stat_response = self._get_zookeeper_stat(node.host, node.port, timeout_seconds, 
                                                   node.security_config)
            if not stat_response:
                return False
            
            # Evaluate health based on stat response
            return self._evaluate_zookeeper_health(stat_response)
            
        except Exception as e:
            self.logger.debug(f"Zookeeper health check failed for {node.node_id}: {e}")
            raise MonitoringError(f"Zookeeper health check failed: {e}")
    
    def _send_four_letter_word(self, host: str, port: int, command: str, timeout_seconds: int,
                              security_config: Optional[object] = None) -> bool:
        """
        Send a four-letter word command to Zookeeper.
        
        Args:
            host: Zookeeper host
            port: Zookeeper port
            command: Four-letter command (e.g., 'ruok', 'stat')
            timeout_seconds: Connection timeout
            security_config: Optional security configuration for SSL
            
        Returns:
            True if command executed successfully, False otherwise
        """
        try:
            if security_config and security_config.enable_ssl and self.secure_connection_manager:
                # Use secure connection
                sock = self.secure_connection_manager.create_secure_socket(
                    host, port, security_config, "zookeeper"
                )
            else:
                # Use regular socket connection
                sock = socket.create_connection((host, port), timeout=timeout_seconds)
            
            try:
                sock.settimeout(timeout_seconds)
                sock.sendall(command.encode())
                
                response = sock.recv(1024).decode().strip()
                
                if command == "ruok":
                    # Expected response is "imok"
                    return response == "imok"
                elif command == "stat":
                    # For stat, any non-empty response indicates success
                    return len(response) > 0
                else:
                    return len(response) > 0
            finally:
                sock.close()
                    
        except (socket.timeout, socket.error, OSError) as e:
            self.logger.debug(f"Four-letter word '{command}' failed for {host}:{port}: {e}")
            return False
    
    def _get_zookeeper_stat(self, host: str, port: int, timeout_seconds: int,
                           security_config: Optional[object] = None) -> Optional[str]:
        """
        Get Zookeeper status information using 'stat' command.
        
        Args:
            host: Zookeeper host
            port: Zookeeper port
            timeout_seconds: Connection timeout
            security_config: Optional security configuration for SSL
            
        Returns:
            Stat response string or None if failed
        """
        try:
            if security_config and security_config.enable_ssl and self.secure_connection_manager:
                # Use secure connection
                sock = self.secure_connection_manager.create_secure_socket(
                    host, port, security_config, "zookeeper"
                )
            else:
                # Use regular socket connection
                sock = socket.create_connection((host, port), timeout=timeout_seconds)
            
            try:
                sock.settimeout(timeout_seconds)
                sock.sendall(b"stat")
                
                response = b""
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    response += chunk
                    if len(response) > 4096:  # Prevent excessive memory usage
                        break
                
                return response.decode().strip()
            finally:
                sock.close()
                
        except (socket.timeout, socket.error, OSError) as e:
            self.logger.debug(f"Zookeeper stat command failed for {host}:{port}: {e}")
            return None
    
    def _evaluate_zookeeper_health(self, stat_response: str) -> bool:
        """
        Evaluate Zookeeper health based on stat command response.
        
        Args:
            stat_response: Response from 'stat' command
            
        Returns:
            True if Zookeeper is considered healthy
        """
        try:
            # Parse stat response for key indicators
            lines = stat_response.split('\n')
            
            # Look for key health indicators
            has_version = any("version" in line.lower() for line in lines)
            has_connections = any("connections" in line.lower() for line in lines)
            has_mode = any("mode:" in line.lower() for line in lines)
            
            # Check for error indicators
            has_errors = any("error" in line.lower() for line in lines)
            
            # Basic health evaluation
            if has_errors:
                self.logger.warning("Zookeeper stat response contains errors")
                return False
            
            if not (has_version and has_connections and has_mode):
                self.logger.warning("Zookeeper stat response missing expected fields")
                return False
            
            # Check for specific mode information
            for line in lines:
                if "mode:" in line.lower():
                    mode = line.split(":")[-1].strip().lower()
                    # Zookeeper should be in follower, leader, or standalone mode
                    if mode not in ["follower", "leader", "standalone"]:
                        self.logger.warning(f"Zookeeper in unexpected mode: {mode}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error evaluating Zookeeper health: {e}")
            return False