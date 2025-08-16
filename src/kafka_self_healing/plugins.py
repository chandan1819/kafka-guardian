"""
Plugin system for the Kafka Self-Healing system.

This module provides the foundation for extensible monitoring, recovery, and notification
capabilities through a plugin-based architecture.
"""

import abc
import importlib
import importlib.util
import inspect
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from .exceptions import PluginError, PluginLoadError, PluginValidationError
from .models import NodeConfig, NodeStatus, RecoveryResult


logger = logging.getLogger(__name__)


class PluginBase(abc.ABC):
    """Base class for all plugins."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the plugin with optional configuration."""
        self.config = config or {}
        self.name = self.__class__.__name__
        self.version = getattr(self.__class__, '__version__', '1.0.0')
        self.description = getattr(self.__class__, '__description__', '')
    
    @abc.abstractmethod
    def validate_config(self) -> bool:
        """Validate the plugin configuration.
        
        Returns:
            bool: True if configuration is valid, False otherwise.
            
        Raises:
            PluginValidationError: If configuration validation fails.
        """
        pass
    
    @abc.abstractmethod
    def initialize(self) -> bool:
        """Initialize the plugin.
        
        Returns:
            bool: True if initialization successful, False otherwise.
            
        Raises:
            PluginError: If initialization fails.
        """
        pass
    
    @abc.abstractmethod
    def cleanup(self) -> None:
        """Clean up plugin resources."""
        pass
    
    def get_info(self) -> Dict[str, str]:
        """Get plugin information."""
        return {
            'name': self.name,
            'version': self.version,
            'description': self.description
        }


class MonitoringPlugin(PluginBase):
    """Base class for monitoring plugins."""
    
    @abc.abstractmethod
    def check_health(self, node: NodeConfig) -> NodeStatus:
        """Check the health of a node.
        
        Args:
            node: The node configuration to check.
            
        Returns:
            NodeStatus: The health status of the node.
            
        Raises:
            PluginError: If health check fails.
        """
        pass
    
    @abc.abstractmethod
    def supports_node_type(self, node_type: str) -> bool:
        """Check if this plugin supports the given node type.
        
        Args:
            node_type: The type of node ('kafka_broker' or 'zookeeper').
            
        Returns:
            bool: True if the plugin supports this node type.
        """
        pass


class RecoveryPlugin(PluginBase):
    """Base class for recovery plugins."""
    
    @abc.abstractmethod
    def execute_recovery(self, node: NodeConfig, failure_type: str) -> RecoveryResult:
        """Execute recovery action for a failed node.
        
        Args:
            node: The node configuration to recover.
            failure_type: The type of failure detected.
            
        Returns:
            RecoveryResult: The result of the recovery attempt.
            
        Raises:
            PluginError: If recovery execution fails.
        """
        pass
    
    @abc.abstractmethod
    def supports_recovery_type(self, recovery_type: str) -> bool:
        """Check if this plugin supports the given recovery type.
        
        Args:
            recovery_type: The type of recovery action.
            
        Returns:
            bool: True if the plugin supports this recovery type.
        """
        pass


class NotificationPlugin(PluginBase):
    """Base class for notification plugins."""
    
    @abc.abstractmethod
    def send_notification(self, message: str, subject: str, recipients: List[str]) -> bool:
        """Send a notification.
        
        Args:
            message: The notification message content.
            subject: The notification subject.
            recipients: List of notification recipients.
            
        Returns:
            bool: True if notification was sent successfully.
            
        Raises:
            PluginError: If notification sending fails.
        """
        pass
    
    @abc.abstractmethod
    def supports_notification_type(self, notification_type: str) -> bool:
        """Check if this plugin supports the given notification type.
        
        Args:
            notification_type: The type of notification.
            
        Returns:
            bool: True if the plugin supports this notification type.
        """
        pass


class PluginManager:
    """Manager for plugin discovery, loading, and lifecycle management."""
    
    def __init__(self, plugin_dirs: Optional[List[str]] = None):
        """Initialize the plugin manager.
        
        Args:
            plugin_dirs: List of directories to search for plugins.
        """
        self.plugin_dirs = plugin_dirs or []
        self.monitoring_plugins: Dict[str, MonitoringPlugin] = {}
        self.recovery_plugins: Dict[str, RecoveryPlugin] = {}
        self.notification_plugins: Dict[str, NotificationPlugin] = {}
        self.loaded_modules: Dict[str, Any] = {}
        self.plugin_errors: Dict[str, str] = {}
    
    def add_plugin_directory(self, plugin_dir: str) -> None:
        """Add a directory to search for plugins.
        
        Args:
            plugin_dir: Path to the plugin directory.
        """
        if plugin_dir not in self.plugin_dirs:
            self.plugin_dirs.append(plugin_dir)
    
    def load_plugins(self) -> None:
        """Load all plugins from configured directories."""
        logger.info(f"Loading plugins from directories: {self.plugin_dirs}")
        
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                logger.warning(f"Plugin directory does not exist: {plugin_dir}")
                continue
            
            self._load_plugins_from_directory(plugin_dir)
        
        logger.info(f"Loaded {len(self.monitoring_plugins)} monitoring plugins, "
                   f"{len(self.recovery_plugins)} recovery plugins, "
                   f"{len(self.notification_plugins)} notification plugins")
    
    def _load_plugins_from_directory(self, plugin_dir: str) -> None:
        """Load plugins from a specific directory.
        
        Args:
            plugin_dir: Path to the plugin directory.
        """
        plugin_path = Path(plugin_dir)
        
        for file_path in plugin_path.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            
            try:
                self._load_plugin_module(str(file_path))
            except Exception as e:
                error_msg = f"Failed to load plugin from {file_path}: {e}"
                logger.error(error_msg)
                self.plugin_errors[str(file_path)] = error_msg
    
    def _load_plugin_module(self, file_path: str) -> None:
        """Load a plugin module from a file.
        
        Args:
            file_path: Path to the plugin file.
            
        Raises:
            PluginLoadError: If the plugin module cannot be loaded.
        """
        module_name = Path(file_path).stem
        
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                raise PluginLoadError(f"Cannot create module spec for {file_path}")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            self.loaded_modules[module_name] = module
            self._discover_plugin_classes(module, file_path)
            
        except Exception as e:
            raise PluginLoadError(f"Failed to load plugin module {file_path}: {e}")
    
    def _discover_plugin_classes(self, module: Any, file_path: str) -> None:
        """Discover and instantiate plugin classes from a module.
        
        Args:
            module: The loaded plugin module.
            file_path: Path to the plugin file.
        """
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            
            try:
                if issubclass(obj, MonitoringPlugin) and obj != MonitoringPlugin:
                    self._register_monitoring_plugin(obj, file_path)
                elif issubclass(obj, RecoveryPlugin) and obj != RecoveryPlugin:
                    self._register_recovery_plugin(obj, file_path)
                elif issubclass(obj, NotificationPlugin) and obj != NotificationPlugin:
                    self._register_notification_plugin(obj, file_path)
            except Exception as e:
                error_msg = f"Failed to register plugin class {name} from {file_path}: {e}"
                logger.error(error_msg)
                self.plugin_errors[f"{file_path}:{name}"] = error_msg
    
    def _register_monitoring_plugin(self, plugin_class: Type[MonitoringPlugin], file_path: str) -> None:
        """Register a monitoring plugin.
        
        Args:
            plugin_class: The monitoring plugin class.
            file_path: Path to the plugin file.
        """
        try:
            plugin_instance = plugin_class()
            
            if not self._validate_plugin(plugin_instance):
                return
            
            if not plugin_instance.initialize():
                logger.error(f"Failed to initialize monitoring plugin {plugin_class.__name__}")
                return
            
            self.monitoring_plugins[plugin_class.__name__] = plugin_instance
            logger.info(f"Registered monitoring plugin: {plugin_class.__name__}")
            
        except Exception as e:
            error_msg = f"Failed to register monitoring plugin {plugin_class.__name__}: {e}"
            logger.error(error_msg)
            self.plugin_errors[f"{file_path}:{plugin_class.__name__}"] = error_msg
    
    def _register_recovery_plugin(self, plugin_class: Type[RecoveryPlugin], file_path: str) -> None:
        """Register a recovery plugin.
        
        Args:
            plugin_class: The recovery plugin class.
            file_path: Path to the plugin file.
        """
        try:
            plugin_instance = plugin_class()
            
            if not self._validate_plugin(plugin_instance):
                return
            
            if not plugin_instance.initialize():
                logger.error(f"Failed to initialize recovery plugin {plugin_class.__name__}")
                return
            
            self.recovery_plugins[plugin_class.__name__] = plugin_instance
            logger.info(f"Registered recovery plugin: {plugin_class.__name__}")
            
        except Exception as e:
            error_msg = f"Failed to register recovery plugin {plugin_class.__name__}: {e}"
            logger.error(error_msg)
            self.plugin_errors[f"{file_path}:{plugin_class.__name__}"] = error_msg
    
    def _register_notification_plugin(self, plugin_class: Type[NotificationPlugin], file_path: str) -> None:
        """Register a notification plugin.
        
        Args:
            plugin_class: The notification plugin class.
            file_path: Path to the plugin file.
        """
        try:
            plugin_instance = plugin_class()
            
            if not self._validate_plugin(plugin_instance):
                return
            
            if not plugin_instance.initialize():
                logger.error(f"Failed to initialize notification plugin {plugin_class.__name__}")
                return
            
            self.notification_plugins[plugin_class.__name__] = plugin_instance
            logger.info(f"Registered notification plugin: {plugin_class.__name__}")
            
        except Exception as e:
            error_msg = f"Failed to register notification plugin {plugin_class.__name__}: {e}"
            logger.error(error_msg)
            self.plugin_errors[f"{file_path}:{plugin_class.__name__}"] = error_msg
    
    def _validate_plugin(self, plugin: PluginBase) -> bool:
        """Validate a plugin instance.
        
        Args:
            plugin: The plugin instance to validate.
            
        Returns:
            bool: True if the plugin is valid.
        """
        try:
            return plugin.validate_config()
        except Exception as e:
            logger.error(f"Plugin validation failed for {plugin.name}: {e}")
            return False
    
    def get_monitoring_plugins(self) -> List[MonitoringPlugin]:
        """Get all loaded monitoring plugins.
        
        Returns:
            List of monitoring plugin instances.
        """
        return list(self.monitoring_plugins.values())
    
    def get_recovery_plugins(self) -> List[RecoveryPlugin]:
        """Get all loaded recovery plugins.
        
        Returns:
            List of recovery plugin instances.
        """
        return list(self.recovery_plugins.values())
    
    def get_notification_plugins(self) -> List[NotificationPlugin]:
        """Get all loaded notification plugins.
        
        Returns:
            List of notification plugin instances.
        """
        return list(self.notification_plugins.values())
    
    def get_monitoring_plugin(self, name: str) -> Optional[MonitoringPlugin]:
        """Get a specific monitoring plugin by name.
        
        Args:
            name: The plugin name.
            
        Returns:
            The monitoring plugin instance or None if not found.
        """
        return self.monitoring_plugins.get(name)
    
    def get_recovery_plugin(self, name: str) -> Optional[RecoveryPlugin]:
        """Get a specific recovery plugin by name.
        
        Args:
            name: The plugin name.
            
        Returns:
            The recovery plugin instance or None if not found.
        """
        return self.recovery_plugins.get(name)
    
    def get_notification_plugin(self, name: str) -> Optional[NotificationPlugin]:
        """Get a specific notification plugin by name.
        
        Args:
            name: The plugin name.
            
        Returns:
            The notification plugin instance or None if not found.
        """
        return self.notification_plugins.get(name)
    
    def get_plugin_errors(self) -> Dict[str, str]:
        """Get all plugin loading errors.
        
        Returns:
            Dictionary mapping plugin paths/names to error messages.
        """
        return self.plugin_errors.copy()
    
    def cleanup_plugins(self) -> None:
        """Clean up all loaded plugins."""
        logger.info("Cleaning up plugins")
        
        for plugin in self.monitoring_plugins.values():
            try:
                plugin.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up monitoring plugin {plugin.name}: {e}")
        
        for plugin in self.recovery_plugins.values():
            try:
                plugin.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up recovery plugin {plugin.name}: {e}")
        
        for plugin in self.notification_plugins.values():
            try:
                plugin.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up notification plugin {plugin.name}: {e}")
        
        self.monitoring_plugins.clear()
        self.recovery_plugins.clear()
        self.notification_plugins.clear()
        self.loaded_modules.clear()
        self.plugin_errors.clear()