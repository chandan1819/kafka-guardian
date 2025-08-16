"""
Unit tests for the logging and audit system.
"""

import json
import logging
import os
import tempfile
import gzip
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from src.kafka_self_healing.logging import (
    LoggingService,
    AuditLogger,
    LogRotator,
    LogConfig,
    CredentialFilter,
    StructuredFormatter
)
from src.kafka_self_healing.models import NodeConfig, NodeStatus, RecoveryResult, RetryPolicy


class TestLogConfig:
    """Test LogConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = LogConfig()
        assert config.log_dir == "logs"
        assert config.log_level == "INFO"
        assert config.max_file_size_mb == 10
        assert config.backup_count == 5
        assert config.compress_backups is True
        assert config.audit_log_enabled is True
        assert config.console_logging is True
        assert config.structured_format is True
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = LogConfig(
            log_dir="/tmp/logs",
            log_level="DEBUG",
            max_file_size_mb=20,
            backup_count=10,
            compress_backups=False
        )
        assert config.log_dir == "/tmp/logs"
        assert config.log_level == "DEBUG"
        assert config.max_file_size_mb == 20
        assert config.backup_count == 10
        assert config.compress_backups is False
    
    def test_invalid_log_level(self):
        """Test validation of invalid log level."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            LogConfig(log_level="INVALID")
    
    def test_invalid_file_size(self):
        """Test validation of invalid file size."""
        with pytest.raises(ValueError, match="max_file_size_mb must be at least 1"):
            LogConfig(max_file_size_mb=0)
    
    def test_invalid_backup_count(self):
        """Test validation of invalid backup count."""
        with pytest.raises(ValueError, match="backup_count must be non-negative"):
            LogConfig(backup_count=-1)


class TestCredentialFilter:
    """Test CredentialFilter class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.filter = CredentialFilter()
    
    def test_filter_password(self):
        """Test filtering of password fields."""
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Config: password=secret123", args=(), exc_info=None
        )
        
        self.filter.filter(record)
        assert "secret123" not in record.msg
        assert "password=***REDACTED***" in record.msg
    
    def test_filter_multiple_credentials(self):
        """Test filtering of multiple credential types."""
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Config: password=secret123, api_key=abc456, token=xyz789",
            args=(), exc_info=None
        )
        
        self.filter.filter(record)
        assert "secret123" not in record.msg
        assert "abc456" not in record.msg
        assert "xyz789" not in record.msg
        assert "password=***REDACTED***" in record.msg
        assert "api_key=***REDACTED***" in record.msg
        assert "token=***REDACTED***" in record.msg
    
    def test_filter_args(self):
        """Test filtering of log record args."""
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Config: %s", args=("password=secret123",), exc_info=None
        )
        
        self.filter.filter(record)
        assert "secret123" not in record.args[0]
        assert "password=***REDACTED***" in record.args[0]
    
    def test_no_credentials(self):
        """Test that normal messages are not modified."""
        original_msg = "Normal log message without credentials"
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=original_msg, args=(), exc_info=None
        )
        
        self.filter.filter(record)
        assert record.msg == original_msg
    
    def test_case_insensitive(self):
        """Test case-insensitive credential filtering."""
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Config: PASSWORD=secret123, Secret=abc456",
            args=(), exc_info=None
        )
        
        self.filter.filter(record)
        assert "secret123" not in record.msg
        assert "abc456" not in record.msg
        assert "PASSWORD=***REDACTED***" in record.msg
        assert "Secret=***REDACTED***" in record.msg


class TestStructuredFormatter:
    """Test StructuredFormatter class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.formatter = StructuredFormatter()
    
    def test_basic_formatting(self):
        """Test basic JSON formatting."""
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname="/path/test.py",
            lineno=42, msg="Test message", args=(), exc_info=None
        )
        record.module = "test"
        record.funcName = "test_function"
        
        formatted = self.formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data['level'] == 'INFO'
        assert log_data['logger'] == 'test.logger'
        assert log_data['message'] == 'Test message'
        assert log_data['module'] == 'test'
        assert log_data['function'] == 'test_function'
        assert log_data['line'] == 42
        assert 'timestamp' in log_data
    
    def test_extra_fields(self):
        """Test formatting with extra fields."""
        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname="/path/test.py",
            lineno=42, msg="Test message", args=(), exc_info=None
        )
        record.module = "test"
        record.funcName = "test_function"
        record.node_id = "broker-1"
        record.action_type = "restart"
        record.component = "recovery"
        record.duration_ms = 1500.5
        
        formatted = self.formatter.format(record)
        log_data = json.loads(formatted)
        
        assert log_data['node_id'] == 'broker-1'
        assert log_data['action_type'] == 'restart'
        assert log_data['component'] == 'recovery'
        assert log_data['duration_ms'] == 1500.5
    
    def test_exception_formatting(self):
        """Test formatting with exception information."""
        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                name="test.logger", level=logging.ERROR, pathname="/path/test.py",
                lineno=42, msg="Error occurred", args=(), exc_info=exc_info
            )
            record.module = "test"
            record.funcName = "test_function"
            
            formatted = self.formatter.format(record)
            log_data = json.loads(formatted)
            
            assert 'exception' in log_data
            assert 'ValueError: Test exception' in log_data['exception']


class TestLogRotator:
    """Test LogRotator class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = LogConfig(log_dir=self.temp_dir, max_file_size_mb=1)
        self.rotator = LogRotator(self.config)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_log_directory_creation(self):
        """Test that log directory is created."""
        assert Path(self.temp_dir).exists()
        assert Path(self.temp_dir).is_dir()
    
    def test_rotating_handler_creation(self):
        """Test creation of rotating file handler."""
        handler = self.rotator.setup_rotating_handler("test.log")
        
        assert handler.maxBytes == 1024 * 1024  # 1MB
        assert handler.backupCount == 5
        assert str(handler.baseFilename).endswith("test.log")
    
    def test_compression_rollover(self):
        """Test log compression during rollover."""
        # Create config with compression enabled
        config = LogConfig(log_dir=self.temp_dir, compress_backups=True)
        rotator = LogRotator(config)
        handler = rotator.setup_rotating_handler("test.log")
        
        # Create a test log file
        log_file = Path(self.temp_dir) / "test.log"
        log_file.write_text("test log content")
        
        # Create the rotated file that would be created by rollover
        rotated_file = f"{log_file}.1"
        Path(rotated_file).write_text("rotated log content")
        
        # Test that the compression function exists and can be called
        with patch('gzip.open') as mock_gzip, \
             patch('shutil.copyfileobj') as mock_copy, \
             patch('os.remove') as mock_remove, \
             patch('os.path.exists', return_value=True):
            
            # Call the compression rollover directly
            rotator._compress_rollover(handler, lambda: None)
            
            # Verify compression was attempted
            mock_gzip.assert_called_once()
            mock_copy.assert_called_once()
            mock_remove.assert_called_once()
    
    def test_cleanup_old_logs(self):
        """Test cleanup of old log files."""
        # Create some test log files with different ages
        old_file = Path(self.temp_dir) / "old.log"
        recent_file = Path(self.temp_dir) / "recent.log"
        
        old_file.write_text("old content")
        recent_file.write_text("recent content")
        
        # Set old file modification time to 31 days ago
        old_time = datetime.now().timestamp() - (31 * 24 * 3600)
        os.utime(old_file, (old_time, old_time))
        
        # Cleanup files older than 30 days
        self.rotator.cleanup_old_logs(days_to_keep=30)
        
        # Old file should be removed, recent file should remain
        assert not old_file.exists()
        assert recent_file.exists()


class TestAuditLogger:
    """Test AuditLogger class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = LogConfig(log_dir=self.temp_dir)
        self.audit_logger = AuditLogger(self.config)
        
        # Sample test data
        self.node_config = NodeConfig(
            node_id="broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        self.node_status = NodeStatus(
            node_id="broker-1",
            is_healthy=True,
            last_check_time=datetime.now(),
            response_time_ms=150.5,
            monitoring_method="jmx"
        )
        
        self.recovery_result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_system_event_logging(self):
        """Test logging of system events."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_system_event(
                'startup',
                'System started',
                cluster_name='test-cluster'
            )
            
            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert args[0] == 'System started'
            assert kwargs['extra']['component'] == 'system'
            assert kwargs['extra']['event_type'] == 'startup'
            assert kwargs['extra']['cluster_name'] == 'test-cluster'
    
    def test_monitoring_event_logging(self):
        """Test logging of monitoring events."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_monitoring_event(
                self.node_config,
                self.node_status,
                duration_ms=100.0
            )
            
            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert 'Health check for broker-1: HEALTHY' in args[0]
            assert kwargs['extra']['component'] == 'monitoring'
            assert kwargs['extra']['node_id'] == 'broker-1'
            assert kwargs['extra']['is_healthy'] is True
            assert kwargs['extra']['duration_ms'] == 100.0
    
    def test_monitoring_event_unhealthy(self):
        """Test logging of unhealthy monitoring events."""
        unhealthy_status = NodeStatus(
            node_id="broker-1",
            is_healthy=False,
            last_check_time=datetime.now(),
            response_time_ms=0,
            error_message="Connection timeout",
            monitoring_method="socket"
        )
        
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_monitoring_event(
                self.node_config,
                unhealthy_status
            )
            
            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert 'UNHEALTHY' in args[0]
            assert 'Connection timeout' in args[0]
            assert kwargs['extra']['is_healthy'] is False
    
    def test_recovery_action_logging(self):
        """Test logging of recovery actions."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_recovery_action(
                self.node_config,
                self.recovery_result
            )
            
            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert 'Recovery action restart for broker-1: SUCCESS' in args[0]
            assert kwargs['extra']['component'] == 'recovery'
            assert kwargs['extra']['action_type'] == 'restart'
            assert kwargs['extra']['success'] is True
    
    def test_recovery_action_failed(self):
        """Test logging of failed recovery actions."""
        failed_result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=1,
            stdout="",
            stderr="Service failed to start",
            execution_time=datetime.now(),
            success=False
        )
        
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_recovery_action(
                self.node_config,
                failed_result
            )
            
            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert 'FAILED' in args[0]
            assert 'exit code: 1' in args[0]
            assert kwargs['extra']['success'] is False
    
    def test_notification_event_logging(self):
        """Test logging of notification events."""
        with patch.object(self.audit_logger.logger, 'info') as mock_info:
            self.audit_logger.log_notification_event(
                'failure_alert',
                'admin@example.com',
                'sent',
                message_id='12345'
            )
            
            mock_info.assert_called_once()
            args, kwargs = mock_info.call_args
            assert 'Notification failure_alert to admin@example.com: sent' in args[0]
            assert kwargs['extra']['component'] == 'notification'
            assert kwargs['extra']['notification_type'] == 'failure_alert'
            assert kwargs['extra']['recipient'] == 'admin@example.com'
            assert kwargs['extra']['delivery_status'] == 'sent'
            assert kwargs['extra']['message_id'] == '12345'


class TestLoggingService:
    """Test LoggingService class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = LogConfig(log_dir=self.temp_dir, console_logging=False)
        self.logging_service = LoggingService(self.config)
        
        # Sample test data
        self.node_config = NodeConfig(
            node_id="broker-1",
            node_type="kafka_broker",
            host="localhost",
            port=9092
        )
        
        self.node_status = NodeStatus(
            node_id="broker-1",
            is_healthy=True,
            last_check_time=datetime.now(),
            response_time_ms=150.5,
            monitoring_method="jmx"
        )
        
        self.recovery_result = RecoveryResult(
            node_id="broker-1",
            action_type="restart",
            command_executed="systemctl restart kafka",
            exit_code=0,
            stdout="Service restarted successfully",
            stderr="",
            execution_time=datetime.now(),
            success=True
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_initialization(self):
        """Test LoggingService initialization."""
        assert self.logging_service.log_config == self.config
        assert isinstance(self.logging_service.audit_logger, AuditLogger)
        assert isinstance(self.logging_service.rotator, LogRotator)
        assert self.logging_service.logger.name == 'kafka_self_healing'
    
    def test_get_logger(self):
        """Test getting component-specific loggers."""
        monitoring_logger = self.logging_service.get_logger('monitoring')
        recovery_logger = self.logging_service.get_logger('recovery')
        
        assert monitoring_logger.name == 'kafka_self_healing.monitoring'
        assert recovery_logger.name == 'kafka_self_healing.recovery'
    
    def test_monitoring_event_logging(self):
        """Test monitoring event logging."""
        with patch.object(self.logging_service.audit_logger, 'log_monitoring_event') as mock_audit:
            with patch.object(self.logging_service.logger, 'log') as mock_log:
                self.logging_service.log_monitoring_event(
                    self.node_config,
                    self.node_status
                )
                
                mock_audit.assert_called_once_with(self.node_config, self.node_status)
                mock_log.assert_called_once()
                args, kwargs = mock_log.call_args
                assert args[0] == logging.INFO  # log level
                assert 'broker-1' in args[1]
                assert 'OK' in args[1]
    
    def test_recovery_action_logging(self):
        """Test recovery action logging."""
        with patch.object(self.logging_service.audit_logger, 'log_recovery_action') as mock_audit:
            with patch.object(self.logging_service.logger, 'log') as mock_log:
                self.logging_service.log_recovery_action(
                    self.node_config,
                    'restart',
                    self.recovery_result
                )
                
                mock_audit.assert_called_once_with(self.node_config, self.recovery_result)
                mock_log.assert_called_once()
                args, kwargs = mock_log.call_args
                assert args[0] == logging.INFO  # log level
                assert 'restart' in args[1]
                assert 'completed' in args[1]
    
    def test_notification_event_logging(self):
        """Test notification event logging."""
        with patch.object(self.logging_service.audit_logger, 'log_notification_event') as mock_audit:
            with patch.object(self.logging_service.logger, 'log') as mock_log:
                self.logging_service.log_notification_event(
                    'failure_alert',
                    'admin@example.com',
                    'sent'
                )
                
                mock_audit.assert_called_once_with('failure_alert', 'admin@example.com', 'sent')
                mock_log.assert_called_once()
                args, kwargs = mock_log.call_args
                assert args[0] == logging.INFO  # log level
                assert 'failure_alert' in args[1]
                assert 'sent' in args[1]
    
    def test_system_startup_logging(self):
        """Test system startup logging."""
        config_summary = {'cluster_name': 'test-cluster', 'node_count': 3}
        
        with patch.object(self.logging_service.audit_logger, 'log_system_event') as mock_audit:
            with patch.object(self.logging_service.logger, 'info') as mock_info:
                self.logging_service.log_system_startup(config_summary)
                
                mock_audit.assert_called_once_with(
                    'startup',
                    'Kafka self-healing system started',
                    **config_summary
                )
                mock_info.assert_called_once()
    
    def test_system_shutdown_logging(self):
        """Test system shutdown logging."""
        with patch.object(self.logging_service.audit_logger, 'log_system_event') as mock_audit:
            with patch.object(self.logging_service.logger, 'info') as mock_info:
                self.logging_service.log_system_shutdown()
                
                mock_audit.assert_called_once_with(
                    'shutdown',
                    'Kafka self-healing system stopped'
                )
                mock_info.assert_called_once()
    
    def test_cleanup_old_logs(self):
        """Test cleanup of old logs."""
        with patch.object(self.logging_service.rotator, 'cleanup_old_logs') as mock_cleanup:
            with patch.object(self.logging_service.logger, 'info') as mock_info:
                self.logging_service.cleanup_old_logs(days_to_keep=15)
                
                mock_cleanup.assert_called_once_with(15)
                mock_info.assert_called_once()
    
    def test_credential_filtering_in_handlers(self):
        """Test that credential filtering is applied to handlers."""
        # Check that all handlers have credential filter
        for handler in self.logging_service.logger.handlers:
            filter_names = [f.__class__.__name__ for f in handler.filters]
            assert 'CredentialFilter' in filter_names
    
    def test_structured_logging_format(self):
        """Test structured logging format when enabled."""
        config = LogConfig(log_dir=self.temp_dir, structured_format=True)
        service = LoggingService(config)
        
        # Find the file handler
        file_handler = None
        for handler in service.logger.handlers:
            if hasattr(handler, 'baseFilename'):
                file_handler = handler
                break
        
        assert file_handler is not None
        assert isinstance(file_handler.formatter, StructuredFormatter)
    
    def test_console_logging_disabled(self):
        """Test that console logging can be disabled."""
        config = LogConfig(log_dir=self.temp_dir, console_logging=False)
        service = LoggingService(config)
        
        # Should only have file handler, no console handler
        handler_types = [type(h).__name__ for h in service.logger.handlers]
        assert 'StreamHandler' not in handler_types
        assert 'RotatingFileHandler' in handler_types


if __name__ == '__main__':
    pytest.main([__file__])