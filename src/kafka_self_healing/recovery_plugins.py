"""
Recovery plugins for the Kafka Self-Healing system.

This module contains concrete implementations of recovery plugins for various
recovery scenarios including service restart, script execution, and Ansible playbooks.
"""

import logging
import os
import subprocess
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .exceptions import RecoveryError, ValidationError
from .models import NodeConfig, RecoveryResult
from .plugins import RecoveryPlugin


logger = logging.getLogger(__name__)


class ServiceRestartPlugin(RecoveryPlugin):
    """Recovery plugin for systemctl-based service management."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the service restart plugin.
        
        Args:
            config: Plugin configuration containing service mappings and options.
        """
        super().__init__(config)
        self.name = "ServiceRestartPlugin"
        self.version = "1.0.0"
        self.description = "Restart services using systemctl"
        
        # Default service mappings
        self.service_mappings = self.config.get('service_mappings', {
            'kafka_broker': 'kafka',
            'zookeeper': 'zookeeper'
        })
        
        # Command options
        self.use_sudo = self.config.get('use_sudo', True)
        self.timeout_seconds = self.config.get('timeout_seconds', 60)
        self.systemctl_path = self.config.get('systemctl_path', '/usr/bin/systemctl')
    
    def validate_config(self) -> bool:
        """Validate the plugin configuration.
        
        Returns:
            bool: True if configuration is valid.
            
        Raises:
            ValidationError: If configuration is invalid.
        """
        if not isinstance(self.service_mappings, dict):
            raise ValidationError("service_mappings must be a dictionary")
        
        if not isinstance(self.use_sudo, bool):
            raise ValidationError("use_sudo must be a boolean")
        
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValidationError("timeout_seconds must be a positive integer")
        
        if not isinstance(self.systemctl_path, str) or not self.systemctl_path:
            raise ValidationError("systemctl_path must be a non-empty string")
        
        return True
    
    def initialize(self) -> bool:
        """Initialize the plugin.
        
        Returns:
            bool: True if initialization successful.
        """
        try:
            # Check if systemctl is available
            result = subprocess.run(
                [self.systemctl_path, '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.error(f"systemctl not available at {self.systemctl_path}")
                return False
            
            logger.info(f"ServiceRestartPlugin initialized with systemctl version check successful")
            return True
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
            logger.error(f"Failed to initialize ServiceRestartPlugin: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up plugin resources."""
        # No cleanup needed for this plugin
        pass
    
    def execute_recovery(self, node: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute service restart recovery for a failed node.
        
        Args:
            node: The node configuration to recover.
            failure_type: The type of failure detected.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
            
        Raises:
            RecoveryError: If the recovery execution fails.
        """
        service_name = self._get_service_name(node.node_type)
        if not service_name:
            raise RecoveryError(f"No service mapping found for node type: {node.node_type}")
        
        logger.info(f"Attempting to restart service '{service_name}' for node {node.node_id}")
        
        # Build the restart command
        command = self._build_restart_command(service_name)
        
        try:
            start_time = datetime.now()
            
            # Execute the restart command
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False
            )
            
            execution_time = datetime.now()
            success = result.returncode == 0
            
            if success:
                logger.info(f"Successfully restarted service '{service_name}' for node {node.node_id}")
            else:
                logger.warning(f"Service restart failed for node {node.node_id}: {result.stderr}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_restart",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                success=success
            )
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"Service restart timed out after {self.timeout_seconds} seconds"
            logger.error(f"Service restart timeout for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_restart",
                command_executed=' '.join(command),
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
            
        except subprocess.SubprocessError as e:
            error_msg = f"Service restart subprocess error: {e}"
            logger.error(f"Service restart subprocess error for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_restart",
                command_executed=' '.join(command),
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
    
    def supports_recovery_type(self, recovery_type: str) -> bool:
        """Check if this plugin supports the given recovery type.
        
        Args:
            recovery_type: The type of recovery action.
            
        Returns:
            bool: True if the plugin supports this recovery type.
        """
        supported_types = [
            "service_restart",
            "service_down",
            "process_failure",
            "connection_failure",
            "health_check_failure"
        ]
        return recovery_type in supported_types
    
    def _get_service_name(self, node_type: str) -> Optional[str]:
        """Get the service name for a node type.
        
        Args:
            node_type: The type of node.
            
        Returns:
            Service name or None if not found.
        """
        return self.service_mappings.get(node_type)
    
    def _build_restart_command(self, service_name: str) -> List[str]:
        """Build the systemctl restart command.
        
        Args:
            service_name: The name of the service to restart.
            
        Returns:
            List of command components.
        """
        command = []
        
        if self.use_sudo:
            command.append('sudo')
        
        command.extend([self.systemctl_path, 'restart', service_name])
        
        return command
    
    def get_service_status(self, node: NodeConfig) -> Optional[RecoveryResult]:
        """Get the current status of the service for a node.
        
        Args:
            node: The node configuration.
            
        Returns:
            RecoveryResult with service status information, or None if service not found.
        """
        service_name = self._get_service_name(node.node_type)
        if not service_name:
            return None
        
        command = []
        if self.use_sudo:
            command.append('sudo')
        command.extend([self.systemctl_path, 'status', service_name])
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_status",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=datetime.now(),
                success=result.returncode == 0
            )
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.error(f"Failed to get service status for {service_name}: {e}")
            return None
    
    def stop_service(self, node: NodeConfig) -> RecoveryResult:
        """Stop the service for a node.
        
        Args:
            node: The node configuration.
            
        Returns:
            RecoveryResult: The result of the stop operation.
            
        Raises:
            RecoveryError: If the service cannot be stopped.
        """
        service_name = self._get_service_name(node.node_type)
        if not service_name:
            raise RecoveryError(f"No service mapping found for node type: {node.node_type}")
        
        command = []
        if self.use_sudo:
            command.append('sudo')
        command.extend([self.systemctl_path, 'stop', service_name])
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_stop",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=datetime.now(),
                success=result.returncode == 0
            )
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            error_msg = f"Service stop error: {e}"
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_stop",
                command_executed=' '.join(command),
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
    
    def start_service(self, node: NodeConfig) -> RecoveryResult:
        """Start the service for a node.
        
        Args:
            node: The node configuration.
            
        Returns:
            RecoveryResult: The result of the start operation.
            
        Raises:
            RecoveryError: If the service cannot be started.
        """
        service_name = self._get_service_name(node.node_type)
        if not service_name:
            raise RecoveryError(f"No service mapping found for node type: {node.node_type}")
        
        command = []
        if self.use_sudo:
            command.append('sudo')
        command.extend([self.systemctl_path, 'start', service_name])
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds
            )
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_start",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=datetime.now(),
                success=result.returncode == 0
            )
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            error_msg = f"Service start error: {e}"
            return RecoveryResult(
                node_id=node.node_id,
                action_type="service_start",
                command_executed=' '.join(command),
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )


class ScriptRecoveryPlugin(RecoveryPlugin):
    """Recovery plugin for executing shell scripts and commands."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the script recovery plugin.
        
        Args:
            config: Plugin configuration containing script paths and parameters.
        """
        super().__init__(config)
        self.name = "ScriptRecoveryPlugin"
        self.version = "1.0.0"
        self.description = "Execute shell scripts and commands for recovery"
        
        # Script configuration
        self.script_directory = self.config.get('script_directory', '/opt/kafka-recovery/scripts')
        self.scripts = self.config.get('scripts', {})
        self.default_shell = self.config.get('default_shell', '/bin/bash')
        self.timeout_seconds = self.config.get('timeout_seconds', 300)
        self.use_sudo = self.config.get('use_sudo', False)
        self.environment_variables = self.config.get('environment_variables', {})
        self.working_directory = self.config.get('working_directory', None)
    
    def validate_config(self) -> bool:
        """Validate the plugin configuration.
        
        Returns:
            bool: True if configuration is valid.
            
        Raises:
            ValidationError: If configuration is invalid.
        """
        if not isinstance(self.script_directory, str):
            raise ValidationError("script_directory must be a string")
        
        if not isinstance(self.scripts, dict):
            raise ValidationError("scripts must be a dictionary")
        
        if not isinstance(self.default_shell, str) or not self.default_shell:
            raise ValidationError("default_shell must be a non-empty string")
        
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValidationError("timeout_seconds must be a positive integer")
        
        if not isinstance(self.use_sudo, bool):
            raise ValidationError("use_sudo must be a boolean")
        
        if not isinstance(self.environment_variables, dict):
            raise ValidationError("environment_variables must be a dictionary")
        
        if self.working_directory is not None and not isinstance(self.working_directory, str):
            raise ValidationError("working_directory must be a string or None")
        
        return True
    
    def initialize(self) -> bool:
        """Initialize the plugin.
        
        Returns:
            bool: True if initialization successful.
        """
        try:
            # Check if default shell is available
            result = subprocess.run(
                [self.default_shell, '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.warning(f"Default shell {self.default_shell} version check failed, but continuing")
            
            # Create script directory if it doesn't exist
            if self.script_directory:
                Path(self.script_directory).mkdir(parents=True, exist_ok=True)
            
            logger.info(f"ScriptRecoveryPlugin initialized with script directory: {self.script_directory}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize ScriptRecoveryPlugin: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up plugin resources."""
        # No cleanup needed for this plugin
        pass
    
    def execute_recovery(self, node: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute script-based recovery for a failed node.
        
        Args:
            node: The node configuration to recover.
            failure_type: The type of failure detected.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
            
        Raises:
            RecoveryError: If the recovery execution fails.
        """
        script_info = self._get_script_for_recovery(node, failure_type)
        if not script_info:
            raise RecoveryError(f"No script found for node type {node.node_type} and failure type {failure_type}")
        
        script_path, script_args = script_info
        logger.info(f"Executing recovery script '{script_path}' for node {node.node_id}")
        
        try:
            # Build the command
            command = self._build_script_command(script_path, script_args, node)
            
            # Prepare environment
            env = self._prepare_environment(node)
            
            # Determine working directory
            cwd = self.working_directory or os.getcwd()
            
            start_time = datetime.now()
            
            # Execute the script
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
                cwd=cwd,
                shell=False
            )
            
            execution_time = datetime.now()
            success = result.returncode == 0
            
            if success:
                logger.info(f"Successfully executed recovery script for node {node.node_id}")
            else:
                logger.warning(f"Recovery script failed for node {node.node_id}: {result.stderr}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="script_recovery",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                success=success
            )
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"Script execution timed out after {self.timeout_seconds} seconds"
            logger.error(f"Script execution timeout for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="script_recovery",
                command_executed=' '.join(command) if 'command' in locals() else "N/A",
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
            
        except subprocess.SubprocessError as e:
            error_msg = f"Script execution subprocess error: {e}"
            logger.error(f"Script execution subprocess error for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="script_recovery",
                command_executed=' '.join(command) if 'command' in locals() else "N/A",
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
        
        except Exception as e:
            error_msg = f"Unexpected error during script execution: {e}"
            logger.error(f"Unexpected error during script execution for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="script_recovery",
                command_executed="N/A",
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
    
    def supports_recovery_type(self, recovery_type: str) -> bool:
        """Check if this plugin supports the given recovery type.
        
        Args:
            recovery_type: The type of recovery action.
            
        Returns:
            bool: True if the plugin supports this recovery type.
        """
        # Check if we have a script configured for this recovery type
        return recovery_type in self.scripts or "default" in self.scripts
    
    def _get_script_for_recovery(self, node: NodeConfig, failure_type: str) -> Optional[tuple]:
        """Get the script path and arguments for a recovery scenario.
        
        Args:
            node: The node configuration.
            failure_type: The type of failure.
            
        Returns:
            Tuple of (script_path, script_args) or None if not found.
        """
        # First, try to find a script specific to the failure type
        if failure_type in self.scripts:
            script_config = self.scripts[failure_type]
        elif "default" in self.scripts:
            script_config = self.scripts["default"]
        else:
            return None
        
        # Handle different script configuration formats
        if isinstance(script_config, str):
            # Simple string path
            script_path = script_config
            script_args = []
        elif isinstance(script_config, dict):
            # Dictionary with path and args
            script_path = script_config.get('path', '')
            script_args = script_config.get('args', [])
        else:
            return None
        
        # Resolve script path
        if not os.path.isabs(script_path):
            script_path = os.path.join(self.script_directory, script_path)
        
        # Check if script exists and is executable
        if not os.path.exists(script_path):
            logger.error(f"Script not found: {script_path}")
            return None
        
        if not os.access(script_path, os.X_OK):
            logger.error(f"Script not executable: {script_path}")
            return None
        
        return script_path, script_args
    
    def _build_script_command(self, script_path: str, script_args: List[str], node: NodeConfig) -> List[str]:
        """Build the script execution command.
        
        Args:
            script_path: Path to the script.
            script_args: Script arguments.
            node: The node configuration.
            
        Returns:
            List of command components.
        """
        command = []
        
        if self.use_sudo:
            command.append('sudo')
        
        # Add shell if script is not directly executable
        if script_path.endswith('.sh') or not os.access(script_path, os.X_OK):
            command.append(self.default_shell)
        
        command.append(script_path)
        
        # Add script arguments with parameter substitution
        for arg in script_args:
            substituted_arg = self._substitute_parameters(arg, node)
            command.append(substituted_arg)
        
        return command
    
    def _substitute_parameters(self, text: str, node: NodeConfig) -> str:
        """Substitute node-specific parameters in text.
        
        Args:
            text: Text with parameter placeholders.
            node: The node configuration.
            
        Returns:
            Text with parameters substituted.
        """
        substitutions = {
            '{node_id}': node.node_id,
            '{node_type}': node.node_type,
            '{host}': node.host,
            '{port}': str(node.port),
            '{jmx_port}': str(node.jmx_port) if node.jmx_port else '',
        }
        
        result = text
        for placeholder, value in substitutions.items():
            result = result.replace(placeholder, value)
        
        return result
    
    def _prepare_environment(self, node: NodeConfig) -> Dict[str, str]:
        """Prepare environment variables for script execution.
        
        Args:
            node: The node configuration.
            
        Returns:
            Dictionary of environment variables.
        """
        # Start with current environment
        env = os.environ.copy()
        
        # Add configured environment variables
        for key, value in self.environment_variables.items():
            env[key] = self._substitute_parameters(str(value), node)
        
        # Add node-specific environment variables
        env['KAFKA_NODE_ID'] = node.node_id
        env['KAFKA_NODE_TYPE'] = node.node_type
        env['KAFKA_HOST'] = node.host
        env['KAFKA_PORT'] = str(node.port)
        if node.jmx_port:
            env['KAFKA_JMX_PORT'] = str(node.jmx_port)
        
        return env
    
    def execute_script_by_name(self, script_name: str, node: NodeConfig, 
                              additional_args: Optional[List[str]] = None) -> RecoveryResult:
        """Execute a specific script by name.
        
        Args:
            script_name: Name of the script to execute.
            node: The node configuration.
            additional_args: Additional arguments to pass to the script.
            
        Returns:
            RecoveryResult: The result of the script execution.
            
        Raises:
            RecoveryError: If the script cannot be executed.
        """
        if script_name not in self.scripts:
            raise RecoveryError(f"Script '{script_name}' not found in configuration")
        
        script_info = self._get_script_for_recovery(node, script_name)
        if not script_info:
            raise RecoveryError(f"Failed to resolve script '{script_name}'")
        
        script_path, script_args = script_info
        
        # Add additional arguments if provided
        if additional_args:
            script_args.extend(additional_args)
        
        # Use the main execute_recovery method but with custom script info
        original_scripts = self.scripts
        try:
            # Temporarily set scripts to only contain our target script
            self.scripts = {script_name: {'path': script_path, 'args': script_args}}
            return self.execute_recovery(node, script_name)
        finally:
            # Restore original scripts configuration
            self.scripts = original_scripts
    
    def list_available_scripts(self) -> Dict[str, Dict[str, Any]]:
        """List all available scripts and their configurations.
        
        Returns:
            Dictionary mapping script names to their configurations.
        """
        result = {}
        
        for script_name, script_config in self.scripts.items():
            if isinstance(script_config, str):
                result[script_name] = {
                    'path': script_config,
                    'args': [],
                    'resolved_path': os.path.join(self.script_directory, script_config) 
                                   if not os.path.isabs(script_config) else script_config
                }
            elif isinstance(script_config, dict):
                script_path = script_config.get('path', '')
                resolved_path = os.path.join(self.script_directory, script_path) \
                               if not os.path.isabs(script_path) else script_path
                
                result[script_name] = {
                    'path': script_path,
                    'args': script_config.get('args', []),
                    'resolved_path': resolved_path,
                    'exists': os.path.exists(resolved_path),
                    'executable': os.access(resolved_path, os.X_OK) if os.path.exists(resolved_path) else False
                }
        
        return result


class AnsibleRecoveryPlugin(RecoveryPlugin):
    """Recovery plugin for executing Ansible playbooks."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the Ansible recovery plugin.
        
        Args:
            config: Plugin configuration containing playbook paths and parameters.
        """
        super().__init__(config)
        self.name = "AnsibleRecoveryPlugin"
        self.version = "1.0.0"
        self.description = "Execute Ansible playbooks for recovery"
        
        # Ansible configuration
        self.playbook_directory = self.config.get('playbook_directory', '/opt/kafka-recovery/playbooks')
        self.playbooks = self.config.get('playbooks', {})
        self.inventory_file = self.config.get('inventory_file', None)
        self.inventory_directory = self.config.get('inventory_directory', None)
        self.ansible_playbook_path = self.config.get('ansible_playbook_path', 'ansible-playbook')
        self.timeout_seconds = self.config.get('timeout_seconds', 600)
        self.extra_vars = self.config.get('extra_vars', {})
        self.ansible_config = self.config.get('ansible_config', None)
        self.vault_password_file = self.config.get('vault_password_file', None)
        self.become = self.config.get('become', False)
        self.become_user = self.config.get('become_user', 'root')
        self.verbosity = self.config.get('verbosity', 0)
    
    def validate_config(self) -> bool:
        """Validate the plugin configuration.
        
        Returns:
            bool: True if configuration is valid.
            
        Raises:
            ValidationError: If configuration is invalid.
        """
        if not isinstance(self.playbook_directory, str):
            raise ValidationError("playbook_directory must be a string")
        
        if not isinstance(self.playbooks, dict):
            raise ValidationError("playbooks must be a dictionary")
        
        if not isinstance(self.ansible_playbook_path, str) or not self.ansible_playbook_path:
            raise ValidationError("ansible_playbook_path must be a non-empty string")
        
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValidationError("timeout_seconds must be a positive integer")
        
        if not isinstance(self.extra_vars, dict):
            raise ValidationError("extra_vars must be a dictionary")
        
        if self.inventory_file is not None and not isinstance(self.inventory_file, str):
            raise ValidationError("inventory_file must be a string or None")
        
        if self.inventory_directory is not None and not isinstance(self.inventory_directory, str):
            raise ValidationError("inventory_directory must be a string or None")
        
        if self.ansible_config is not None and not isinstance(self.ansible_config, str):
            raise ValidationError("ansible_config must be a string or None")
        
        if self.vault_password_file is not None and not isinstance(self.vault_password_file, str):
            raise ValidationError("vault_password_file must be a string or None")
        
        if not isinstance(self.become, bool):
            raise ValidationError("become must be a boolean")
        
        if not isinstance(self.become_user, str):
            raise ValidationError("become_user must be a string")
        
        if not isinstance(self.verbosity, int) or self.verbosity < 0:
            raise ValidationError("verbosity must be a non-negative integer")
        
        return True
    
    def initialize(self) -> bool:
        """Initialize the plugin.
        
        Returns:
            bool: True if initialization successful.
        """
        try:
            # Check if ansible-playbook is available
            result = subprocess.run(
                [self.ansible_playbook_path, '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                logger.error(f"ansible-playbook not available at {self.ansible_playbook_path}")
                return False
            
            # Create playbook directory if it doesn't exist
            if self.playbook_directory:
                Path(self.playbook_directory).mkdir(parents=True, exist_ok=True)
            
            logger.info(f"AnsibleRecoveryPlugin initialized with ansible-playbook version check successful")
            return True
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
            logger.error(f"Failed to initialize AnsibleRecoveryPlugin: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up plugin resources."""
        # No cleanup needed for this plugin
        pass
    
    def execute_recovery(self, node: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute Ansible playbook recovery for a failed node.
        
        Args:
            node: The node configuration to recover.
            failure_type: The type of failure detected.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
            
        Raises:
            RecoveryError: If the recovery execution fails.
        """
        playbook_info = self._get_playbook_for_recovery(node, failure_type)
        if not playbook_info:
            raise RecoveryError(f"No playbook found for node type {node.node_type} and failure type {failure_type}")
        
        playbook_path, playbook_vars = playbook_info
        logger.info(f"Executing Ansible playbook '{playbook_path}' for node {node.node_id}")
        
        try:
            # Build the ansible-playbook command
            command = self._build_ansible_command(playbook_path, playbook_vars, node)
            
            # Prepare environment
            env = self._prepare_environment(node)
            
            start_time = datetime.now()
            
            # Execute the playbook
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
                shell=False
            )
            
            execution_time = datetime.now()
            success = result.returncode == 0
            
            if success:
                logger.info(f"Successfully executed Ansible playbook for node {node.node_id}")
            else:
                logger.warning(f"Ansible playbook failed for node {node.node_id}: {result.stderr}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="ansible_recovery",
                command_executed=' '.join(command),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                success=success
            )
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"Ansible playbook execution timed out after {self.timeout_seconds} seconds"
            logger.error(f"Ansible playbook timeout for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="ansible_recovery",
                command_executed=' '.join(command) if 'command' in locals() else "N/A",
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
            
        except subprocess.SubprocessError as e:
            error_msg = f"Ansible playbook subprocess error: {e}"
            logger.error(f"Ansible playbook subprocess error for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="ansible_recovery",
                command_executed=' '.join(command) if 'command' in locals() else "N/A",
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
        
        except Exception as e:
            error_msg = f"Unexpected error during Ansible playbook execution: {e}"
            logger.error(f"Unexpected error during Ansible playbook execution for node {node.node_id}: {error_msg}")
            
            return RecoveryResult(
                node_id=node.node_id,
                action_type="ansible_recovery",
                command_executed="N/A",
                exit_code=-1,
                stdout="",
                stderr=error_msg,
                execution_time=datetime.now(),
                success=False
            )
    
    def supports_recovery_type(self, recovery_type: str) -> bool:
        """Check if this plugin supports the given recovery type.
        
        Args:
            recovery_type: The type of recovery action.
            
        Returns:
            bool: True if the plugin supports this recovery type.
        """
        # Check if we have a playbook configured for this recovery type
        return recovery_type in self.playbooks or "default" in self.playbooks
    
    def _get_playbook_for_recovery(self, node: NodeConfig, failure_type: str) -> Optional[tuple]:
        """Get the playbook path and variables for a recovery scenario.
        
        Args:
            node: The node configuration.
            failure_type: The type of failure.
            
        Returns:
            Tuple of (playbook_path, playbook_vars) or None if not found.
        """
        # First, try to find a playbook specific to the failure type
        if failure_type in self.playbooks:
            playbook_config = self.playbooks[failure_type]
        elif "default" in self.playbooks:
            playbook_config = self.playbooks["default"]
        else:
            return None
        
        # Handle different playbook configuration formats
        if isinstance(playbook_config, str):
            # Simple string path
            playbook_path = playbook_config
            playbook_vars = {}
        elif isinstance(playbook_config, dict):
            # Dictionary with path and vars
            playbook_path = playbook_config.get('path', '')
            playbook_vars = playbook_config.get('vars', {})
        else:
            return None
        
        # Resolve playbook path
        if not os.path.isabs(playbook_path):
            playbook_path = os.path.join(self.playbook_directory, playbook_path)
        
        # Check if playbook exists
        if not os.path.exists(playbook_path):
            logger.error(f"Playbook not found: {playbook_path}")
            return None
        
        return playbook_path, playbook_vars
    
    def _build_ansible_command(self, playbook_path: str, playbook_vars: Dict[str, Any], node: NodeConfig) -> List[str]:
        """Build the ansible-playbook command.
        
        Args:
            playbook_path: Path to the playbook.
            playbook_vars: Playbook variables.
            node: The node configuration.
            
        Returns:
            List of command components.
        """
        command = [self.ansible_playbook_path]
        
        # Add inventory
        if self.inventory_file:
            command.extend(['-i', self.inventory_file])
        elif self.inventory_directory:
            command.extend(['-i', self.inventory_directory])
        else:
            # Create a temporary inventory with the node
            inventory_content = f"{node.host} ansible_host={node.host}"
            # For simplicity, we'll use the host directly
            command.extend(['-i', f"{node.host},"])
        
        # Add verbosity
        if self.verbosity > 0:
            command.append('-' + 'v' * min(self.verbosity, 4))
        
        # Add become options
        if self.become:
            command.append('--become')
            if self.become_user != 'root':
                command.extend(['--become-user', self.become_user])
        
        # Add vault password file
        if self.vault_password_file:
            command.extend(['--vault-password-file', self.vault_password_file])
        
        # Add extra variables
        all_vars = {}
        all_vars.update(self.extra_vars)
        all_vars.update(playbook_vars)
        
        # Add node-specific variables
        node_vars = self._get_node_variables(node)
        all_vars.update(node_vars)
        
        # Substitute parameters in variables
        for key, value in all_vars.items():
            if isinstance(value, str):
                all_vars[key] = self._substitute_parameters(value, node)
        
        # Add variables to command
        if all_vars:
            vars_json = self._dict_to_json_string(all_vars)
            command.extend(['--extra-vars', vars_json])
        
        # Add the playbook path
        command.append(playbook_path)
        
        return command
    
    def _get_node_variables(self, node: NodeConfig) -> Dict[str, Any]:
        """Get node-specific variables for Ansible.
        
        Args:
            node: The node configuration.
            
        Returns:
            Dictionary of node variables.
        """
        return {
            'kafka_node_id': node.node_id,
            'kafka_node_type': node.node_type,
            'kafka_host': node.host,
            'kafka_port': node.port,
            'kafka_jmx_port': node.jmx_port or '',
            'target_host': node.host
        }
    
    def _substitute_parameters(self, text: str, node: NodeConfig) -> str:
        """Substitute node-specific parameters in text.
        
        Args:
            text: Text with parameter placeholders.
            node: The node configuration.
            
        Returns:
            Text with parameters substituted.
        """
        substitutions = {
            '{node_id}': node.node_id,
            '{node_type}': node.node_type,
            '{host}': node.host,
            '{port}': str(node.port),
            '{jmx_port}': str(node.jmx_port) if node.jmx_port else '',
        }
        
        result = text
        for placeholder, value in substitutions.items():
            result = result.replace(placeholder, value)
        
        return result
    
    def _prepare_environment(self, node: NodeConfig) -> Dict[str, str]:
        """Prepare environment variables for Ansible execution.
        
        Args:
            node: The node configuration.
            
        Returns:
            Dictionary of environment variables.
        """
        # Start with current environment
        env = os.environ.copy()
        
        # Add Ansible configuration file if specified
        if self.ansible_config:
            env['ANSIBLE_CONFIG'] = self.ansible_config
        
        # Add node-specific environment variables
        env['KAFKA_NODE_ID'] = node.node_id
        env['KAFKA_NODE_TYPE'] = node.node_type
        env['KAFKA_HOST'] = node.host
        env['KAFKA_PORT'] = str(node.port)
        if node.jmx_port:
            env['KAFKA_JMX_PORT'] = str(node.jmx_port)
        
        return env
    
    def _dict_to_json_string(self, data: Dict[str, Any]) -> str:
        """Convert dictionary to JSON string for Ansible extra vars.
        
        Args:
            data: Dictionary to convert.
            
        Returns:
            JSON string representation.
        """
        import json
        return json.dumps(data)
    
    def execute_playbook_by_name(self, playbook_name: str, node: NodeConfig, 
                                 additional_vars: Optional[Dict[str, Any]] = None) -> RecoveryResult:
        """Execute a specific playbook by name.
        
        Args:
            playbook_name: Name of the playbook to execute.
            node: The node configuration.
            additional_vars: Additional variables to pass to the playbook.
            
        Returns:
            RecoveryResult: The result of the playbook execution.
            
        Raises:
            RecoveryError: If the playbook cannot be executed.
        """
        if playbook_name not in self.playbooks:
            raise RecoveryError(f"Playbook '{playbook_name}' not found in configuration")
        
        playbook_info = self._get_playbook_for_recovery(node, playbook_name)
        if not playbook_info:
            raise RecoveryError(f"Failed to resolve playbook '{playbook_name}'")
        
        playbook_path, playbook_vars = playbook_info
        
        # Add additional variables if provided
        if additional_vars:
            playbook_vars.update(additional_vars)
        
        # Use the main execute_recovery method but with custom playbook info
        original_playbooks = self.playbooks
        try:
            # Temporarily set playbooks to only contain our target playbook
            self.playbooks = {playbook_name: {'path': playbook_path, 'vars': playbook_vars}}
            return self.execute_recovery(node, playbook_name)
        finally:
            # Restore original playbooks configuration
            self.playbooks = original_playbooks
    
    def list_available_playbooks(self) -> Dict[str, Dict[str, Any]]:
        """List all available playbooks and their configurations.
        
        Returns:
            Dictionary mapping playbook names to their configurations.
        """
        result = {}
        
        for playbook_name, playbook_config in self.playbooks.items():
            if isinstance(playbook_config, str):
                result[playbook_name] = {
                    'path': playbook_config,
                    'vars': {},
                    'resolved_path': os.path.join(self.playbook_directory, playbook_config) 
                                   if not os.path.isabs(playbook_config) else playbook_config
                }
            elif isinstance(playbook_config, dict):
                playbook_path = playbook_config.get('path', '')
                resolved_path = os.path.join(self.playbook_directory, playbook_path) \
                               if not os.path.isabs(playbook_path) else playbook_path
                
                result[playbook_name] = {
                    'path': playbook_path,
                    'vars': playbook_config.get('vars', {}),
                    'resolved_path': resolved_path,
                    'exists': os.path.exists(resolved_path)
                }
        
        return result