"""
Recovery engine system for the Kafka Self-Healing system.

This module provides the core recovery framework including the RecoveryAction base class,
RecoveryEngine orchestrator, and retry logic with exponential backoff.
"""

import abc
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from .exceptions import RecoveryError, ValidationError
from .models import NodeConfig, RecoveryResult, RetryPolicy
from .plugins import RecoveryPlugin


logger = logging.getLogger(__name__)


class RecoveryAction(abc.ABC):
    """Base class for recovery actions."""
    
    def __init__(self, action_type: str, config: Optional[Dict[str, Any]] = None):
        """Initialize the recovery action.
        
        Args:
            action_type: The type of recovery action.
            config: Optional configuration for the action.
        """
        self.action_type = action_type
        self.config = config or {}
        self.name = self.__class__.__name__
    
    @abc.abstractmethod
    def execute(self, node: NodeConfig) -> RecoveryResult:
        """Execute the recovery action.
        
        Args:
            node: The node configuration to recover.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
            
        Raises:
            RecoveryError: If the recovery action fails.
        """
        pass
    
    @abc.abstractmethod
    def validate_config(self) -> bool:
        """Validate the recovery action configuration.
        
        Returns:
            bool: True if configuration is valid.
            
        Raises:
            ValidationError: If configuration is invalid.
        """
        pass
    
    def supports_node_type(self, node_type: str) -> bool:
        """Check if this action supports the given node type.
        
        Args:
            node_type: The type of node ('kafka_broker' or 'zookeeper').
            
        Returns:
            bool: True if the action supports this node type.
        """
        return True  # Default implementation supports all node types
    
    def get_estimated_duration(self) -> int:
        """Get estimated duration for this recovery action in seconds.
        
        Returns:
            int: Estimated duration in seconds.
        """
        return 30  # Default estimate


class RetryManager:
    """Manages retry logic with exponential backoff."""
    
    def __init__(self, retry_policy: RetryPolicy):
        """Initialize the retry manager.
        
        Args:
            retry_policy: The retry policy configuration.
        """
        self.retry_policy = retry_policy
        self.attempt_count = 0
        self.last_attempt_time: Optional[datetime] = None
    
    def should_retry(self) -> bool:
        """Check if another retry attempt should be made.
        
        Returns:
            bool: True if another retry should be attempted.
        """
        return self.attempt_count < self.retry_policy.max_attempts
    
    def get_next_delay(self) -> float:
        """Calculate the delay before the next retry attempt.
        
        Returns:
            float: Delay in seconds before next retry.
        """
        if self.attempt_count == 0:
            return 0  # No delay for first attempt
        
        # Calculate exponential backoff delay
        delay = self.retry_policy.initial_delay_seconds * (
            self.retry_policy.backoff_multiplier ** (self.attempt_count - 1)
        )
        
        # Cap at maximum delay
        return min(delay, self.retry_policy.max_delay_seconds)
    
    def record_attempt(self) -> None:
        """Record that an attempt was made."""
        self.attempt_count += 1
        self.last_attempt_time = datetime.now()
    
    def reset(self) -> None:
        """Reset the retry manager for a new recovery sequence."""
        self.attempt_count = 0
        self.last_attempt_time = None
    
    def get_attempt_info(self) -> Dict[str, Any]:
        """Get information about retry attempts.
        
        Returns:
            Dict containing attempt count, last attempt time, and next delay.
        """
        return {
            'attempt_count': self.attempt_count,
            'max_attempts': self.retry_policy.max_attempts,
            'last_attempt_time': self.last_attempt_time.isoformat() if self.last_attempt_time else None,
            'next_delay_seconds': self.get_next_delay() if self.should_retry() else None
        }


class RecoveryEngine:
    """Main recovery engine that orchestrates recovery attempts."""
    
    def __init__(self, default_retry_policy: Optional[RetryPolicy] = None):
        """Initialize the recovery engine.
        
        Args:
            default_retry_policy: Default retry policy for recovery attempts.
        """
        self.default_retry_policy = default_retry_policy or RetryPolicy()
        self.recovery_actions: Dict[str, RecoveryAction] = {}
        self.recovery_plugins: Dict[str, RecoveryPlugin] = {}
        self.recovery_history: Dict[str, List[RecoveryResult]] = {}
        self.active_recoveries: Dict[str, RetryManager] = {}
        self.escalation_callbacks: List[Callable[[str, List[RecoveryResult]], None]] = []
    
    def register_recovery_action(self, action_type: str, action: RecoveryAction) -> None:
        """Register a recovery action.
        
        Args:
            action_type: The type of recovery action.
            action: The recovery action instance.
            
        Raises:
            ValidationError: If the action configuration is invalid.
        """
        if not action.validate_config():
            raise ValidationError(f"Invalid configuration for recovery action: {action_type}")
        
        self.recovery_actions[action_type] = action
        logger.info(f"Registered recovery action: {action_type}")
    
    def register_recovery_plugin(self, plugin: RecoveryPlugin) -> None:
        """Register a recovery plugin.
        
        Args:
            plugin: The recovery plugin instance.
        """
        self.recovery_plugins[plugin.name] = plugin
        logger.info(f"Registered recovery plugin: {plugin.name}")
    
    def register_escalation_callback(self, callback: Callable[[str, List[RecoveryResult]], None]) -> None:
        """Register a callback for escalation when recovery fails.
        
        Args:
            callback: Function to call when recovery fails after all retries.
                     Takes node_id and recovery history as parameters.
        """
        self.escalation_callbacks.append(callback)
    
    def execute_recovery(self, node: NodeConfig, failure_type: str = "unknown") -> RecoveryResult:
        """Execute recovery for a failed node.
        
        Args:
            node: The node configuration to recover.
            failure_type: The type of failure detected.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
            
        Raises:
            RecoveryError: If no suitable recovery action is found.
        """
        logger.info(f"Starting recovery for node {node.node_id}, failure type: {failure_type}")
        
        # Get or create retry manager for this node
        retry_manager = self.active_recoveries.get(node.node_id)
        if retry_manager is None:
            retry_policy = node.retry_policy or self.default_retry_policy
            retry_manager = RetryManager(retry_policy)
            self.active_recoveries[node.node_id] = retry_manager
        
        # Check if we should retry
        if not retry_manager.should_retry():
            logger.warning(f"Maximum retry attempts reached for node {node.node_id}")
            self._handle_escalation(node.node_id)
            raise RecoveryError(f"Maximum retry attempts reached for node {node.node_id}")
        
        # Wait for retry delay if needed
        delay = retry_manager.get_next_delay()
        if delay > 0:
            logger.info(f"Waiting {delay} seconds before retry attempt for node {node.node_id}")
            time.sleep(delay)
        
        # Record the attempt
        retry_manager.record_attempt()
        
        # Find suitable recovery action
        recovery_action = self._find_recovery_action(node, failure_type)
        if recovery_action is None:
            error_msg = f"No suitable recovery action found for node {node.node_id}, failure type: {failure_type}"
            logger.error(error_msg)
            raise RecoveryError(error_msg)
        
        # Execute the recovery action
        try:
            result = recovery_action.execute(node)
            
            # Record the result
            self._record_recovery_result(node.node_id, result)
            
            # If successful, reset retry manager
            if result.success:
                logger.info(f"Recovery successful for node {node.node_id}")
                self.active_recoveries.pop(node.node_id, None)
            else:
                logger.warning(f"Recovery attempt failed for node {node.node_id}: {result.stderr}")
            
            return result
            
        except Exception as e:
            # Create failure result
            result = RecoveryResult(
                node_id=node.node_id,
                action_type=recovery_action.action_type,
                command_executed="N/A",
                exit_code=-1,
                stdout="",
                stderr=str(e),
                execution_time=datetime.now(),
                success=False
            )
            
            self._record_recovery_result(node.node_id, result)
            logger.error(f"Recovery action failed for node {node.node_id}: {e}")
            
            return result
    
    def _find_recovery_action(self, node: NodeConfig, failure_type: str) -> Optional[RecoveryAction]:
        """Find a suitable recovery action for the node and failure type.
        
        Args:
            node: The node configuration.
            failure_type: The type of failure.
            
        Returns:
            RecoveryAction or None if no suitable action is found.
        """
        # First, try to find action from node's configured recovery actions
        for action_type in node.recovery_actions:
            action = self.recovery_actions.get(action_type)
            if action and action.supports_node_type(node.node_type):
                return action
        
        # Then, try recovery plugins
        for plugin in self.recovery_plugins.values():
            if plugin.supports_recovery_type(failure_type):
                # Create a wrapper action for the plugin
                return PluginRecoveryAction(plugin, failure_type)
        
        # Finally, try any available recovery action that supports the node type
        for action in self.recovery_actions.values():
            if action.supports_node_type(node.node_type):
                return action
        
        return None
    
    def _record_recovery_result(self, node_id: str, result: RecoveryResult) -> None:
        """Record a recovery result in the history.
        
        Args:
            node_id: The node ID.
            result: The recovery result.
        """
        if node_id not in self.recovery_history:
            self.recovery_history[node_id] = []
        
        self.recovery_history[node_id].append(result)
        
        # Keep only the last 100 results per node to prevent memory issues
        if len(self.recovery_history[node_id]) > 100:
            self.recovery_history[node_id] = self.recovery_history[node_id][-100:]
    
    def _handle_escalation(self, node_id: str) -> None:
        """Handle escalation when recovery fails after all retries.
        
        Args:
            node_id: The node ID that failed recovery.
        """
        history = self.recovery_history.get(node_id, [])
        
        logger.error(f"Escalating recovery failure for node {node_id}")
        
        for callback in self.escalation_callbacks:
            try:
                callback(node_id, history)
            except Exception as e:
                logger.error(f"Error in escalation callback: {e}")
        
        # Clean up active recovery
        self.active_recoveries.pop(node_id, None)
    
    def get_recovery_history(self, node_id: str) -> List[RecoveryResult]:
        """Get recovery history for a node.
        
        Args:
            node_id: The node ID.
            
        Returns:
            List of recovery results for the node.
        """
        return self.recovery_history.get(node_id, []).copy()
    
    def get_active_recoveries(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active recovery attempts.
        
        Returns:
            Dict mapping node IDs to retry attempt information.
        """
        return {
            node_id: retry_manager.get_attempt_info()
            for node_id, retry_manager in self.active_recoveries.items()
        }
    
    def cancel_recovery(self, node_id: str) -> bool:
        """Cancel active recovery for a node.
        
        Args:
            node_id: The node ID.
            
        Returns:
            bool: True if recovery was cancelled, False if no active recovery.
        """
        if node_id in self.active_recoveries:
            self.active_recoveries.pop(node_id)
            logger.info(f"Cancelled recovery for node {node_id}")
            return True
        return False
    
    def reset_recovery_history(self, node_id: Optional[str] = None) -> None:
        """Reset recovery history.
        
        Args:
            node_id: Optional node ID to reset history for. If None, resets all history.
        """
        if node_id:
            self.recovery_history.pop(node_id, None)
            logger.info(f"Reset recovery history for node {node_id}")
        else:
            self.recovery_history.clear()
            logger.info("Reset all recovery history")


class PluginRecoveryAction(RecoveryAction):
    """Wrapper to use RecoveryPlugin as RecoveryAction."""
    
    def __init__(self, plugin: RecoveryPlugin, failure_type: str):
        """Initialize the plugin recovery action.
        
        Args:
            plugin: The recovery plugin.
            failure_type: The type of failure.
        """
        super().__init__(f"plugin_{plugin.name}", plugin.config)
        self.plugin = plugin
        self.failure_type = failure_type
    
    def execute(self, node: NodeConfig) -> RecoveryResult:
        """Execute the plugin recovery action.
        
        Args:
            node: The node configuration to recover.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
        """
        return self.plugin.execute_recovery(node, self.failure_type)
    
    def validate_config(self) -> bool:
        """Validate the plugin configuration.
        
        Returns:
            bool: True if configuration is valid.
        """
        return self.plugin.validate_config()
    
    def supports_node_type(self, node_type: str) -> bool:
        """Check if this action supports the given node type.
        
        Args:
            node_type: The type of node.
            
        Returns:
            bool: True if the action supports this node type.
        """
        # For plugin actions, we assume they handle their own node type checking
        return True