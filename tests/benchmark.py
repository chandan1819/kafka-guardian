#!/usr/bin/env python3
"""
Performance benchmarking script for Kafka Self-Healing system.
"""

import asyncio
import json
import time
import statistics
import psutil
import argparse
from pathlib import Path
from typing import List, Dict, Any
import tempfile
import yaml
import subprocess

from src.kafka_self_healing.main import SelfHealingSystem
from src.kafka_self_healing.monitoring import MonitoringService
from src.kafka_self_healing.models import NodeConfig


class PerformanceBenchmark:
    """Performance benchmarking for the self-healing system."""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.system = None
        self.results = {}
    
    def setup(self):
        """Set up the benchmarking environment."""
        self.system = SelfHealingSystem(self.config_file)
        
    def teardown(self):
        """Clean up after benchmarking."""
        if self.system:
            self.system.stop()
    
    def benchmark_monitoring_latency(self, duration_seconds: int = 60) -> Dict[str, Any]:
        """Benchmark monitoring latency and throughput."""
        print(f"Benchmarking monitoring latency for {duration_seconds} seconds...")
        
        self.system.start()
        
        latencies = []
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            # Measure single monitoring cycle latency
            cycle_start = time.time()
            
            # Wait for next monitoring cycle
            time.sleep(5)  # Monitoring interval
            
            cycle_end = time.time()
            cycle_latency = cycle_end - cycle_start
            latencies.append(cycle_latency)
        
        self.system.stop()
        
        return {
            'avg_latency_ms': statistics.mean(latencies) * 1000,
            'min_latency_ms': min(latencies) * 1000,
            'max_latency_ms': max(latencies) * 1000,
            'p95_latency_ms': statistics.quantiles(latencies, n=20)[18] * 1000,
            'p99_latency_ms': statistics.quantiles(latencies, n=100)[98] * 1000,
            'total_cycles': len(latencies),
            'throughput_cycles_per_sec': len(latencies) / duration_seconds
        }
    
    def benchmark_memory_usage(self, duration_seconds: int = 300) -> Dict[str, Any]:
        """Benchmark memory usage over time."""
        print(f"Benchmarking memory usage for {duration_seconds} seconds...")
        
        process = psutil.Process()
        baseline_memory = process.memory_info().rss
        
        self.system.start()
        
        memory_samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            current_memory = process.memory_info().rss
            memory_samples.append(current_memory)
            time.sleep(5)
        
        self.system.stop()
        
        memory_growth = [m - baseline_memory for m in memory_samples]
        
        return {
            'baseline_memory_mb': baseline_memory / 1024 / 1024,
            'avg_memory_mb': statistics.mean(memory_samples) / 1024 / 1024,
            'max_memory_mb': max(memory_samples) / 1024 / 1024,
            'memory_growth_mb': max(memory_growth) / 1024 / 1024,
            'memory_stable': max(memory_growth) < 10 * 1024 * 1024  # Less than 10MB growth
        }
    
    def benchmark_cpu_usage(self, duration_seconds: int = 120) -> Dict[str, Any]:
        """Benchmark CPU usage."""
        print(f"Benchmarking CPU usage for {duration_seconds} seconds...")
        
        process = psutil.Process()
        
        self.system.start()
        
        cpu_samples = []
        start_time = time.time()
        
        while time.time() - start_time < duration_seconds:
            cpu_percent = process.cpu_percent(interval=1)
            cpu_samples.append(cpu_percent)
        
        self.system.stop()
        
        return {
            'avg_cpu_percent': statistics.mean(cpu_samples),
            'max_cpu_percent': max(cpu_samples),
            'p95_cpu_percent': statistics.quantiles(cpu_samples, n=20)[18] if len(cpu_samples) > 20 else max(cpu_samples),
            'cpu_efficient': statistics.mean(cpu_samples) < 5.0  # Less than 5% average
        }
    
    def benchmark_concurrent_monitoring(self, node_count: int = 10) -> Dict[str, Any]:
        """Benchmark monitoring performance with multiple nodes."""
        print(f"Benchmarking concurrent monitoring with {node_count} nodes...")
        
        # Create config with multiple mock nodes
        config = self.create_multi_node_config(node_count)
        config_file = self.write_temp_config(config)
        
        try:
            system = SelfHealingSystem(config_file)
            
            start_time = time.time()
            system.start()
            
            # Let it run several monitoring cycles
            time.sleep(30)
            
            # Measure concurrent monitoring performance
            monitoring_service = system.monitoring_service
            
            # Check that all nodes are being monitored
            monitored_nodes = 0
            total_response_time = 0
            
            for i in range(node_count):
                node_id = f"mock_node_{i}"
                status = monitoring_service.get_node_status(node_id)
                if status:
                    monitored_nodes += 1
                    total_response_time += status.response_time_ms
            
            system.stop()
            
            return {
                'total_nodes': node_count,
                'monitored_nodes': monitored_nodes,
                'monitoring_coverage': monitored_nodes / node_count,
                'avg_response_time_ms': total_response_time / max(monitored_nodes, 1),
                'concurrent_efficiency': monitored_nodes >= node_count * 0.9
            }
            
        finally:
            import os
            os.unlink(config_file)
    
    def benchmark_recovery_performance(self) -> Dict[str, Any]:
        """Benchmark recovery action performance."""
        print("Benchmarking recovery performance...")
        
        self.system.start()
        
        # Simulate recovery scenarios
        recovery_times = []
        
        for i in range(5):  # Test 5 recovery scenarios
            start_time = time.time()
            
            # Mock a recovery action
            from src.kafka_self_healing.models import NodeConfig
            node_config = NodeConfig(
                node_id=f"test_node_{i}",
                node_type="kafka_broker",
                host="localhost",
                port=9092,
                jmx_port=9999,
                monitoring_methods=["socket"],
                recovery_actions=["restart_service"],
                retry_policy=None
            )
            
            # Execute recovery (mocked)
            result = self.system.recovery_engine.execute_recovery(node_config, "connection_failure")
            
            end_time = time.time()
            recovery_times.append(end_time - start_time)
        
        self.system.stop()
        
        return {
            'avg_recovery_time_ms': statistics.mean(recovery_times) * 1000,
            'max_recovery_time_ms': max(recovery_times) * 1000,
            'recovery_efficiency': statistics.mean(recovery_times) < 5.0  # Less than 5 seconds
        }
    
    def create_multi_node_config(self, node_count: int) -> Dict[str, Any]:
        """Create configuration with multiple mock nodes."""
        kafka_brokers = []
        zookeeper_nodes = []
        
        for i in range(node_count // 2):
            kafka_brokers.append({
                "node_id": f"mock_kafka_{i}",
                "host": "localhost",
                "port": 9092 + i,
                "jmx_port": 9999 + i
            })
        
        for i in range(node_count - len(kafka_brokers)):
            zookeeper_nodes.append({
                "node_id": f"mock_zk_{i}",
                "host": "localhost", 
                "port": 2181 + i
            })
        
        return {
            "cluster": {
                "kafka_brokers": kafka_brokers,
                "zookeeper_nodes": zookeeper_nodes
            },
            "monitoring": {
                "interval_seconds": 5,
                "timeout_seconds": 10,
                "methods": ["socket"]
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
                    "from_email": "test@example.com",
                    "to_emails": ["admin@example.com"]
                }
            },
            "logging": {
                "level": "INFO",
                "file": "test_logs/benchmark.log"
            }
        }
    
    def write_temp_config(self, config: Dict[str, Any]) -> str:
        """Write configuration to temporary file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            return f.name
    
    def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all performance benchmarks."""
        print("Starting comprehensive performance benchmarks...")
        
        results = {}
        
        try:
            # Monitoring latency benchmark
            results['monitoring_latency'] = self.benchmark_monitoring_latency(60)
            
            # Memory usage benchmark
            results['memory_usage'] = self.benchmark_memory_usage(120)
            
            # CPU usage benchmark  
            results['cpu_usage'] = self.benchmark_cpu_usage(60)
            
            # Concurrent monitoring benchmark
            results['concurrent_monitoring'] = self.benchmark_concurrent_monitoring(10)
            
            # Recovery performance benchmark
            results['recovery_performance'] = self.benchmark_recovery_performance()
            
        except Exception as e:
            print(f"Benchmark failed: {e}")
            results['error'] = str(e)
        
        return results
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a performance report."""
        report = []
        report.append("=" * 60)
        report.append("KAFKA SELF-HEALING SYSTEM PERFORMANCE REPORT")
        report.append("=" * 60)
        report.append("")
        
        if 'monitoring_latency' in results:
            ml = results['monitoring_latency']
            report.append("MONITORING LATENCY:")
            report.append(f"  Average: {ml['avg_latency_ms']:.2f}ms")
            report.append(f"  P95: {ml['p95_latency_ms']:.2f}ms")
            report.append(f"  P99: {ml['p99_latency_ms']:.2f}ms")
            report.append(f"  Throughput: {ml['throughput_cycles_per_sec']:.2f} cycles/sec")
            report.append("")
        
        if 'memory_usage' in results:
            mu = results['memory_usage']
            report.append("MEMORY USAGE:")
            report.append(f"  Baseline: {mu['baseline_memory_mb']:.1f}MB")
            report.append(f"  Average: {mu['avg_memory_mb']:.1f}MB")
            report.append(f"  Maximum: {mu['max_memory_mb']:.1f}MB")
            report.append(f"  Growth: {mu['memory_growth_mb']:.1f}MB")
            report.append(f"  Stable: {'✓' if mu['memory_stable'] else '✗'}")
            report.append("")
        
        if 'cpu_usage' in results:
            cu = results['cpu_usage']
            report.append("CPU USAGE:")
            report.append(f"  Average: {cu['avg_cpu_percent']:.2f}%")
            report.append(f"  Maximum: {cu['max_cpu_percent']:.2f}%")
            report.append(f"  P95: {cu['p95_cpu_percent']:.2f}%")
            report.append(f"  Efficient: {'✓' if cu['cpu_efficient'] else '✗'}")
            report.append("")
        
        if 'concurrent_monitoring' in results:
            cm = results['concurrent_monitoring']
            report.append("CONCURRENT MONITORING:")
            report.append(f"  Total Nodes: {cm['total_nodes']}")
            report.append(f"  Monitored: {cm['monitored_nodes']}")
            report.append(f"  Coverage: {cm['monitoring_coverage']:.1%}")
            report.append(f"  Avg Response: {cm['avg_response_time_ms']:.2f}ms")
            report.append(f"  Efficient: {'✓' if cm['concurrent_efficiency'] else '✗'}")
            report.append("")
        
        if 'recovery_performance' in results:
            rp = results['recovery_performance']
            report.append("RECOVERY PERFORMANCE:")
            report.append(f"  Average Time: {rp['avg_recovery_time_ms']:.2f}ms")
            report.append(f"  Maximum Time: {rp['max_recovery_time_ms']:.2f}ms")
            report.append(f"  Efficient: {'✓' if rp['recovery_efficiency'] else '✗'}")
            report.append("")
        
        report.append("=" * 60)
        
        return "\n".join(report)


def main():
    """Main benchmarking entry point."""
    parser = argparse.ArgumentParser(description='Kafka Self-Healing Performance Benchmark')
    parser.add_argument('--config', required=True, help='Configuration file path')
    parser.add_argument('--output', help='Output file for results (JSON)')
    parser.add_argument('--report', help='Output file for human-readable report')
    
    args = parser.parse_args()
    
    # Create benchmark instance
    benchmark = PerformanceBenchmark(args.config)
    benchmark.setup()
    
    try:
        # Run benchmarks
        results = benchmark.run_all_benchmarks()
        
        # Save JSON results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"Results saved to {args.output}")
        
        # Generate and save report
        report = benchmark.generate_report(results)
        
        if args.report:
            with open(args.report, 'w') as f:
                f.write(report)
            print(f"Report saved to {args.report}")
        else:
            print(report)
    
    finally:
        benchmark.teardown()


if __name__ == '__main__':
    main()