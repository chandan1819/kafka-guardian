"""
Kafka Guardian - Autonomous monitoring and self-healing system for Apache Kafka clusters.

This package provides intelligent monitoring, automated recovery, and comprehensive
alerting for Kafka brokers and Zookeeper nodes.
"""

__version__ = "1.0.0"
__author__ = "Chandan Kumar"
__email__ = "chandan1819@example.com"
__license__ = "MIT"
__description__ = "Autonomous monitoring and self-healing system for Apache Kafka clusters"

# Package metadata
__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "__description__",
]

# Import main components for easy access
try:
    from .main import SelfHealingSystem
    from .config import ConfigurationManager
    from .monitoring import MonitoringService
    from .recovery import RecoveryEngine
    from .notification import NotificationService
    from .models import NodeConfig, NodeStatus, RecoveryResult
    
    __all__.extend([
        "SelfHealingSystem",
        "ConfigurationManager", 
        "MonitoringService",
        "RecoveryEngine",
        "NotificationService",
        "NodeConfig",
        "NodeStatus", 
        "RecoveryResult",
    ])
    
except ImportError:
    # Handle import errors gracefully during package installation
    pass