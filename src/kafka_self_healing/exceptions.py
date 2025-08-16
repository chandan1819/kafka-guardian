"""
Custom exception classes for the Kafka self-healing system.
"""


class KafkaSelfHealingError(Exception):
    """Base exception class for all Kafka self-healing system errors."""
    pass


class ConfigurationError(KafkaSelfHealingError):
    """Raised when configuration is invalid or missing."""
    pass


class MonitoringError(KafkaSelfHealingError):
    """Raised when monitoring operations fail."""
    pass


class RecoveryError(KafkaSelfHealingError):
    """Raised when recovery operations fail."""
    pass


class NotificationError(KafkaSelfHealingError):
    """Raised when notification operations fail."""
    pass


class PluginError(KafkaSelfHealingError):
    """Raised when plugin operations fail."""
    pass


class PluginLoadError(PluginError):
    """Raised when plugin loading fails."""
    pass


class PluginValidationError(PluginError):
    """Raised when plugin validation fails."""
    pass


class ValidationError(KafkaSelfHealingError):
    """Raised when data validation fails."""
    pass


class SystemError(KafkaSelfHealingError):
    """Raised when system-level operations fail."""
    pass