"""
Unit tests for monitoring plugins.
"""

import pytest
import socket
import time
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

from src.kafka_self_healing.monitoring_plugins import (
    JMXMonitoringPlugin, SocketMonitoringPlugin, ZookeeperMonitoringPlugin
)
from src.kafka_self_healing.models import NodeConfig
from src.kafka_self_healing.exceptions import MonitoringError


class TestJMXMonitoringPlugin:
    """Test cases for JMXMonitoringPlugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = JMXMonitoringPlugin()
        self.kafka_node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        assert self.plugin.plugin_name == "jmx_monitoring"
        assert "kafka_broker" in self.plugin.supported_node_types
        assert "zookeeper" not in self.plugin.supported_node_types
    
    def test_init_with_credentials(self):
        """Test initialization with JMX credentials."""
        plugin = JMXMonitoringPlugin(jmx_username="admin", jmx_password="secret")
        assert plugin.jmx_username == "admin"
        assert plugin.jmx_password == "secret"
    
    def test_check_health_unsupported_node_type(self):
        """Test health check with unsupported node type."""
        zk_node = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="localhost",
            port=2181
        )
        
        with pytest.raises(MonitoringError, match="JMX monitoring not supported"):
            self.plugin.check_health(zk_node, 5)
    
    def test_check_health_no_jmx_port(self):
        """Test health check when JMX port is not configured."""
        node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
            # No jmx_port
        )
        
        with pytest.raises(MonitoringError, match="JMX port not configured"):
            self.plugin.check_health(node, 5)
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_check_jmx_port_accessible_success(self, mock_socket):
        """Test successful JMX port accessibility check."""
        mock_socket.return_value.__enter__ = Mock()
        mock_socket.return_value.__exit__ = Mock()
        
        result = self.plugin._check_jmx_port_accessible("localhost", 9999, 5)
        assert result is True
        mock_socket.assert_called_once_with(("localhost", 9999), timeout=5)
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_check_jmx_port_accessible_failure(self, mock_socket):
        """Test JMX port accessibility check failure."""
        mock_socket.side_effect = socket.timeout("Connection timeout")
        
        result = self.plugin._check_jmx_port_accessible("localhost", 9999, 5)
        assert result is False
    
    def test_get_jmx_metrics_success(self):
        """Test successful JMX metrics retrieval."""
        with patch.object(self.plugin, '_check_jmx_port_accessible', return_value=True):
            metrics = self.plugin._get_jmx_metrics(self.kafka_node, 5)
            
            assert isinstance(metrics, dict)
            assert "kafka.server:type=KafkaServer,name=BrokerState" in metrics
            assert "kafka.server:type=ReplicaManager,name=PartitionCount" in metrics
    
    def test_get_jmx_metrics_port_not_accessible(self):
        """Test JMX metrics retrieval when port is not accessible."""
        with patch.object(self.plugin, '_check_jmx_port_accessible', return_value=False):
            with pytest.raises(MonitoringError, match="JMX port not accessible"):
                self.plugin._get_jmx_metrics(self.kafka_node, 5)
    
    def test_evaluate_broker_health_healthy(self):
        """Test broker health evaluation for healthy broker."""
        metrics = {
            "kafka.server:type=KafkaServer,name=BrokerState": {"Value": 3},
            "kafka.server:type=ReplicaManager,name=PartitionCount": {"Value": 10},
            "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce": {"Mean": 1.5}
        }
        
        result = self.plugin._evaluate_broker_health(metrics)
        assert result is True
    
    def test_evaluate_broker_health_wrong_state(self):
        """Test broker health evaluation for broker in wrong state."""
        metrics = {
            "kafka.server:type=KafkaServer,name=BrokerState": {"Value": 1},  # Not running
            "kafka.server:type=ReplicaManager,name=PartitionCount": {"Value": 10},
            "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce": {"Mean": 1.5}
        }
        
        result = self.plugin._evaluate_broker_health(metrics)
        assert result is False
    
    def test_evaluate_broker_health_no_partitions(self):
        """Test broker health evaluation for broker with no partitions."""
        metrics = {
            "kafka.server:type=KafkaServer,name=BrokerState": {"Value": 3},
            "kafka.server:type=ReplicaManager,name=PartitionCount": {"Value": 0},  # No partitions
            "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce": {"Mean": 1.5}
        }
        
        result = self.plugin._evaluate_broker_health(metrics)
        assert result is False
    
    def test_evaluate_broker_health_high_latency(self):
        """Test broker health evaluation for broker with high latency."""
        metrics = {
            "kafka.server:type=KafkaServer,name=BrokerState": {"Value": 3},
            "kafka.server:type=ReplicaManager,name=PartitionCount": {"Value": 10},
            "kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce": {"Mean": 1500}  # High latency
        }
        
        result = self.plugin._evaluate_broker_health(metrics)
        assert result is False
    
    @patch.object(JMXMonitoringPlugin, '_check_jmx_port_accessible')
    @patch.object(JMXMonitoringPlugin, '_get_jmx_metrics')
    @patch.object(JMXMonitoringPlugin, '_evaluate_broker_health')
    def test_check_health_success(self, mock_evaluate, mock_get_metrics, mock_check_port):
        """Test successful health check."""
        mock_check_port.return_value = True
        mock_get_metrics.return_value = {"test": "metrics"}
        mock_evaluate.return_value = True
        
        result = self.plugin.check_health(self.kafka_node, 5)
        assert result is True
        
        mock_check_port.assert_called_once()
        mock_get_metrics.assert_called_once()
        mock_evaluate.assert_called_once()
    
    @patch.object(JMXMonitoringPlugin, '_check_jmx_port_accessible')
    def test_check_health_port_not_accessible(self, mock_check_port):
        """Test health check when JMX port is not accessible."""
        mock_check_port.return_value = False
        
        result = self.plugin.check_health(self.kafka_node, 5)
        assert result is False


class TestSocketMonitoringPlugin:
    """Test cases for SocketMonitoringPlugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = SocketMonitoringPlugin()
        self.kafka_node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092,
            jmx_port=9999
        )
        self.zk_node = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="localhost",
            port=2181
        )
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        assert self.plugin.plugin_name == "socket_monitoring"
        assert "kafka_broker" in self.plugin.supported_node_types
        assert "zookeeper" in self.plugin.supported_node_types
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_test_socket_connection_success(self, mock_socket):
        """Test successful socket connection."""
        mock_socket.return_value.__enter__ = Mock()
        mock_socket.return_value.__exit__ = Mock()
        
        result = self.plugin._test_socket_connection("localhost", 9092, 5)
        assert result is True
        mock_socket.assert_called_once_with(("localhost", 9092), timeout=5)
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_test_socket_connection_failure(self, mock_socket):
        """Test socket connection failure."""
        mock_socket.side_effect = socket.timeout("Connection timeout")
        
        result = self.plugin._test_socket_connection("localhost", 9092, 5)
        assert result is False
    
    @patch.object(SocketMonitoringPlugin, '_test_socket_connection')
    def test_check_health_kafka_success(self, mock_test_socket):
        """Test successful health check for Kafka broker."""
        mock_test_socket.return_value = True
        
        result = self.plugin.check_health(self.kafka_node, 5)
        assert result is True
        
        # Should test both main port and JMX port
        assert mock_test_socket.call_count == 2
    
    @patch.object(SocketMonitoringPlugin, '_test_socket_connection')
    def test_check_health_kafka_main_port_failure(self, mock_test_socket):
        """Test health check when main port fails."""
        mock_test_socket.return_value = False
        
        result = self.plugin.check_health(self.kafka_node, 5)
        assert result is False
        
        # Should only test main port since it failed
        assert mock_test_socket.call_count == 1
    
    @patch.object(SocketMonitoringPlugin, '_test_socket_connection')
    def test_check_health_kafka_jmx_port_failure(self, mock_test_socket):
        """Test health check when JMX port fails but main port succeeds."""
        # Main port succeeds, JMX port fails
        mock_test_socket.side_effect = [True, False]
        
        result = self.plugin.check_health(self.kafka_node, 5)
        # Should still be healthy since JMX port failure doesn't fail the check
        assert result is True
        assert mock_test_socket.call_count == 2
    
    @patch.object(SocketMonitoringPlugin, '_test_socket_connection')
    def test_check_health_zookeeper_success(self, mock_test_socket):
        """Test successful health check for Zookeeper node."""
        mock_test_socket.return_value = True
        
        result = self.plugin.check_health(self.zk_node, 5)
        assert result is True
        
        # Should only test main port for Zookeeper
        assert mock_test_socket.call_count == 1
    
    @patch.object(SocketMonitoringPlugin, '_test_socket_connection')
    def test_check_health_exception(self, mock_test_socket):
        """Test health check with exception."""
        mock_test_socket.side_effect = Exception("Test exception")
        
        with pytest.raises(MonitoringError, match="Socket health check failed"):
            self.plugin.check_health(self.kafka_node, 5)


class TestZookeeperMonitoringPlugin:
    """Test cases for ZookeeperMonitoringPlugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = ZookeeperMonitoringPlugin()
        self.zk_node = NodeConfig(
            node_id="zk-1",
            node_type="zookeeper",
            host="localhost",
            port=2181
        )
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        assert self.plugin.plugin_name == "zookeeper_monitoring"
        assert "zookeeper" in self.plugin.supported_node_types
        assert "kafka_broker" not in self.plugin.supported_node_types
    
    def test_check_health_unsupported_node_type(self):
        """Test health check with unsupported node type."""
        kafka_node = NodeConfig(
            node_id="kafka-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        with pytest.raises(MonitoringError, match="Zookeeper monitoring not supported"):
            self.plugin.check_health(kafka_node, 5)
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_send_four_letter_word_ruok_success(self, mock_socket):
        """Test successful 'ruok' command."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b"imok"
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_socket.return_value.__exit__ = Mock()
        
        result = self.plugin._send_four_letter_word("localhost", 2181, "ruok", 5)
        assert result is True
        
        mock_sock.sendall.assert_called_once_with(b"ruok")
        mock_sock.recv.assert_called_once_with(1024)
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_send_four_letter_word_ruok_failure(self, mock_socket):
        """Test 'ruok' command with wrong response."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b"error"
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_socket.return_value.__exit__ = Mock()
        
        result = self.plugin._send_four_letter_word("localhost", 2181, "ruok", 5)
        assert result is False
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_send_four_letter_word_stat_success(self, mock_socket):
        """Test successful 'stat' command."""
        mock_sock = Mock()
        mock_sock.recv.return_value = b"Zookeeper version: 3.6.0"
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_socket.return_value.__exit__ = Mock()
        
        result = self.plugin._send_four_letter_word("localhost", 2181, "stat", 5)
        assert result is True
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_send_four_letter_word_connection_failure(self, mock_socket):
        """Test four-letter word command with connection failure."""
        mock_socket.side_effect = socket.timeout("Connection timeout")
        
        result = self.plugin._send_four_letter_word("localhost", 2181, "ruok", 5)
        assert result is False
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_get_zookeeper_stat_success(self, mock_socket):
        """Test successful Zookeeper stat retrieval."""
        stat_response = """Zookeeper version: 3.6.0-SNAPSHOT
Latency min/avg/max: 0/0/0
Received: 1
Sent: 0
Connections: 1
Outstanding: 0
Zxid: 0x0
Mode: standalone
Node count: 4"""
        
        mock_sock = Mock()
        mock_sock.recv.side_effect = [stat_response.encode(), b""]
        mock_socket.return_value.__enter__.return_value = mock_sock
        mock_socket.return_value.__exit__ = Mock()
        
        result = self.plugin._get_zookeeper_stat("localhost", 2181, 5)
        assert result == stat_response
        
        mock_sock.sendall.assert_called_once_with(b"stat")
    
    @patch('src.kafka_self_healing.monitoring_plugins.socket.create_connection')
    def test_get_zookeeper_stat_failure(self, mock_socket):
        """Test Zookeeper stat retrieval failure."""
        mock_socket.side_effect = socket.error("Connection failed")
        
        result = self.plugin._get_zookeeper_stat("localhost", 2181, 5)
        assert result is None
    
    def test_evaluate_zookeeper_health_healthy(self):
        """Test Zookeeper health evaluation for healthy node."""
        stat_response = """Zookeeper version: 3.6.0-SNAPSHOT
Latency min/avg/max: 0/0/0
Received: 1
Sent: 0
Connections: 1
Outstanding: 0
Zxid: 0x0
Mode: leader
Node count: 4"""
        
        result = self.plugin._evaluate_zookeeper_health(stat_response)
        assert result is True
    
    def test_evaluate_zookeeper_health_with_errors(self):
        """Test Zookeeper health evaluation with errors in response."""
        stat_response = """Error: Connection failed
Zookeeper version: 3.6.0-SNAPSHOT"""
        
        result = self.plugin._evaluate_zookeeper_health(stat_response)
        assert result is False
    
    def test_evaluate_zookeeper_health_missing_fields(self):
        """Test Zookeeper health evaluation with missing fields."""
        stat_response = """Zookeeper version: 3.6.0-SNAPSHOT"""
        
        result = self.plugin._evaluate_zookeeper_health(stat_response)
        assert result is False
    
    def test_evaluate_zookeeper_health_invalid_mode(self):
        """Test Zookeeper health evaluation with invalid mode."""
        stat_response = """Zookeeper version: 3.6.0-SNAPSHOT
Connections: 1
Mode: unknown"""
        
        result = self.plugin._evaluate_zookeeper_health(stat_response)
        assert result is False
    
    def test_evaluate_zookeeper_health_valid_modes(self):
        """Test Zookeeper health evaluation with all valid modes."""
        valid_modes = ["leader", "follower", "standalone"]
        
        for mode in valid_modes:
            stat_response = f"""Zookeeper version: 3.6.0-SNAPSHOT
Connections: 1
Mode: {mode}"""
            
            result = self.plugin._evaluate_zookeeper_health(stat_response)
            assert result is True, f"Mode {mode} should be valid"
    
    @patch.object(ZookeeperMonitoringPlugin, '_send_four_letter_word')
    @patch.object(ZookeeperMonitoringPlugin, '_get_zookeeper_stat')
    @patch.object(ZookeeperMonitoringPlugin, '_evaluate_zookeeper_health')
    def test_check_health_success(self, mock_evaluate, mock_get_stat, mock_send_word):
        """Test successful Zookeeper health check."""
        mock_send_word.return_value = True
        mock_get_stat.return_value = "stat response"
        mock_evaluate.return_value = True
        
        result = self.plugin.check_health(self.zk_node, 5)
        assert result is True
        
        mock_send_word.assert_called_once_with("localhost", 2181, "ruok", 5)
        mock_get_stat.assert_called_once_with("localhost", 2181, 5)
        mock_evaluate.assert_called_once_with("stat response")
    
    @patch.object(ZookeeperMonitoringPlugin, '_send_four_letter_word')
    def test_check_health_ruok_failure(self, mock_send_word):
        """Test health check when 'ruok' command fails."""
        mock_send_word.return_value = False
        
        result = self.plugin.check_health(self.zk_node, 5)
        assert result is False
    
    @patch.object(ZookeeperMonitoringPlugin, '_send_four_letter_word')
    @patch.object(ZookeeperMonitoringPlugin, '_get_zookeeper_stat')
    def test_check_health_stat_failure(self, mock_get_stat, mock_send_word):
        """Test health check when 'stat' command fails."""
        mock_send_word.return_value = True
        mock_get_stat.return_value = None
        
        result = self.plugin.check_health(self.zk_node, 5)
        assert result is False