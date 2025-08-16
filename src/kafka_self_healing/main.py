"""
Main application entry point for the Kafka Self-Healing system.

This module provides the main application class with startup and shutdown procedures,
signal handling for graceful shutdown, and system initialization.
"""

import signal
import sys
import threading
import time
import psutil
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from .config import ConfigurationManager
from .logging import LoggingService, LogConfig
from .monitoring import MonitoringService
from .recovery import RecoveryEngine
from .notification import NotificationService
from .plugins import PluginManager
from .integration import MonitoringRecoveryIntegrator
from .exceptions import ValidationError, SystemError


class KafkaSelfHealingApp:
    """
    Main application class that orchestrates all system components.
    
    Handles startup/shutdown procedures, signal handling, and component coordination.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the application.
        
        Args:
            config_path: Path to configuration file (optional)
        """
        self.config_path = config_path
        self.running = False
        self.shutdown_event = threading.Event()
        
        # Core components
        self.config_manager: Optional[ConfigurationManager] = None
        self.logging_service: Optional[LoggingService] = None
        self.monitoring_service: Optional[MonitoringService] = None
        self.recovery_engine: Optional[RecoveryEngine] = None
        self.notification_service: Optional[NotificationService] = None
        self.plugin_manager: Optional[PluginManager] = None
        self.integrator: Optional[MonitoringRecoveryIntegrator] = None
        
        # Logger will be initialized after logging service
        self.logger: Optional[logging.Logger] = None
        
        # Signal handlers
        self._original_sigterm_handler = None
        self._original_sigint_handler = None
        
        # System resilience
        self._health_check_thread: Optional[threading.Thread] = None
        self._error_count = 0
        self._last_error_time: Optional[datetime] = None
        self._degraded_mode = False
        self._resource_monitor_thread: Optional[threading.Thread] = None
        
        # Resource thresholds
        self.memory_threshold_percent = 85
        self.disk_threshold_percent = 90
        self.cpu_threshold_percent = 95
    
    def initialize(self) -> None:
        """
        Initialize all system components.
        
        Raises:
            ValidationError: If configuration is invalid
            SystemError: If system initialization fails
        """
        try:
            # Step 1: Load and validate configuration
            self._initialize_configuration()
            
            # Step 2: Setup logging system
            self._initialize_logging()
            
            # Step 3: Initialize plugin system
            self._initialize_plugins()
            
            # Step 4: Initialize core services
            self._initialize_monitoring()
            self._initialize_recovery()
            self._initialize_notification()
            
            # Step 5: Initialize integration layer
            self._initialize_integration()
            
            # Step 6: Wire components together
            self._wire_components()
            
            self.logger.info("System initialization completed successfully")
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"System initialization failed: {e}")
            else:
                print(f"System initialization failed: {e}", file=sys.stderr)
            raise SystemError(f"Failed to initialize system: {e}")
    
    def start(self) -> None:
        """
        Start the self-healing system.
        
        Raises:
            SystemError: If system is already running or fails to start
        """
        if self.running:
            raise SystemError("System is already running")
        
        try:
            # Setup signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Setup global exception handler
            self._setup_global_exception_handler()
            
            # Start all services
            self._start_services()
            
            # Start system monitoring
            self._start_system_monitoring()
            
            self.running = True
            self.logger.info("Kafka Self-Healing system started successfully")
            
            # Log startup summary
            self._log_startup_summary()
            
        except Exception as e:
            self.logger.error(f"Failed to start system: {e}")
            self._cleanup()
            raise SystemError(f"Failed to start system: {e}")
    
    def stop(self) -> None:
        """Stop the self-healing system gracefully."""
        if not self.running:
            self.logger.warning("System is not running")
            return
        
        self.logger.info("Initiating system shutdown...")
        self.running = False
        self.shutdown_event.set()
        
        try:
            # Stop system monitoring threads
            if self._health_check_thread and self._health_check_thread.is_alive():
                self._health_check_thread.join(timeout=5)
            if self._resource_monitor_thread and self._resource_monitor_thread.is_alive():
                self._resource_monitor_thread.join(timeout=5)
            
            # Stop all services in reverse order
            self._stop_services()
            
            # Restore original signal handlers
            self._restore_signal_handlers()
            
            # Log shutdown
            if self.logging_service:
                self.logging_service.log_system_shutdown()
            
            self.logger.info("System shutdown completed")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
        finally:
            self._cleanup()
    
    def run(self) -> None:
        """
        Run the application until shutdown is requested.
        
        This method blocks until the system is shut down via signal or stop() call.
        """
        if not self.running:
            raise SystemError("System must be started before running")
        
        self.logger.info("System is running. Press Ctrl+C to stop.")
        
        try:
            # Main application loop
            while self.running and not self.shutdown_event.is_set():
                # Check system health periodically
                self._check_system_health()
                
                # Wait for shutdown signal or timeout
                if self.shutdown_event.wait(timeout=30):
                    break
                    
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            if self.running:
                self.stop()
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get current system status and statistics.
        
        Returns:
            Dictionary containing system status information
        """
        status = {
            'running': self.running,
            'uptime_seconds': 0,
            'degraded_mode': self._degraded_mode,
            'error_count': self._error_count,
            'last_error_time': self._last_error_time.isoformat() if self._last_error_time else None,
            'components': {},
            'resources': self._get_resource_status()
        }
        
        if self.monitoring_service:
            status['components']['monitoring'] = self.monitoring_service.get_monitoring_statistics()
        
        if self.recovery_engine:
            status['components']['recovery'] = {
                'active_recoveries': len(self.recovery_engine.get_active_recoveries()),
                'registered_actions': len(self.recovery_engine.recovery_actions),
                'registered_plugins': len(self.recovery_engine.recovery_plugins)
            }
        
        if self.integrator:
            status['components']['integration'] = self.integrator.get_failure_statistics()
        
        if self.notification_service:
            status['components']['notification'] = {
                'queue_sizes': self.notification_service.delivery_queue.get_queue_sizes(),
                'registered_notifiers': len(self.notification_service.notifiers)
            }
        
        return status
    
    def _get_resource_status(self) -> Dict[str, Any]:
        """Get current system resource status."""
        try:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
            
            return {
                'memory': {
                    'percent': memory.percent,
                    'available_gb': memory.available / (1024**3),
                    'threshold_percent': self.memory_threshold_percent,
                    'status': 'critical' if memory.percent > self.memory_threshold_percent else 'normal'
                },
                'disk': {
                    'percent': (disk.used / disk.total) * 100,
                    'free_gb': disk.free / (1024**3),
                    'threshold_percent': self.disk_threshold_percent,
                    'status': 'critical' if (disk.used / disk.total) * 100 > self.disk_threshold_percent else 'normal'
                },
                'cpu': {
                    'percent': cpu_percent,
                    'threshold_percent': self.cpu_threshold_percent,
                    'status': 'critical' if cpu_percent > self.cpu_threshold_percent else 'normal'
                }
            }
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error getting resource status: {e}")
            return {'error': str(e)}
    
    def _initialize_configuration(self) -> None:
        """Initialize configuration management."""
        self.config_manager = ConfigurationManager()
        
        # Load configuration file if provided
        if self.config_path:
            config_data = self.config_manager.load_config(self.config_path)
            self.config_manager.validate_config(config_data)
        else:
            # Look for default configuration files
            default_configs = [
                'config.yaml',
                'config.yml', 
                'config.json',
                'config.ini'
            ]
            
            config_loaded = False
            for config_file in default_configs:
                if Path(config_file).exists():
                    config_data = self.config_manager.load_config(config_file)
                    self.config_manager.validate_config(config_data)
                    self.config_path = config_file
                    config_loaded = True
                    break
            
            if not config_loaded:
                raise ValidationError("No configuration file found. Please provide a config file.")
    
    def _initialize_logging(self) -> None:
        """Initialize logging system."""
        # Create log config from system configuration
        log_config = LogConfig()
        
        # Override with configuration values if available
        if self.config_manager._config_data and 'logging' in self.config_manager._config_data:
            log_settings = self.config_manager._config_data['logging']
            log_config.log_dir = log_settings.get('log_dir', log_config.log_dir)
            log_config.log_level = log_settings.get('log_level', log_config.log_level)
            log_config.max_file_size_mb = log_settings.get('max_file_size_mb', log_config.max_file_size_mb)
            log_config.backup_count = log_settings.get('backup_count', log_config.backup_count)
            log_config.compress_backups = log_settings.get('compress_backups', log_config.compress_backups)
            log_config.console_logging = log_settings.get('console_logging', log_config.console_logging)
            log_config.structured_format = log_settings.get('structured_format', log_config.structured_format)
        
        self.logging_service = LoggingService(log_config)
        self.logger = self.logging_service.get_logger('main')
    
    def _initialize_plugins(self) -> None:
        """Initialize plugin system."""
        self.plugin_manager = PluginManager()
        
        # Load plugins from default directory if it exists
        plugin_dir = Path('plugins')
        if plugin_dir.exists():
            self.plugin_manager.load_plugins(str(plugin_dir))
            self.logger.info(f"Loaded plugins from {plugin_dir}")
    
    def _initialize_monitoring(self) -> None:
        """Initialize monitoring service."""
        cluster_config = self.config_manager.get_cluster_config()
        self.monitoring_service = MonitoringService(cluster_config)
        
        # Register custom monitoring plugins if available
        if self.plugin_manager:
            for plugin in self.plugin_manager.get_monitoring_plugins():
                self.monitoring_service.add_monitoring_plugin(plugin.name, plugin)
        
        self.logger.info("Monitoring service initialized")
    
    def _initialize_recovery(self) -> None:
        """Initialize recovery engine."""
        retry_policy = self.config_manager.get_retry_policy()
        self.recovery_engine = RecoveryEngine(retry_policy)
        
        # Register recovery plugins if available
        if self.plugin_manager:
            for plugin in self.plugin_manager.get_recovery_plugins():
                self.recovery_engine.register_recovery_plugin(plugin)
        
        self.logger.info("Recovery engine initialized")
    
    def _initialize_notification(self) -> None:
        """Initialize notification service."""
        notification_config = self.config_manager.get_notification_config()
        self.notification_service = NotificationService(notification_config)
        
        # Register notification plugins if available
        if self.plugin_manager:
            for plugin in self.plugin_manager.get_notification_plugins():
                self.notification_service.register_notifier(plugin.name, plugin)
        
        self.logger.info("Notification service initialized")
    
    def _initialize_integration(self) -> None:
        """Initialize monitoring-recovery integration layer."""
        self.integrator = MonitoringRecoveryIntegrator(
            self.monitoring_service,
            self.recovery_engine
        )
        self.logger.info("Monitoring-recovery integration initialized")
    
    def _wire_components(self) -> None:
        """Wire components together with callbacks and integrations."""
        # Connect integration layer to notification system
        def on_recovery_escalation(node_id, recovery_history):
            """Handle recovery escalation by sending notifications."""
            try:
                # Find the node config
                cluster_config = self.config_manager.get_cluster_config()
                node = cluster_config.get_node_by_id(node_id)
                if node and recovery_history:
                    last_error = recovery_history[-1].stderr if recovery_history[-1].stderr else "Unknown error"
                    self.notification_service.send_failure_alert(node, recovery_history, last_error)
                    self.logger.info(f"Failure alert sent for node {node_id}")
            except Exception as e:
                self.logger.error(f"Error sending failure notification: {e}")
        
        def on_recovery_success(recovery_event):
            """Handle successful recovery by sending confirmation."""
            try:
                node_config = recovery_event.node_config
                successful_action = recovery_event.recovery_result
                
                # Get failed attempts from recovery history
                recovery_history = self.recovery_engine.get_recovery_history(node_config.node_id)
                failed_attempts = [r for r in recovery_history[:-1] if not r.success]
                
                # Calculate downtime duration
                failure_time = recovery_event.failure_event.timestamp
                recovery_time = recovery_event.timestamp
                downtime = recovery_time - failure_time
                downtime_str = f"{int(downtime.total_seconds())} seconds"
                
                self.notification_service.send_recovery_confirmation(
                    node_config, successful_action, downtime_str, failed_attempts
                )
                self.logger.info(f"Recovery confirmation sent for node {node_config.node_id}")
            except Exception as e:
                self.logger.error(f"Error sending recovery confirmation: {e}")
        
        # Register callbacks with integration layer
        self.integrator.register_escalation_callback(on_recovery_escalation)
        self.integrator.register_recovery_callback(on_recovery_success)
        
        self.logger.info("Component integration completed")
    
    def _setup_global_exception_handler(self) -> None:
        """Setup global exception handler for unhandled exceptions."""
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                # Allow KeyboardInterrupt to be handled normally
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            # Log the unhandled exception
            if self.logger:
                self.logger.critical(
                    "Unhandled exception occurred",
                    exc_info=(exc_type, exc_value, exc_traceback)
                )
            else:
                # Fallback if logger not available
                print(f"CRITICAL: Unhandled exception: {exc_type.__name__}: {exc_value}", file=sys.stderr)
                traceback.print_exception(exc_type, exc_value, exc_traceback)
            
            # Increment error count
            self._error_count += 1
            self._last_error_time = datetime.now()
            
            # If too many errors, initiate graceful shutdown
            if self._error_count > 5:
                self.logger.critical("Too many unhandled exceptions, initiating shutdown")
                self.shutdown_event.set()
        
        sys.excepthook = handle_exception
    
    def _start_system_monitoring(self) -> None:
        """Start system health and resource monitoring."""
        # Start health check thread
        self._health_check_thread = threading.Thread(
            target=self._system_health_monitor_loop,
            daemon=True
        )
        self._health_check_thread.start()
        
        # Start resource monitor thread
        self._resource_monitor_thread = threading.Thread(
            target=self._resource_monitor_loop,
            daemon=True
        )
        self._resource_monitor_thread.start()
        
        self.logger.info("System monitoring started")
    
    def _system_health_monitor_loop(self) -> None:
        """Monitor system health and component status."""
        while self.running and not self.shutdown_event.is_set():
            try:
                self._check_system_health()
                
                # Check for degraded mode conditions
                self._check_degraded_mode()
                
                # Sleep for 30 seconds between checks
                if self.shutdown_event.wait(timeout=30):
                    break
                    
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error in system health monitor: {e}")
                time.sleep(5)  # Brief pause before retrying
    
    def _resource_monitor_loop(self) -> None:
        """Monitor system resources and handle constraints."""
        while self.running and not self.shutdown_event.is_set():
            try:
                self._check_resource_constraints()
                
                # Sleep for 60 seconds between resource checks
                if self.shutdown_event.wait(timeout=60):
                    break
                    
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Error in resource monitor: {e}")
                time.sleep(10)  # Brief pause before retrying
    
    def _check_degraded_mode(self) -> None:
        """Check if system should enter degraded mode."""
        should_degrade = False
        
        # Check error rate
        if self._error_count > 3 and self._last_error_time:
            time_since_error = datetime.now() - self._last_error_time
            if time_since_error < timedelta(minutes=5):
                should_degrade = True
                self.logger.warning("High error rate detected, considering degraded mode")
        
        # Check component health (only if system is running)
        if self.running and self.monitoring_service and not self.monitoring_service.is_monitoring_active():
            should_degrade = True
            self.logger.warning("Monitoring service inactive, entering degraded mode")
        
        # Enter or exit degraded mode
        if should_degrade and not self._degraded_mode:
            self._enter_degraded_mode()
        elif not should_degrade and self._degraded_mode:
            self._exit_degraded_mode()
    
    def _enter_degraded_mode(self) -> None:
        """Enter degraded mode with reduced functionality."""
        self._degraded_mode = True
        self.logger.warning("Entering degraded mode")
        
        # Reduce monitoring frequency
        if self.monitoring_service and hasattr(self.monitoring_service, 'cluster_config'):
            original_interval = self.monitoring_service.cluster_config.monitoring_interval_seconds
            degraded_interval = max(original_interval * 2, 60)  # At least 60 seconds
            self.monitoring_service.cluster_config.monitoring_interval_seconds = degraded_interval
            self.logger.info(f"Reduced monitoring interval to {degraded_interval} seconds")
        
        # Reduce concurrent recoveries
        if self.integrator:
            self.integrator.set_max_concurrent_recoveries(2)
            self.logger.info("Reduced max concurrent recoveries to 2")
    
    def _exit_degraded_mode(self) -> None:
        """Exit degraded mode and restore normal functionality."""
        self._degraded_mode = False
        self.logger.info("Exiting degraded mode")
        
        # Restore normal monitoring frequency
        if self.monitoring_service and self.config_manager:
            try:
                cluster_config = self.config_manager.get_cluster_config()
                normal_interval = cluster_config.monitoring_interval_seconds
                self.monitoring_service.cluster_config.monitoring_interval_seconds = normal_interval
                self.logger.info(f"Restored monitoring interval to {normal_interval} seconds")
            except Exception as e:
                self.logger.error(f"Error restoring monitoring interval: {e}")
        
        # Restore normal concurrent recoveries
        if self.integrator:
            self.integrator.set_max_concurrent_recoveries(5)
            self.logger.info("Restored max concurrent recoveries to 5")
        
        # Reset error count
        self._error_count = 0
        self._last_error_time = None
    
    def _check_resource_constraints(self) -> None:
        """Check system resource usage and handle constraints."""
        try:
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > self.memory_threshold_percent:
                self.logger.warning(f"High memory usage: {memory.percent:.1f}%")
                self._handle_high_memory_usage()
            
            # Check disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > self.disk_threshold_percent:
                self.logger.warning(f"High disk usage: {disk_percent:.1f}%")
                self._handle_high_disk_usage()
            
            # Check CPU usage (average over last minute)
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > self.cpu_threshold_percent:
                self.logger.warning(f"High CPU usage: {cpu_percent:.1f}%")
                self._handle_high_cpu_usage()
                
        except Exception as e:
            self.logger.error(f"Error checking resource constraints: {e}")
    
    def _handle_high_memory_usage(self) -> None:
        """Handle high memory usage by cleaning up resources."""
        try:
            # Clear old log entries
            if self.logging_service:
                self.logging_service.cleanup_old_logs(days_to_keep=7)
            
            # Clear old recovery history
            if self.recovery_engine:
                # Clear history for nodes not seen recently
                for node_id in list(self.recovery_engine.recovery_history.keys()):
                    history = self.recovery_engine.recovery_history[node_id]
                    if history and len(history) > 10:
                        # Keep only last 10 entries
                        self.recovery_engine.recovery_history[node_id] = history[-10:]
            
            # Clear old integration events
            if self.integrator:
                for node_id in list(self.integrator.failure_events.keys()):
                    events = self.integrator.failure_events[node_id]
                    if len(events) > 20:
                        self.integrator.failure_events[node_id] = events[-20:]
                
                for node_id in list(self.integrator.recovery_events.keys()):
                    events = self.integrator.recovery_events[node_id]
                    if len(events) > 20:
                        self.integrator.recovery_events[node_id] = events[-20:]
            
            self.logger.info("Performed memory cleanup")
            
        except Exception as e:
            self.logger.error(f"Error handling high memory usage: {e}")
    
    def _handle_high_disk_usage(self) -> None:
        """Handle high disk usage by cleaning up logs and temporary files."""
        try:
            # Aggressive log cleanup
            if self.logging_service:
                self.logging_service.cleanup_old_logs(days_to_keep=3)
            
            # Clean up temporary files in log directory
            if hasattr(self.logging_service, 'log_config'):
                log_dir = Path(self.logging_service.log_config.log_dir)
                if log_dir.exists():
                    for temp_file in log_dir.glob("*.tmp"):
                        try:
                            temp_file.unlink()
                        except Exception:
                            pass
            
            self.logger.warning("Performed disk cleanup due to high usage")
            
        except Exception as e:
            self.logger.error(f"Error handling high disk usage: {e}")
    
    def _handle_high_cpu_usage(self) -> None:
        """Handle high CPU usage by reducing system load."""
        try:
            # Temporarily increase monitoring intervals
            if self.monitoring_service and hasattr(self.monitoring_service, 'cluster_config'):
                current_interval = self.monitoring_service.cluster_config.monitoring_interval_seconds
                temp_interval = min(current_interval * 2, 300)  # Max 5 minutes
                self.monitoring_service.cluster_config.monitoring_interval_seconds = temp_interval
                self.logger.info(f"Temporarily increased monitoring interval to {temp_interval} seconds")
            
            # Reduce concurrent operations
            if self.integrator:
                self.integrator.set_max_concurrent_recoveries(1)
                self.logger.info("Temporarily reduced concurrent recoveries to 1")
            
            # Schedule restoration after 5 minutes
            def restore_normal_operation():
                time.sleep(300)  # 5 minutes
                try:
                    if self.monitoring_service and self.config_manager:
                        cluster_config = self.config_manager.get_cluster_config()
                        normal_interval = cluster_config.monitoring_interval_seconds
                        self.monitoring_service.cluster_config.monitoring_interval_seconds = normal_interval
                    
                    if self.integrator:
                        self.integrator.set_max_concurrent_recoveries(5)
                    
                    self.logger.info("Restored normal operation after high CPU usage")
                except Exception as e:
                    self.logger.error(f"Error restoring normal operation: {e}")
            
            threading.Thread(target=restore_normal_operation, daemon=True).start()
            
        except Exception as e:
            self.logger.error(f"Error handling high CPU usage: {e}")
    
    def _start_services(self) -> None:
        """Start all services in proper order."""
        # Start notification service first (for error reporting)
        if self.notification_service:
            self.notification_service.start()
            self.logger.info("Notification service started")
        
        # Start monitoring service
        if self.monitoring_service:
            self.monitoring_service.start_monitoring()
            self.logger.info("Monitoring service started")
    
    def _stop_services(self) -> None:
        """Stop all services in reverse order."""
        # Stop monitoring first to prevent new recovery attempts
        if self.monitoring_service:
            self.monitoring_service.stop_monitoring()
            self.logger.info("Monitoring service stopped")
        
        # Stop notification service last
        if self.notification_service:
            self.notification_service.stop()
            self.logger.info("Notification service stopped")
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            self.logger.info(f"Received {signal_name} signal, initiating shutdown...")
            self.shutdown_event.set()
        
        # Store original handlers
        self._original_sigterm_handler = signal.signal(signal.SIGTERM, signal_handler)
        self._original_sigint_handler = signal.signal(signal.SIGINT, signal_handler)
    
    def _restore_signal_handlers(self) -> None:
        """Restore original signal handlers."""
        if self._original_sigterm_handler:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)
        if self._original_sigint_handler:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
    
    def _check_system_health(self) -> None:
        """Perform periodic system health checks."""
        try:
            health_issues = []
            
            # Check if services are still running
            if self.monitoring_service and not self.monitoring_service.is_monitoring_active():
                health_issues.append("Monitoring service is not active")
                # Attempt to restart monitoring
                try:
                    self.monitoring_service.start_monitoring()
                    self.logger.info("Attempted to restart monitoring service")
                except Exception as e:
                    self.logger.error(f"Failed to restart monitoring service: {e}")
            
            # Check queue sizes for potential issues
            if self.notification_service:
                try:
                    queue_sizes = self.notification_service.delivery_queue.get_queue_sizes()
                    if queue_sizes['delivery_queue'] > 100:
                        health_issues.append(f"Large notification delivery queue: {queue_sizes['delivery_queue']}")
                    if queue_sizes['retry_queue'] > 50:
                        health_issues.append(f"Large notification retry queue: {queue_sizes['retry_queue']}")
                except Exception as e:
                    health_issues.append(f"Cannot check notification queues: {e}")
            
            # Check integration layer health
            if self.integrator:
                try:
                    stats = self.integrator.get_failure_statistics()
                    if stats['active_recoveries'] > 10:
                        health_issues.append(f"Too many active recoveries: {stats['active_recoveries']}")
                    if stats['nodes_in_cooldown'] > 5:
                        health_issues.append(f"Many nodes in cooldown: {stats['nodes_in_cooldown']}")
                except Exception as e:
                    health_issues.append(f"Cannot check integration stats: {e}")
            
            # Check recovery engine health
            if self.recovery_engine:
                try:
                    active_recoveries = self.recovery_engine.get_active_recoveries()
                    if len(active_recoveries) > 0:
                        # Check for stuck recoveries
                        for node_id, retry_info in active_recoveries.items():
                            if retry_info['attempt_count'] >= 3:
                                health_issues.append(f"Node {node_id} has many retry attempts: {retry_info['attempt_count']}")
                except Exception as e:
                    health_issues.append(f"Cannot check recovery engine: {e}")
            
            # Log health issues
            if health_issues:
                for issue in health_issues:
                    self.logger.warning(f"Health issue: {issue}")
            else:
                self.logger.debug("System health check passed")
            
        except Exception as e:
            self.logger.error(f"Error during system health check: {e}")
            self._error_count += 1
            self._last_error_time = datetime.now()
    
    def _log_startup_summary(self) -> None:
        """Log system startup summary."""
        cluster_config = self.config_manager.get_cluster_config()
        
        summary = {
            'config_file': self.config_path,
            'total_nodes': len(cluster_config.nodes),
            'kafka_brokers': len(cluster_config.get_kafka_brokers()),
            'zookeeper_nodes': len(cluster_config.get_zookeeper_nodes()),
            'monitoring_interval': cluster_config.monitoring_interval_seconds,
            'components_initialized': [
                'configuration',
                'logging',
                'monitoring',
                'recovery',
                'notification',
                'plugins'
            ]
        }
        
        if self.logging_service:
            self.logging_service.log_system_startup(summary)
    
    def _cleanup(self) -> None:
        """Cleanup resources and reset state."""
        self.running = False
        self.shutdown_event.clear()


def main():
    """Main entry point for the application."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Kafka Self-Healing System')
    parser.add_argument(
        '--config', '-c',
        type=str,
        help='Path to configuration file'
    )
    parser.add_argument(
        '--version', '-v',
        action='version',
        version='Kafka Self-Healing System 1.0.0'
    )
    
    args = parser.parse_args()
    
    app = KafkaSelfHealingApp(config_path=args.config)
    
    try:
        # Initialize and start the system
        app.initialize()
        app.start()
        
        # Run until shutdown
        app.run()
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if app.running:
            app.stop()


if __name__ == '__main__':
    main()