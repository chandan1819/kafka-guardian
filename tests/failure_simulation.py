#!/usr/bin/env python3
"""
Failure simulation script for testing the Kafka Self-Healing system.
This script provides various failure scenarios to test system resilience.
"""

import subprocess
import time
import random
import argparse
from typing import List, Dict, Any
from enum import Enum
import threading
import signal
import sys


class FailureType(Enum):
    """Types of failures that can be simulated."""
    KAFKA_BROKER_STOP = "kafka_broker_stop"
    KAFKA_BROKER_KILL = "kafka_broker_kill"
    ZOOKEEPER_STOP = "zookeeper_stop"
    ZOOKEEPER_KILL = "zookeeper_kill"
    NETWORK_PARTITION = "network_partition"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    PARTIAL_CLUSTER_FAILURE = "partial_cluster_failure"
    CASCADING_FAILURE = "cascading_failure"


class FailureSimulator:
    """Simulates various failure scenarios for testing."""
    
    def __init__(self, docker_compose_file: str = "docker-compose.test.yml"):
        self.docker_compose_file = docker_compose_file
        self.active_failures = []
        self.running = False
        self.simulation_thread = None
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print(f"\nReceived signal {signum}, shutting down...")
        self.stop_simulation()
        sys.exit(0)
    
    def simulate_kafka_broker_failure(self, broker_id: str, duration: int = 30):
        """Simulate Kafka broker failure."""
        container_name = f"test-kafka{broker_id}"
        
        print(f"Simulating failure: Stopping {container_name} for {duration} seconds")
        
        try:
            # Stop the container
            subprocess.run([
                "docker", "stop", container_name
            ], check=True, capture_output=True)
            
            self.active_failures.append({
                'type': FailureType.KAFKA_BROKER_STOP,
                'container': container_name,
                'start_time': time.time(),
                'duration': duration
            })
            
            # Wait for the specified duration
            time.sleep(duration)
            
            # Restart the container
            subprocess.run([
                "docker", "start", container_name
            ], check=True, capture_output=True)
            
            print(f"Recovered: Restarted {container_name}")
            
            # Remove from active failures
            self.active_failures = [f for f in self.active_failures 
                                  if f['container'] != container_name]
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to simulate broker failure: {e}")
    
    def simulate_zookeeper_failure(self, duration: int = 30):
        """Simulate Zookeeper failure."""
        container_name = "test-zookeeper"
        
        print(f"Simulating failure: Stopping {container_name} for {duration} seconds")
        
        try:
            # Stop the container
            subprocess.run([
                "docker", "stop", container_name
            ], check=True, capture_output=True)
            
            self.active_failures.append({
                'type': FailureType.ZOOKEEPER_STOP,
                'container': container_name,
                'start_time': time.time(),
                'duration': duration
            })
            
            # Wait for the specified duration
            time.sleep(duration)
            
            # Restart the container
            subprocess.run([
                "docker", "start", container_name
            ], check=True, capture_output=True)
            
            print(f"Recovered: Restarted {container_name}")
            
            # Remove from active failures
            self.active_failures = [f for f in self.active_failures 
                                  if f['container'] != container_name]
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to simulate Zookeeper failure: {e}")
    
    def simulate_network_partition(self, duration: int = 60):
        """Simulate network partition by blocking traffic."""
        print(f"Simulating network partition for {duration} seconds")
        
        try:
            # Block traffic to Kafka ports using iptables
            containers = ["test-kafka1", "test-kafka2"]
            
            for container in containers:
                # Get container IP
                result = subprocess.run([
                    "docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", 
                    container
                ], capture_output=True, text=True, check=True)
                
                container_ip = result.stdout.strip()
                
                if container_ip:
                    # Block incoming traffic to container
                    subprocess.run([
                        "docker", "exec", container,
                        "iptables", "-A", "INPUT", "-j", "DROP"
                    ], capture_output=True)
            
            self.active_failures.append({
                'type': FailureType.NETWORK_PARTITION,
                'containers': containers,
                'start_time': time.time(),
                'duration': duration
            })
            
            # Wait for the specified duration
            time.sleep(duration)
            
            # Restore network connectivity
            for container in containers:
                subprocess.run([
                    "docker", "exec", container,
                    "iptables", "-F", "INPUT"
                ], capture_output=True)
            
            print("Recovered: Network partition resolved")
            
            # Remove from active failures
            self.active_failures = [f for f in self.active_failures 
                                  if f['type'] != FailureType.NETWORK_PARTITION]
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to simulate network partition: {e}")
    
    def simulate_resource_exhaustion(self, container: str, duration: int = 45):
        """Simulate resource exhaustion (CPU/Memory)."""
        print(f"Simulating resource exhaustion on {container} for {duration} seconds")
        
        try:
            # Start CPU stress test
            stress_cmd = [
                "docker", "exec", "-d", container,
                "bash", "-c", 
                "for i in {1..4}; do while true; do :; done & done"
            ]
            
            subprocess.run(stress_cmd, check=True, capture_output=True)
            
            self.active_failures.append({
                'type': FailureType.RESOURCE_EXHAUSTION,
                'container': container,
                'start_time': time.time(),
                'duration': duration
            })
            
            # Wait for the specified duration
            time.sleep(duration)
            
            # Kill stress processes
            subprocess.run([
                "docker", "exec", container,
                "pkill", "-f", "bash"
            ], capture_output=True)
            
            print(f"Recovered: Resource exhaustion resolved on {container}")
            
            # Remove from active failures
            self.active_failures = [f for f in self.active_failures 
                                  if not (f['type'] == FailureType.RESOURCE_EXHAUSTION 
                                         and f['container'] == container)]
            
        except subprocess.CalledProcessError as e:
            print(f"Failed to simulate resource exhaustion: {e}")
    
    def simulate_cascading_failure(self):
        """Simulate cascading failure scenario."""
        print("Simulating cascading failure scenario")
        
        # Start with Zookeeper failure
        threading.Thread(target=self.simulate_zookeeper_failure, args=(20,)).start()
        
        # Wait a bit, then fail first Kafka broker
        time.sleep(10)
        threading.Thread(target=self.simulate_kafka_broker_failure, args=("1", 30)).start()
        
        # Wait a bit more, then fail second Kafka broker
        time.sleep(15)
        threading.Thread(target=self.simulate_kafka_broker_failure, args=("2", 25)).start()
        
        print("Cascading failure scenario initiated")
    
    def simulate_partial_cluster_failure(self):
        """Simulate partial cluster failure."""
        print("Simulating partial cluster failure")
        
        # Fail one Kafka broker and Zookeeper simultaneously
        threading.Thread(target=self.simulate_kafka_broker_failure, args=("2", 60)).start()
        threading.Thread(target=self.simulate_zookeeper_failure, args=(45)).start()
        
        print("Partial cluster failure scenario initiated")
    
    def run_random_failures(self, duration: int = 300, interval_range: tuple = (30, 120)):
        """Run random failure scenarios for testing."""
        print(f"Starting random failure simulation for {duration} seconds")
        
        self.running = True
        start_time = time.time()
        
        failure_scenarios = [
            lambda: self.simulate_kafka_broker_failure("1", random.randint(20, 60)),
            lambda: self.simulate_kafka_broker_failure("2", random.randint(20, 60)),
            lambda: self.simulate_zookeeper_failure(random.randint(15, 45)),
            lambda: self.simulate_resource_exhaustion("test-kafka1", random.randint(30, 60)),
            lambda: self.simulate_resource_exhaustion("test-kafka2", random.randint(30, 60)),
        ]
        
        while self.running and (time.time() - start_time) < duration:
            # Wait for random interval
            wait_time = random.randint(interval_range[0], interval_range[1])
            
            for _ in range(wait_time):
                if not self.running:
                    break
                time.sleep(1)
            
            if not self.running:
                break
            
            # Choose random failure scenario
            scenario = random.choice(failure_scenarios)
            
            # Run scenario in background thread
            threading.Thread(target=scenario).start()
        
        print("Random failure simulation completed")
    
    def start_chaos_testing(self, duration: int = 600):
        """Start comprehensive chaos testing."""
        print(f"Starting chaos testing for {duration} seconds")
        
        self.running = True
        self.simulation_thread = threading.Thread(
            target=self.run_random_failures, 
            args=(duration, (20, 90))
        )
        self.simulation_thread.start()
    
    def stop_simulation(self):
        """Stop all running simulations."""
        print("Stopping failure simulation...")
        
        self.running = False
        
        # Wait for simulation thread to finish
        if self.simulation_thread and self.simulation_thread.is_alive():
            self.simulation_thread.join(timeout=10)
        
        # Recover from any active failures
        self.recover_all_failures()
        
        print("Failure simulation stopped")
    
    def recover_all_failures(self):
        """Recover from all active failures."""
        print("Recovering from all active failures...")
        
        for failure in self.active_failures:
            try:
                if failure['type'] in [FailureType.KAFKA_BROKER_STOP, FailureType.ZOOKEEPER_STOP]:
                    subprocess.run([
                        "docker", "start", failure['container']
                    ], capture_output=True)
                    print(f"Recovered: Restarted {failure['container']}")
                
                elif failure['type'] == FailureType.NETWORK_PARTITION:
                    for container in failure['containers']:
                        subprocess.run([
                            "docker", "exec", container,
                            "iptables", "-F", "INPUT"
                        ], capture_output=True)
                    print("Recovered: Network partition resolved")
                
                elif failure['type'] == FailureType.RESOURCE_EXHAUSTION:
                    subprocess.run([
                        "docker", "exec", failure['container'],
                        "pkill", "-f", "bash"
                    ], capture_output=True)
                    print(f"Recovered: Resource exhaustion resolved on {failure['container']}")
                    
            except subprocess.CalledProcessError as e:
                print(f"Failed to recover from failure: {e}")
        
        self.active_failures.clear()
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """Get current cluster status."""
        status = {
            'zookeeper': self._check_container_status('test-zookeeper'),
            'kafka1': self._check_container_status('test-kafka1'),
            'kafka2': self._check_container_status('test-kafka2'),
            'active_failures': len(self.active_failures),
            'failure_details': self.active_failures
        }
        
        return status
    
    def _check_container_status(self, container_name: str) -> str:
        """Check the status of a Docker container."""
        try:
            result = subprocess.run([
                "docker", "inspect", "-f", "{{.State.Status}}", container_name
            ], capture_output=True, text=True, check=True)
            
            return result.stdout.strip()
            
        except subprocess.CalledProcessError:
            return "not_found"
    
    def print_status(self):
        """Print current cluster and failure status."""
        status = self.get_cluster_status()
        
        print("\n" + "="*50)
        print("CLUSTER STATUS")
        print("="*50)
        print(f"Zookeeper: {status['zookeeper']}")
        print(f"Kafka1: {status['kafka1']}")
        print(f"Kafka2: {status['kafka2']}")
        print(f"Active Failures: {status['active_failures']}")
        
        if status['failure_details']:
            print("\nActive Failure Details:")
            for failure in status['failure_details']:
                elapsed = time.time() - failure['start_time']
                remaining = max(0, failure['duration'] - elapsed)
                print(f"  - {failure['type'].value}: {remaining:.1f}s remaining")
        
        print("="*50)


def main():
    """Main entry point for failure simulation."""
    parser = argparse.ArgumentParser(description='Kafka Cluster Failure Simulator')
    parser.add_argument('--scenario', choices=[
        'kafka1_failure', 'kafka2_failure', 'zookeeper_failure',
        'network_partition', 'resource_exhaustion', 'cascading_failure',
        'partial_cluster_failure', 'chaos_testing', 'random_failures'
    ], required=True, help='Failure scenario to simulate')
    
    parser.add_argument('--duration', type=int, default=60, 
                       help='Duration of failure in seconds (default: 60)')
    parser.add_argument('--docker-compose', default='docker-compose.test.yml',
                       help='Docker compose file to use')
    parser.add_argument('--status-interval', type=int, default=10,
                       help='Status reporting interval in seconds')
    
    args = parser.parse_args()
    
    simulator = FailureSimulator(args.docker_compose)
    
    # Start status reporting thread
    def status_reporter():
        while simulator.running:
            simulator.print_status()
            time.sleep(args.status_interval)
    
    try:
        if args.scenario == 'kafka1_failure':
            simulator.simulate_kafka_broker_failure("1", args.duration)
        
        elif args.scenario == 'kafka2_failure':
            simulator.simulate_kafka_broker_failure("2", args.duration)
        
        elif args.scenario == 'zookeeper_failure':
            simulator.simulate_zookeeper_failure(args.duration)
        
        elif args.scenario == 'network_partition':
            simulator.simulate_network_partition(args.duration)
        
        elif args.scenario == 'resource_exhaustion':
            simulator.simulate_resource_exhaustion("test-kafka1", args.duration)
        
        elif args.scenario == 'cascading_failure':
            simulator.simulate_cascading_failure()
            time.sleep(args.duration)
        
        elif args.scenario == 'partial_cluster_failure':
            simulator.simulate_partial_cluster_failure()
            time.sleep(args.duration)
        
        elif args.scenario == 'chaos_testing':
            # Start status reporting
            status_thread = threading.Thread(target=status_reporter)
            status_thread.daemon = True
            status_thread.start()
            
            simulator.start_chaos_testing(args.duration)
            simulator.simulation_thread.join()
        
        elif args.scenario == 'random_failures':
            # Start status reporting
            status_thread = threading.Thread(target=status_reporter)
            status_thread.daemon = True
            status_thread.start()
            
            simulator.run_random_failures(args.duration)
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        simulator.stop_simulation()


if __name__ == '__main__':
    main()