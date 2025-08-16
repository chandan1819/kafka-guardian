"""
Logging and audit system for the Kafka self-healing system.

This module provides structured logging capabilities, audit trails,
and automatic log rotation with credential filtering.
"""

import logging
import logging.handlers
import json
import re
import os
import gzip
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field

from .models import NodeConfig, NodeStatus, RecoveryResult


@dataclass
class LogConfig:
    """Configuration for logging system."""
    log_dir: str = "logs"
    log_level: str = "INFO"
    max_file_size_mb: int = 10
    backup_count: int = 5
    compress_backups: bool = True
    audit_log_enabled: bool = True
    console_logging: bool = True
    structured_format: bool = True
    
    def __post_init__(self):
        """Validate log configuration."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        if self.max_file_size_mb < 1:
            raise ValueError("max_file_size_mb must be at least 1")
        if self.backup_count < 0:
            raise ValueError("backup_count must be non-negative")


class CredentialFilter(logging.Filter):
    """Filter to prevent credential exposure in logs."""
    
    # Patterns to match sensitive information
    SENSITIVE_PATTERNS = [
        r'password["\s]*[:=]["\s]*[^"\s,}]+',
        r'passwd["\s]*[:=]["\s]*[^"\s,}]+',
        r'secret["\s]*[:=]["\s]*[^"\s,}]+',
        r'token["\s]*[:=]["\s]*[^"\s,}]+',
        r'key["\s]*[:=]["\s]*[^"\s,}]+',
        r'api_key["\s]*[:=]["\s]*[^"\s,}]+',
        r'auth["\s]*[:=]["\s]*[^"\s,}]+',
        r'credential["\s]*[:=]["\s]*[^"\s,}]+',
    ]
    
    def __init__(self):
        super().__init__()
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.SENSITIVE_PATTERNS
        ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out sensitive information from log records."""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._sanitize_message(record.msg)
        
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                self._sanitize_message(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        
        return True
    
    def _sanitize_message(self, message: str) -> str:
        """Remove sensitive information from a message."""
        sanitized = message
        for pattern in self.compiled_patterns:
            sanitized = pattern.sub(
                lambda m: m.group(0).split('=')[0] + '=***REDACTED***',
                sanitized
            )
        return sanitized


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'node_id'):
            log_entry['node_id'] = record.node_id
        if hasattr(record, 'action_type'):
            log_entry['action_type'] = record.action_type
        if hasattr(record, 'component'):
            log_entry['component'] = record.component
        if hasattr(record, 'duration_ms'):
            log_entry['duration_ms'] = record.duration_ms
        
        # Add exception info if present
        if record.exc_info and record.exc_info != (None, None, None):
            log_entry['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)


class LogRotator:
    """Handles automatic log file rotation and archival."""
    
    def __init__(self, log_config: LogConfig):
        self.log_config = log_config
        self.log_dir = Path(log_config.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def setup_rotating_handler(self, filename: str) -> logging.handlers.RotatingFileHandler:
        """Create a rotating file handler with compression."""
        log_path = self.log_dir / filename
        max_bytes = self.log_config.max_file_size_mb * 1024 * 1024
        
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=self.log_config.backup_count
        )
        
        # Override doRollover to add compression
        if self.log_config.compress_backups:
            original_do_rollover = handler.doRollover
            def compress_rollover():
                return self._compress_rollover(handler, original_do_rollover)
            handler.doRollover = compress_rollover
        
        return handler
    
    def _compress_rollover(self, handler: logging.handlers.RotatingFileHandler, 
                          original_rollover) -> None:
        """Perform rollover with compression of old log files."""
        original_rollover()
        
        # Compress the rotated file
        log_path = Path(handler.baseFilename)
        rotated_file = f"{log_path}.1"
        
        if os.path.exists(rotated_file):
            compressed_file = f"{rotated_file}.gz"
            with open(rotated_file, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(rotated_file)
    
    def cleanup_old_logs(self, days_to_keep: int = 30) -> None:
        """Remove log files older than specified days."""
        cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 3600)
        
        for log_file in self.log_dir.glob("*.log*"):
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()


class AuditLogger:
    """Specialized logger for tracking system actions with timestamps."""
    
    def __init__(self, log_config: LogConfig):
        self.log_config = log_config
        self.logger = logging.getLogger('kafka_self_healing.audit')
        self.logger.setLevel(logging.INFO)
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        if log_config.audit_log_enabled:
            self._setup_audit_handler()
    
    def _setup_audit_handler(self) -> None:
        """Setup audit log file handler."""
        rotator = LogRotator(self.log_config)
        handler = rotator.setup_rotating_handler('audit.log')
        
        # Use structured format for audit logs
        formatter = StructuredFormatter()
        handler.setFormatter(formatter)
        
        # Add credential filter
        handler.addFilter(CredentialFilter())
        
        self.logger.addHandler(handler)
    
    def log_system_event(self, event_type: str, message: str, **kwargs) -> None:
        """Log a system-level event."""
        extra = {
            'component': 'system',
            'event_type': event_type,
            **kwargs
        }
        self.logger.info(message, extra=extra)
    
    def log_monitoring_event(self, node: NodeConfig, status: NodeStatus, 
                           duration_ms: float = 0) -> None:
        """Log a monitoring event."""
        extra = {
            'component': 'monitoring',
            'node_id': node.node_id,
            'node_type': node.node_type,
            'host': node.host,
            'port': node.port,
            'is_healthy': status.is_healthy,
            'monitoring_method': status.monitoring_method,
            'duration_ms': duration_ms
        }
        
        message = f"Health check for {node.node_id}: {'HEALTHY' if status.is_healthy else 'UNHEALTHY'}"
        if not status.is_healthy and status.error_message:
            message += f" - {status.error_message}"
        
        self.logger.info(message, extra=extra)
    
    def log_recovery_action(self, node: NodeConfig, result: RecoveryResult) -> None:
        """Log a recovery action execution."""
        extra = {
            'component': 'recovery',
            'node_id': node.node_id,
            'node_type': node.node_type,
            'action_type': result.action_type,
            'command': result.command_executed,
            'exit_code': result.exit_code,
            'success': result.success
        }
        
        message = f"Recovery action {result.action_type} for {node.node_id}: {'SUCCESS' if result.success else 'FAILED'}"
        if not result.success:
            message += f" (exit code: {result.exit_code})"
        
        self.logger.info(message, extra=extra)
    
    def log_notification_event(self, notification_type: str, recipient: str, 
                             status: str, **kwargs) -> None:
        """Log a notification delivery event."""
        extra = {
            'component': 'notification',
            'notification_type': notification_type,
            'recipient': recipient,
            'delivery_status': status,
            **kwargs
        }
        
        message = f"Notification {notification_type} to {recipient}: {status}"
        self.logger.info(message, extra=extra)


class LoggingService:
    """Main logging service with structured logging capabilities."""
    
    def __init__(self, log_config: Optional[LogConfig] = None):
        self.log_config = log_config or LogConfig()
        self.audit_logger = AuditLogger(self.log_config)
        self.rotator = LogRotator(self.log_config)
        
        # Setup main application logger
        self.logger = logging.getLogger('kafka_self_healing')
        self.logger.setLevel(getattr(logging, self.log_config.log_level.upper()))
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """Setup logging handlers."""
        # File handler for application logs
        file_handler = self.rotator.setup_rotating_handler('application.log')
        
        if self.log_config.structured_format:
            file_formatter = StructuredFormatter()
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(CredentialFilter())
        self.logger.addHandler(file_handler)
        
        # Console handler if enabled
        if self.log_config.console_logging:
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            console_handler.addFilter(CredentialFilter())
            self.logger.addHandler(console_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger instance for a specific component."""
        return logging.getLogger(f'kafka_self_healing.{name}')
    
    def log_monitoring_event(self, node: NodeConfig, status: NodeStatus) -> None:
        """Log a monitoring event through audit logger."""
        start_time = datetime.now()
        self.audit_logger.log_monitoring_event(node, status)
        
        # Also log to main logger for debugging
        level = logging.INFO if status.is_healthy else logging.WARNING
        self.logger.log(
            level,
            f"Node {node.node_id} health check: {'OK' if status.is_healthy else 'FAILED'}",
            extra={'node_id': node.node_id, 'component': 'monitoring'}
        )
    
    def log_recovery_action(self, node: NodeConfig, action: str, result: RecoveryResult) -> None:
        """Log a recovery action execution."""
        self.audit_logger.log_recovery_action(node, result)
        
        # Also log to main logger
        level = logging.INFO if result.success else logging.ERROR
        self.logger.log(
            level,
            f"Recovery action '{action}' for {node.node_id}: {'completed' if result.success else 'failed'}",
            extra={'node_id': node.node_id, 'action_type': action, 'component': 'recovery'}
        )
    
    def log_notification_event(self, notification_type: str, recipient: str, status: str) -> None:
        """Log a notification delivery event."""
        self.audit_logger.log_notification_event(notification_type, recipient, status)
        
        # Also log to main logger
        level = logging.INFO if status.lower() == 'sent' else logging.WARNING
        self.logger.log(
            level,
            f"Notification {notification_type} to {recipient}: {status}",
            extra={'component': 'notification'}
        )
    
    def log_system_startup(self, config_summary: Dict[str, Any]) -> None:
        """Log system startup event."""
        self.audit_logger.log_system_event(
            'startup',
            'Kafka self-healing system started',
            **config_summary
        )
        self.logger.info("System startup completed", extra={'component': 'system'})
    
    def log_system_shutdown(self) -> None:
        """Log system shutdown event."""
        self.audit_logger.log_system_event('shutdown', 'Kafka self-healing system stopped')
        self.logger.info("System shutdown completed", extra={'component': 'system'})
    
    def cleanup_old_logs(self, days_to_keep: int = 30) -> None:
        """Clean up old log files."""
        self.rotator.cleanup_old_logs(days_to_keep)
        self.logger.info(f"Cleaned up log files older than {days_to_keep} days")