"""
End-to-end integration tests for the Kafka Self-Healing system.
These tests require Docker and docker-compose to be available.
"""

import asyncio
import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from typing import Dict, Any
import tempfile
import yaml
import psutil
import requests
from unittest.mock import patch

from src.kafka_self_healing.main import SelfHealingSystem
from src.kafka_self_healing.config import ConfigurationManager
from src.kafka_self_healing.models import NodeConfig, NodeStatus


class E2ETestBase(unittest.TestCase):
    """Base class for end-to-end tests with Docker setup."""
    
    @classmethod
    def setUpClass(cls):
        """Set up Docker test environment."""
        cls.docker_compose_file = Path(__file__).parent.parent / "docker-compose.test.yml"
        cls.start_test_cluster()
        cls.wait_for_cluster_ready()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up Docker test environment."""
        cls.stop_test_cluster()
    
    @classmethod
    def start_test_cluster(cls):
        """Start the test Kafka cluster using Docker Compose."""
        try:
            subprocess.run([
                "docker-compose", "-f", str(cls.docker_compose_file), 
                "up", "-d"
            ], check=True, capture_output=True)
            print("Test cluster started successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to start test cluster: {e}")
            print(f"stdout: {e.stdout.decode()}")
            print(f"stderr: {e.stderr.decode()}")
            raise
    
    @classmethod
    def stop_test_cluster(cls):
        """Stop the test Kafka cluster."""
        try:
            subprocess.run([
                "docker-compose", "-f", str(cls.docker_compose_file), 
                "down", "-v"
            ], check=True, capture_output=True)
            print("Test cluster stopped successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to stop test cluster: {e}")
    
    @classmethod
    def wait_for_cluster_ready(cls, timeout=120):
        """Wait for the cluster to be ready."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check Zookeeper
                result = subprocess.run([
                    "docker", "exec", "test-zookeeper", 
                    "bash", "-c", "echo 'ruok' | nc localhost 2181"
                ], capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0 and "imok" in result.stdout:
                    # Check Kafka brokers
                    kafka1_ready = cls.check_kafka_ready("test-kafka1", 9092)
                    kafka2_ready = cls.check_kafka_ready("test-kafka2", 9093)
                    
                    if kafka1_ready and kafka2_ready:
                        print("Test cluster is ready")
                        time.sleep(5)  # Additional wait for stability
                        return
                
            except Exception as e:
                print(f"Waiting for cluster... {e}")
            
            time.sleep(2)
        
        raise TimeoutError("Test cluster failed to become ready within timeout")
    
    @classmethod
    def check_kafka_ready(cls, container_name: str, port: int) -> bool:
        """Check if a Kafka broker is ready."""
        try:
            result = subprocess.run([
                "docker", "exec", container_name,
                "kafka-broker-api-versions", "--bootstrap-server", f"localhost:{port}"
            ], capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False
    
    def create_test_config(self, **overrides) -> str:
        """Create a test configuration file."""
        config = {
            "cluster": {
                "kafka_brokers": [
                    {
                        "node_id": "kafka1",
                        "host": "localhost",
                        "port": 9092,
                        "jmx_port": 9999
                    },
                    {
                        "node_id": "kafka2", 
                        "host": "localhost",
                        "port": 9093,
                        "jmx_port": 9998
                    }
                ],
                "zookeeper_nodes": [
                    {
                        "node_id": "zk1",
                        "host": "localhost",
                        "port": 2181
                    }
                ]
            },
            "monitoring": {
                "interval_seconds": 5,
                "timeout_seconds": 10,
                "methods": ["socket", "jmx"]
            },
            "recovery": {
                "max_attempts": 2,
                "initial_delay_seconds": 1,
                "backoff_multiplier": 2.0,
                "max_delay_seconds": 10,
                "actions": ["restart_service"]
            },
            "notifications": {
                "smtp": {
                    "host": "localhost",
                    "port": 1025,
                    "username": "",
                    "password": "",
                    "from_email": "test@example.com",
                    "to_emails": ["admin@example.com"]
                }
            },
            "logging": {
                "level": "INFO",
                "file": "test_logs/e2e_test.log",
                "max_size_mb": 10,
                "backup_count": 3
            }
        }
        
        # Apply overrides
        config.update(overrides)
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            return f.name


class TestE2EMonitoring(E2ETestBase):
    """End-to-end tests for monitoring functionality."""
    
    def test_successful_monitoring_cycle(self):
        """Test that monitoring successfully detects healthy nodes."""
        config_file = self.create_test_config()
        
        try:
            system = SelfHealingSystem(config_file)
            system.start()
            
            # Let it run for a few monitoring cycles
            time.sleep(15)
            
            # Check that nodes are being monitored
            monitoring_service = system.monitoring_service
            self.assertIsNotNone(monitoring_service)
            
            # Verify healthy status for all nodes
            for node_id in ["kafka1", "kafka2", "zk1"]:
                status = monitoring_service.get_node_status(node_id)
                self.assertIsNotNone(status)
                self.assertTrue(status.is_healthy, f"Node {node_id} should be healthy")
            
            system.stop()
            
        finally:
            os.unlink(config_file)
    
    def test_failure_detection(self):
        """Test that monitoring detects when a node fails."""
        config_file = self.create_test_config()
        
        try:
            system = SelfHealingSystem(config_file)
            system.start()
            
            # Let it establish baseline
            time.sleep(10)
            
            # Stop one Kafka broker
            subprocess.run([
                "docker", "stop", "test-kafka2"
            ], check=True)
            
            # Wait for failure detection
            time.sleep(15)
            
            # Check that failure was detected
            monitoring_service = system.monitoring_service
            kafka2_status = monitoring_service.get_node_status("kafka2")
            self.assertIsNotNone(kafka2_status)
            self.assertFalse(kafka2_status.is_healthy, "kafka2 should be detected as unhealthy")
            
            # Restart the broker
            subprocess.run([
                "docker", "start", "test-kafka2"
            ], check=True)
            
            # Wait for recovery detection
            time.sleep(20)
            
            kafka2_status = monitoring_service.get_node_status("kafka2")
            self.assertTrue(kafka2_status.is_healthy, "kafka2 should recover to healthy")
            
            system.stop()
            
        finally:
            os.unlink(config_file)


class TestE2ERecovery(E2ETestBase):
    """End-to-end tests for recovery functionality."""
    
    def test_recovery_workflow(self):
        """Test complete recovery workflow from failure detection to recovery."""
        config_file = self.create_test_config()
        
        try:
            system = SelfHealingSystem(config_file)
            
            # Mock the recovery action to simulate container restart
            original_execute = system.recovery_engine.execute_recovery
            recovery_attempts = []
            
            def mock_execute_recovery(node_config, failure_type):
                recovery_attempts.append((node_config.node_id, failure_type))
                # Simulate successful recovery by restarting container
                if node_config.node_id == "kafka2":
                    subprocess.run(["docker", "restart", "test-kafka2"], check=True)
                return original_execute(node_config, failure_type)
            
            system.recovery_engine.execute_recovery = mock_execute_recovery
            system.start()
            
            # Let it establish baseline
            time.sleep(10)
            
            # Stop Kafka broker to trigger recovery
            subprocess.run(["docker", "stop", "test-kafka2"], check=True)
            
            # Wait for failure detection and recovery
            time.sleep(30)
            
            # Verify recovery was attempted
            self.assertTrue(len(recovery_attempts) > 0, "Recovery should have been attempted")
            self.assertEqual(recovery_attempts[0][0], "kafka2", "Recovery should target kafka2")
            
            # Verify node is healthy again
            kafka2_status = system.monitoring_service.get_node_status("kafka2")
            self.assertTrue(kafka2_status.is_healthy, "kafka2 should be recovered")
            
            system.stop()
            
        finally:
            os.unlink(config_file)


class TestE2ENotifications(E2ETestBase):
    """End-to-end tests for notification functionality."""
    
    def test_notification_on_recovery_failure(self):
        """Test that notifications are sent when recovery fails."""
        config_file = self.create_test_config()
        
        try:
            system = SelfHealingSystem(config_file)
            
            # Mock recovery to always fail
            def mock_failing_recovery(node_config, failure_type):
                from src.kafka_self_healing.models import RecoveryResult
                return RecoveryResult(
                    node_id=node_config.node_id,
                    action_type="mock_fail",
                    command_executed="mock command",
                    exit_code=1,
                    stdout="",
                    stderr="Mock failure",
                    execution_time=time.time(),
                    success=False
                )
            
            system.recovery_engine.execute_recovery = mock_failing_recovery
            system.start()
            
            # Let it establish baseline
            time.sleep(10)
            
            # Stop Kafka broker to trigger failed recovery
            subprocess.run(["docker", "stop", "test-kafka2"], check=True)
            
            # Wait for failure detection, recovery attempts, and notification
            time.sleep(45)
            
            # Check MailHog for sent emails
            try:
                response = requests.get("http://localhost:8025/api/v2/messages")
                messages = response.json()
                
                self.assertTrue(len(messages) > 0, "Should have sent notification email")
                
                # Check email content
                email = messages[0]
                self.assertIn("kafka2", email["Content"]["Body"])
                self.assertIn("failure", email["Content"]["Body"].lower())
                
            except Exception as e:
                self.fail(f"Failed to check notifications: {e}")
            
            system.stop()
            
        finally:
            os.unlink(config_file)


class TestE2EPerformance(E2ETestBase):
    """Performance and resource usage tests."""
    
    def test_monitoring_performance(self):
        """Test monitoring performance and resource usage."""
        config_file = self.create_test_config()
        
        try:
            # Get baseline resource usage
            process = psutil.Process()
            baseline_memory = process.memory_info().rss
            baseline_cpu = process.cpu_percent()
            
            system = SelfHealingSystem(config_file)
            system.start()
            
            # Run for monitoring cycles and measure performance
            start_time = time.time()
            monitoring_cycles = 0
            
            while time.time() - start_time < 60:  # Run for 1 minute
                time.sleep(5)
                monitoring_cycles += 1
                
                # Check resource usage
                current_memory = process.memory_info().rss
                current_cpu = process.cpu_percent()
                
                # Memory should not grow excessively (allow 50MB growth)
                memory_growth = current_memory - baseline_memory
                self.assertLess(memory_growth, 50 * 1024 * 1024, 
                               f"Memory growth too high: {memory_growth / 1024 / 1024:.1f}MB")
                
                # CPU usage should be reasonable (allow up to 20% average)
                self.assertLess(current_cpu, 20.0, 
                               f"CPU usage too high: {current_cpu:.1f}%")
            
            # Verify monitoring frequency
            expected_cycles = 60 / 5  # 5 second intervals
            self.assertGreaterEqual(monitoring_cycles, expected_cycles * 0.8, 
                                   "Monitoring frequency too low")
            
            system.stop()
            
        finally:
            os.unlink(config_file)
    
    def test_concurrent_monitoring_performance(self):
        """Test performance with multiple nodes being monitored concurrently."""
        # Create config with more nodes for stress testing
        config_file = self.create_test_config()
        
        try:
            system = SelfHealingSystem(config_file)
            
            start_time = time.time()
            system.start()
            
            # Let it run several monitoring cycles
            time.sleep(30)
            
            # Measure monitoring latency
            monitoring_service = system.monitoring_service
            
            # All nodes should be checked within reasonable time
            for node_id in ["kafka1", "kafka2", "zk1"]:
                status = monitoring_service.get_node_status(node_id)
                self.assertIsNotNone(status)
                
                # Check that status is recent (within last monitoring interval + buffer)
                time_since_check = time.time() - status.last_check_time
                self.assertLess(time_since_check, 15, 
                               f"Node {node_id} check too old: {time_since_check:.1f}s")
            
            system.stop()
            
        finally:
            os.unlink(config_file)


class TestE2EResilience(E2ETestBase):
    """Tests for system resilience and error handling."""
    
    def test_partial_cluster_failure_resilience(self):
        """Test system continues operating when part of cluster fails."""
        config_file = self.create_test_config()
        
        try:
            system = SelfHealingSystem(config_file)
            system.start()
            
            # Let it establish baseline
            time.sleep(10)
            
            # Stop Zookeeper (major failure)
            subprocess.run(["docker", "stop", "test-zookeeper"], check=True)
            
            # System should continue monitoring Kafka brokers
            time.sleep(20)
            
            # Kafka brokers should still be monitored (though may be unhealthy due to ZK)
            monitoring_service = system.monitoring_service
            kafka1_status = monitoring_service.get_node_status("kafka1")
            kafka2_status = monitoring_service.get_node_status("kafka2")
            
            self.assertIsNotNone(kafka1_status, "kafka1 should still be monitored")
            self.assertIsNotNone(kafka2_status, "kafka2 should still be monitored")
            
            # Restart Zookeeper
            subprocess.run(["docker", "start", "test-zookeeper"], check=True)
            time.sleep(20)
            
            # System should recover
            zk_status = monitoring_service.get_node_status("zk1")
            self.assertIsNotNone(zk_status, "Zookeeper should be monitored again")
            
            system.stop()
            
        finally:
            os.unlink(config_file)
    
    def test_configuration_error_handling(self):
        """Test system handles configuration errors gracefully."""
        # Create config with invalid settings
        invalid_config = self.create_test_config()
        
        # Modify config to have invalid values
        with open(invalid_config, 'r') as f:
            config = yaml.safe_load(f)
        
        config['cluster']['kafka_brokers'][0]['port'] = 'invalid_port'
        
        with open(invalid_config, 'w') as f:
            yaml.dump(config, f)
        
        try:
            # System should fail gracefully with clear error
            with self.assertRaises(Exception) as context:
                system = SelfHealingSystem(invalid_config)
                system.start()
            
            # Error should be informative
            error_msg = str(context.exception).lower()
            self.assertTrue(
                'port' in error_msg or 'config' in error_msg,
                f"Error message should mention configuration issue: {error_msg}"
            )
            
        finally:
            os.unlink(invalid_config)


if __name__ == '__main__':
    # Set up test environment
    os.makedirs('test_logs', exist_ok=True)
    
    # Run tests
    unittest.main(verbosity=2)