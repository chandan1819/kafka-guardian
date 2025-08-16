"""
Integration module for connecting monitoring failures to recovery actions.

This module provides failure type classification, workflow coordination,
and callback management for the monitoring-recovery integration.
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

from .models import NodeConfig, NodeStatus, RecoveryResult
from .monitoring import MonitoringService
from .recovery import RecoveryEngine
from .exceptions import SystemError


class FailureType(Enum):
    """Classification of different failure types."""
    HEALTH_CHECK_FAILURE = "health_check_failure"
    CONNECTION_TIMEOUT = "connection_timeout"
    AUTHENTICATION_FAILURE = "authentication_failure"
    SERVICE_UNAVAILABLE = "service_unavailable"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_UNREACHABLE = "network_unreachable"
    JMX_CONNECTION_FAILURE = "jmx_connection_failure"
    ZOOKEEPER_FAILURE = "zookeeper_failure"
    UNKNOWN_FAILURE = "unknown_failure"


@dataclass
class FailureEvent:
    """Represents a failure event with context."""
    node_config: NodeConfig
    node_status: NodeStatus
    failure_type: FailureType
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            'node_id': self.node_config.node_id,
            'node_type': self.node_config.node_type,
            'host': self.node_config.host,
            'port': self.node_config.port,
            'failure_type': self.failure_type.value,
            'is_healthy': self.node_status.is_healthy,
            'error_message': self.node_status.error_message,
            'monitoring_method': self.node_status.monitoring_method,
            'response_time_ms': self.node_status.response_time_ms,
            'timestamp': self.timestamp.isoformat(),
            'context': self.context
        }


@dataclass
class RecoveryEvent:
    """Represents a recovery event with results."""
    node_config: NodeConfig
    recovery_result: RecoveryResult
    failure_event: FailureEvent
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            'node_id': self.node_config.node_id,
            'recovery_action': self.recovery_result.action_type,
            'success': self.recovery_result.success,
            'exit_code': self.recovery_result.exit_code,
            'command': self.recovery_result.command_executed,
            'failure_type': self.failure_event.failure_type.value,
            'timestamp': self.timestamp.isoformat()
        }


class FailureClassifier:
    """Classifies failures based on node status and error patterns."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Error patterns for classification
        self.error_patterns = {
            FailureType.CONNECTION_TIMEOUT: [
                'timeout', 'timed out', 'connection timeout',
                'read timeout', 'connect timeout'
            ],
            FailureType.AUTHENTICATION_FAILURE: [
                'authentication failed', 'auth failed', 'unauthorized',
                'access denied', 'permission denied', 'invalid credentials'
            ],
            FailureType.SERVICE_UNAVAILABLE: [
                'service unavailable', 'connection refused', 'no route to host',
                'service not available', 'server not available'
            ],
            FailureType.RESOURCE_EXHAUSTION: [
                'out of memory', 'disk full', 'no space left',
                'resource exhausted', 'too many connections'
            ],
            FailureType.NETWORK_UNREACHABLE: [
                'network unreachable', 'host unreachable', 'no route',
                'network is down', 'destination unreachable'
            ],
            FailureType.JMX_CONNECTION_FAILURE: [
                'jmx', 'mbean', 'management', 'jconsole',
                'remote management', 'jmx connection'
            ],
            FailureType.ZOOKEEPER_FAILURE: [
                'zookeeper', 'zk', 'ensemble', 'quorum',
                'leader election', 'znode'
            ]
        }
    
    def classify_failure(self, node_config: NodeConfig, node_status: NodeStatus) -> FailureType:
        """
        Classify the type of failure based on node status and error message.
        
        Args:
            node_config: Configuration of the failed node
            node_status: Current status of the node
            
        Returns:
            FailureType: Classified failure type
        """
        if node_status.is_healthy:
            # This shouldn't happen, but handle gracefully
            self.logger.warning(f"classify_failure called for healthy node {node_config.node_id}")
            return FailureType.UNKNOWN_FAILURE
        
        error_message = (node_status.error_message or "").lower()
        monitoring_method = (node_status.monitoring_method or "").lower()
        
        # Check error message patterns
        for failure_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern in error_message:
                    self.logger.debug(f"Classified failure as {failure_type.value} based on pattern '{pattern}'")
                    return failure_type
        
        # Check monitoring method specific failures
        if 'jmx' in monitoring_method and 'connection' in error_message:
            return FailureType.JMX_CONNECTION_FAILURE
        
        if 'zookeeper' in monitoring_method:
            return FailureType.ZOOKEEPER_FAILURE
        
        # Check response time for timeout classification
        if node_status.response_time_ms > 10000:  # More than 10 seconds
            return FailureType.CONNECTION_TIMEOUT
        
        # Default classification
        self.logger.debug(f"Could not classify failure for {node_config.node_id}, using HEALTH_CHECK_FAILURE")
        return FailureType.HEALTH_CHECK_FAILURE
    
    def get_recovery_priority(self, failure_type: FailureType) -> int:
        """
        Get recovery priority for a failure type (lower number = higher priority).
        
        Args:
            failure_type: The type of failure
            
        Returns:
            int: Priority level (0-10, where 0 is highest priority)
        """
        priority_map = {
            FailureType.SERVICE_UNAVAILABLE: 1,
            FailureType.HEALTH_CHECK_FAILURE: 2,
            FailureType.CONNECTION_TIMEOUT: 3,
            FailureType.JMX_CONNECTION_FAILURE: 4,
            FailureType.ZOOKEEPER_FAILURE: 2,
            FailureType.RESOURCE_EXHAUSTION: 1,
            FailureType.NETWORK_UNREACHABLE: 5,
            FailureType.AUTHENTICATION_FAILURE: 8,
            FailureType.UNKNOWN_FAILURE: 5
        }
        return priority_map.get(failure_type, 5)
    
    def get_recommended_actions(self, failure_type: FailureType, node_type: str) -> List[str]:
        """
        Get recommended recovery actions for a failure type and node type.
        
        Args:
            failure_type: The type of failure
            node_type: The type of node ('kafka_broker' or 'zookeeper')
            
        Returns:
            List[str]: Recommended recovery action types in order of preference
        """
        # Base recommendations by failure type
        action_map = {
            FailureType.SERVICE_UNAVAILABLE: ['service_restart', 'script_recovery'],
            FailureType.HEALTH_CHECK_FAILURE: ['service_restart', 'script_recovery'],
            FailureType.CONNECTION_TIMEOUT: ['service_restart', 'network_check'],
            FailureType.JMX_CONNECTION_FAILURE: ['jmx_restart', 'service_restart'],
            FailureType.ZOOKEEPER_FAILURE: ['zk_restart', 'service_restart'],
            FailureType.RESOURCE_EXHAUSTION: ['cleanup_logs', 'service_restart'],
            FailureType.NETWORK_UNREACHABLE: ['network_check', 'service_restart'],
            FailureType.AUTHENTICATION_FAILURE: ['credential_refresh', 'service_restart'],
            FailureType.UNKNOWN_FAILURE: ['service_restart', 'script_recovery']
        }
        
        base_actions = action_map.get(failure_type, ['service_restart'])
        
        # Add node-type specific actions
        if node_type == 'kafka_broker':
            if 'service_restart' in base_actions:
                base_actions = ['kafka_restart' if action == 'service_restart' else action 
                              for action in base_actions]
        elif node_type == 'zookeeper':
            if 'service_restart' in base_actions:
                base_actions = ['zookeeper_restart' if action == 'service_restart' else action 
                              for action in base_actions]
        
        return base_actions


class MonitoringRecoveryIntegrator:
    """
    Integrates monitoring service with recovery engine.
    
    Provides workflow coordination, failure classification, and callback management.
    """
    
    def __init__(self, monitoring_service: MonitoringService, recovery_engine: RecoveryEngine):
        """
        Initialize the integrator.
        
        Args:
            monitoring_service: The monitoring service instance
            recovery_engine: The recovery engine instance
        """
        self.monitoring_service = monitoring_service
        self.recovery_engine = recovery_engine
        self.failure_classifier = FailureClassifier()
        self.logger = logging.getLogger(__name__)
        
        # Event tracking
        self.failure_events: Dict[str, List[FailureEvent]] = {}
        self.recovery_events: Dict[str, List[RecoveryEvent]] = {}
        
        # Callback management
        self.failure_callbacks: List[Callable[[FailureEvent], None]] = []
        self.recovery_callbacks: List[Callable[[RecoveryEvent], None]] = []
        self.escalation_callbacks: List[Callable[[str, List[RecoveryResult]], None]] = []
        
        # Workflow state
        self.active_recoveries: Dict[str, FailureEvent] = {}
        self.recovery_cooldown: Dict[str, datetime] = {}
        
        # Configuration
        self.cooldown_period_seconds = 300  # 5 minutes
        self.max_concurrent_recoveries = 5
        
        # Wire up the integration
        self._setup_integration()
    
    def _setup_integration(self) -> None:
        """Setup integration between monitoring and recovery services."""
        # Register callbacks with monitoring service
        self.monitoring_service.register_failure_callback(self._handle_node_failure)
        self.monitoring_service.register_recovery_callback(self._handle_node_recovery)
        
        # Register escalation callback with recovery engine
        self.recovery_engine.register_escalation_callback(self._handle_recovery_escalation)
        
        self.logger.info("Monitoring-recovery integration setup completed")
    
    def _handle_node_failure(self, node_config: NodeConfig, node_status: NodeStatus) -> None:
        """
        Handle node failure detected by monitoring service.
        
        Args:
            node_config: Configuration of the failed node
            node_status: Current status of the node
        """
        try:
            # Check if node is in cooldown period
            if self._is_in_cooldown(node_config.node_id):
                self.logger.info(f"Node {node_config.node_id} is in cooldown period, skipping recovery")
                return
            
            # Check concurrent recovery limit
            if len(self.active_recoveries) >= self.max_concurrent_recoveries:
                self.logger.warning(f"Maximum concurrent recoveries reached, queuing {node_config.node_id}")
                return
            
            # Classify the failure
            failure_type = self.failure_classifier.classify_failure(node_config, node_status)
            
            # Create failure event
            failure_event = FailureEvent(
                node_config=node_config,
                node_status=node_status,
                failure_type=failure_type,
                context={
                    'monitoring_method': node_status.monitoring_method,
                    'response_time_ms': node_status.response_time_ms
                }
            )
            
            # Record failure event
            self._record_failure_event(failure_event)
            
            # Trigger failure callbacks
            for callback in self.failure_callbacks:
                try:
                    callback(failure_event)
                except Exception as e:
                    self.logger.error(f"Error in failure callback: {e}")
            
            # Start recovery process
            self._initiate_recovery(failure_event)
            
        except Exception as e:
            self.logger.error(f"Error handling node failure for {node_config.node_id}: {e}")
    
    def _handle_node_recovery(self, node_config: NodeConfig, node_status: NodeStatus) -> None:
        """
        Handle node recovery detected by monitoring service.
        
        Args:
            node_config: Configuration of the recovered node
            node_status: Current status of the node
        """
        try:
            node_id = node_config.node_id
            
            # Check if we were tracking this recovery
            if node_id in self.active_recoveries:
                failure_event = self.active_recoveries.pop(node_id)
                
                # Get recovery history to find successful action
                recovery_history = self.recovery_engine.get_recovery_history(node_id)
                if recovery_history:
                    successful_result = recovery_history[-1]
                    if successful_result.success:
                        # Create recovery event
                        recovery_event = RecoveryEvent(
                            node_config=node_config,
                            recovery_result=successful_result,
                            failure_event=failure_event
                        )
                        
                        # Record recovery event
                        self._record_recovery_event(recovery_event)
                        
                        # Trigger recovery callbacks
                        for callback in self.recovery_callbacks:
                            try:
                                callback(recovery_event)
                            except Exception as e:
                                self.logger.error(f"Error in recovery callback: {e}")
                        
                        self.logger.info(f"Node {node_id} recovered successfully using {successful_result.action_type}")
                
                # Set cooldown period
                self.recovery_cooldown[node_id] = datetime.now() + timedelta(seconds=self.cooldown_period_seconds)
            
        except Exception as e:
            self.logger.error(f"Error handling node recovery for {node_config.node_id}: {e}")
    
    def _handle_recovery_escalation(self, node_id: str, recovery_history: List[RecoveryResult]) -> None:
        """
        Handle recovery escalation when all recovery attempts fail.
        
        Args:
            node_id: ID of the node that failed recovery
            recovery_history: History of recovery attempts
        """
        try:
            # Remove from active recoveries
            failure_event = self.active_recoveries.pop(node_id, None)
            
            # Set extended cooldown period for failed recoveries
            extended_cooldown = datetime.now() + timedelta(seconds=self.cooldown_period_seconds * 3)
            self.recovery_cooldown[node_id] = extended_cooldown
            
            # Trigger escalation callbacks
            for callback in self.escalation_callbacks:
                try:
                    callback(node_id, recovery_history)
                except Exception as e:
                    self.logger.error(f"Error in escalation callback: {e}")
            
            self.logger.error(f"Recovery escalated for node {node_id} after {len(recovery_history)} attempts")
            
        except Exception as e:
            self.logger.error(f"Error handling recovery escalation for {node_id}: {e}")
    
    def _initiate_recovery(self, failure_event: FailureEvent) -> None:
        """
        Initiate recovery process for a failure event.
        
        Args:
            failure_event: The failure event to recover from
        """
        node_config = failure_event.node_config
        node_id = node_config.node_id
        
        try:
            # Mark as active recovery
            self.active_recoveries[node_id] = failure_event
            
            # Get recommended actions for this failure type
            recommended_actions = self.failure_classifier.get_recommended_actions(
                failure_event.failure_type, 
                node_config.node_type
            )
            
            # Update node config with recommended actions if not already set
            if not node_config.recovery_actions:
                node_config.recovery_actions = recommended_actions[:2]  # Use top 2 recommendations
            
            # Execute recovery
            self.logger.info(f"Initiating recovery for {node_id} (failure type: {failure_event.failure_type.value})")
            recovery_result = self.recovery_engine.execute_recovery(
                node_config, 
                failure_event.failure_type.value
            )
            
            self.logger.info(f"Recovery attempt for {node_id}: {'SUCCESS' if recovery_result.success else 'FAILED'}")
            
        except Exception as e:
            self.logger.error(f"Error initiating recovery for {node_id}: {e}")
            # Remove from active recoveries on error
            self.active_recoveries.pop(node_id, None)
    
    def _is_in_cooldown(self, node_id: str) -> bool:
        """Check if a node is in cooldown period."""
        if node_id not in self.recovery_cooldown:
            return False
        return datetime.now() < self.recovery_cooldown[node_id]
    
    def _record_failure_event(self, failure_event: FailureEvent) -> None:
        """Record a failure event in history."""
        node_id = failure_event.node_config.node_id
        if node_id not in self.failure_events:
            self.failure_events[node_id] = []
        
        self.failure_events[node_id].append(failure_event)
        
        # Keep only last 50 events per node
        if len(self.failure_events[node_id]) > 50:
            self.failure_events[node_id] = self.failure_events[node_id][-50:]
    
    def _record_recovery_event(self, recovery_event: RecoveryEvent) -> None:
        """Record a recovery event in history."""
        node_id = recovery_event.node_config.node_id
        if node_id not in self.recovery_events:
            self.recovery_events[node_id] = []
        
        self.recovery_events[node_id].append(recovery_event)
        
        # Keep only last 50 events per node
        if len(self.recovery_events[node_id]) > 50:
            self.recovery_events[node_id] = self.recovery_events[node_id][-50:]
    
    def register_failure_callback(self, callback: Callable[[FailureEvent], None]) -> None:
        """Register a callback for failure events."""
        self.failure_callbacks.append(callback)
        self.logger.info(f"Registered failure callback: {callback.__name__}")
    
    def register_recovery_callback(self, callback: Callable[[RecoveryEvent], None]) -> None:
        """Register a callback for recovery events."""
        self.recovery_callbacks.append(callback)
        self.logger.info(f"Registered recovery callback: {callback.__name__}")
    
    def register_escalation_callback(self, callback: Callable[[str, List[RecoveryResult]], None]) -> None:
        """Register a callback for escalation events."""
        self.escalation_callbacks.append(callback)
        self.logger.info(f"Registered escalation callback: {callback.__name__}")
    
    def get_failure_statistics(self) -> Dict[str, Any]:
        """Get failure and recovery statistics."""
        total_failures = sum(len(events) for events in self.failure_events.values())
        total_recoveries = sum(len(events) for events in self.recovery_events.values())
        
        # Count failures by type
        failure_type_counts = {}
        for events in self.failure_events.values():
            for event in events:
                failure_type = event.failure_type.value
                failure_type_counts[failure_type] = failure_type_counts.get(failure_type, 0) + 1
        
        return {
            'total_failures': total_failures,
            'total_recoveries': total_recoveries,
            'active_recoveries': len(self.active_recoveries),
            'nodes_in_cooldown': len(self.recovery_cooldown),
            'failure_types': failure_type_counts,
            'recovery_success_rate': (total_recoveries / total_failures * 100) if total_failures > 0 else 0
        }
    
    def get_node_failure_history(self, node_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get failure history for a specific node."""
        events = self.failure_events.get(node_id, [])
        return [event.to_dict() for event in events[-limit:]]
    
    def get_node_recovery_history(self, node_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recovery history for a specific node."""
        events = self.recovery_events.get(node_id, [])
        return [event.to_dict() for event in events[-limit:]]
    
    def clear_cooldown(self, node_id: str) -> bool:
        """Clear cooldown period for a node."""
        if node_id in self.recovery_cooldown:
            del self.recovery_cooldown[node_id]
            self.logger.info(f"Cleared cooldown for node {node_id}")
            return True
        return False
    
    def set_cooldown_period(self, seconds: int) -> None:
        """Set the cooldown period for recoveries."""
        self.cooldown_period_seconds = seconds
        self.logger.info(f"Set cooldown period to {seconds} seconds")
    
    def set_max_concurrent_recoveries(self, max_recoveries: int) -> None:
        """Set the maximum number of concurrent recoveries."""
        self.max_concurrent_recoveries = max_recoveries
        self.logger.info(f"Set max concurrent recoveries to {max_recoveries}")