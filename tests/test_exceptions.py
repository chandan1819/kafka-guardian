"""
Unit tests for custom exception classes.
"""

import pytest
from src.kafka_self_healing.exceptions import (
    KafkaSelfHealingError,
    ConfigurationError,
    MonitoringError,
    RecoveryError,
    NotificationError,
    PluginError,
    ValidationError
)


class TestExceptions:
    """Test cases for custom exception classes."""

    def test_base_exception(self):
        """Test base KafkaSelfHealingError exception."""
        error = KafkaSelfHealingError("Base error message")
        assert str(error) == "Base error message"
        assert isinstance(error, Exception)

    def test_configuration_error(self):
        """Test ConfigurationError inherits from base exception."""
        error = ConfigurationError("Configuration is invalid")
        assert str(error) == "Configuration is invalid"
        assert isinstance(error, KafkaSelfHealingError)
        assert isinstance(error, Exception)

    def test_monitoring_error(self):
        """Test MonitoringError inherits from base exception."""
        error = MonitoringError("Monitoring failed")
        assert str(error) == "Monitoring failed"
        assert isinstance(error, KafkaSelfHealingError)

    def test_recovery_error(self):
        """Test RecoveryError inherits from base exception."""
        error = RecoveryError("Recovery action failed")
        assert str(error) == "Recovery action failed"
        assert isinstance(error, KafkaSelfHealingError)

    def test_notification_error(self):
        """Test NotificationError inherits from base exception."""
        error = NotificationError("Failed to send notification")
        assert str(error) == "Failed to send notification"
        assert isinstance(error, KafkaSelfHealingError)

    def test_plugin_error(self):
        """Test PluginError inherits from base exception."""
        error = PluginError("Plugin loading failed")
        assert str(error) == "Plugin loading failed"
        assert isinstance(error, KafkaSelfHealingError)

    def test_validation_error(self):
        """Test ValidationError inherits from base exception."""
        error = ValidationError("Data validation failed")
        assert str(error) == "Data validation failed"
        assert isinstance(error, KafkaSelfHealingError)

    def test_exception_raising(self):
        """Test that exceptions can be raised and caught properly."""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Test configuration error")

        with pytest.raises(KafkaSelfHealingError):
            raise MonitoringError("Test monitoring error")

        # Test catching base exception
        try:
            raise ValidationError("Test validation error")
        except KafkaSelfHealingError as e:
            assert str(e) == "Test validation error"