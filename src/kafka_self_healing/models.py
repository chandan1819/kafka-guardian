"""
Core data models for the Kafka self-healing system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import json
from .exceptions import ValidationError


@dataclass
class RetryPolicy:
    """Configuration for retry behavior in recovery operations."""
    max_attempts: int = 3
    initial_delay_seconds: int = 30
    backoff_multiplier: float = 2.0
    max_delay_seconds: int = 300

    def __post_init__(self):
        """Validate retry policy parameters."""
        if self.max_attempts < 1:
            raise ValidationError("max_attempts must be at least 1")
        if self.initial_delay_seconds < 0:
            raise ValidationError("initial_delay_seconds must be non-negative")
        if self.backoff_multiplier < 1.0:
            raise ValidationError("backoff_multiplier must be at least 1.0")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValidationError("max_delay_seconds must be >= initial_delay_seconds")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'max_attempts': self.max_attempts,
            'initial_delay_seconds': self.initial_delay_seconds,
            'backoff_multiplier': self.backoff_multiplier,
            'max_delay_seconds': self.max_delay_seconds
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RetryPolicy':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class SecurityConfig:
    """Configuration for security settings."""
    enable_ssl: bool = False
    ssl_verify_hostname: bool = True
    ssl_ca_cert_path: Optional[str] = None
    ssl_cert_path: Optional[str] = None
    ssl_key_path: Optional[str] = None
    ssl_key_password: Optional[str] = None
    enable_sasl: bool = False
    sasl_mechanism: str = "PLAIN"  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512, GSSAPI
    
    def __post_init__(self):
        """Validate security configuration parameters."""
        valid_sasl_mechanisms = ['PLAIN', 'SCRAM-SHA-256', 'SCRAM-SHA-512', 'GSSAPI']
        if self.sasl_mechanism not in valid_sasl_mechanisms:
            raise ValidationError(f"sasl_mechanism must be one of: {valid_sasl_mechanisms}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'enable_ssl': self.enable_ssl,
            'ssl_verify_hostname': self.ssl_verify_hostname,
            'ssl_ca_cert_path': self.ssl_ca_cert_path,
            'ssl_cert_path': self.ssl_cert_path,
            'ssl_key_path': self.ssl_key_path,
            'ssl_key_password': self.ssl_key_password,
            'enable_sasl': self.enable_sasl,
            'sasl_mechanism': self.sasl_mechanism
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SecurityConfig':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class CredentialConfig:
    """Configuration for credential management."""
    store_type: str = "env"  # 'env', 'file', 'vault'
    file_path: Optional[str] = None
    encrypted: bool = False
    encryption_key_env: str = "CREDENTIAL_ENCRYPTION_KEY"
    env_prefix: str = ""
    
    def __post_init__(self):
        """Validate credential configuration parameters."""
        if self.store_type not in ['env', 'file', 'vault']:
            raise ValidationError("store_type must be 'env', 'file', or 'vault'")
        
        if self.store_type == 'file' and not self.file_path:
            raise ValidationError("file_path is required when store_type is 'file'")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'store_type': self.store_type,
            'file_path': self.file_path,
            'encrypted': self.encrypted,
            'encryption_key_env': self.encryption_key_env,
            'env_prefix': self.env_prefix
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CredentialConfig':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class NodeConfig:
    """Configuration for a Kafka broker or Zookeeper node."""
    node_id: str
    node_type: str  # 'kafka_broker' or 'zookeeper'
    host: str
    port: int
    jmx_port: Optional[int] = None
    monitoring_methods: List[str] = field(default_factory=list)
    recovery_actions: List[str] = field(default_factory=list)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    security_config: SecurityConfig = field(default_factory=SecurityConfig)

    def __post_init__(self):
        """Validate node configuration parameters."""
        if not self.node_id:
            raise ValidationError("node_id cannot be empty")
        if self.node_type not in ['kafka_broker', 'zookeeper']:
            raise ValidationError("node_type must be 'kafka_broker' or 'zookeeper'")
        if not self.host:
            raise ValidationError("host cannot be empty")
        if not (1 <= self.port <= 65535):
            raise ValidationError("port must be between 1 and 65535")
        if self.jmx_port is not None and not (1 <= self.jmx_port <= 65535):
            raise ValidationError("jmx_port must be between 1 and 65535")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'node_id': self.node_id,
            'node_type': self.node_type,
            'host': self.host,
            'port': self.port,
            'jmx_port': self.jmx_port,
            'monitoring_methods': self.monitoring_methods,
            'recovery_actions': self.recovery_actions,
            'retry_policy': self.retry_policy.to_dict(),
            'security_config': self.security_config.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NodeConfig':
        """Create instance from dictionary."""
        data = data.copy()
        retry_policy_data = data.pop('retry_policy', {})
        retry_policy = RetryPolicy.from_dict(retry_policy_data)
        
        security_config_data = data.pop('security_config', {})
        security_config = SecurityConfig.from_dict(security_config_data)
        
        return cls(retry_policy=retry_policy, security_config=security_config, **data)


@dataclass
class NodeStatus:
    """Health status information for a monitored node."""
    node_id: str
    is_healthy: bool
    last_check_time: datetime
    response_time_ms: float
    error_message: Optional[str] = None
    monitoring_method: str = ""

    def __post_init__(self):
        """Validate node status parameters."""
        if not self.node_id:
            raise ValidationError("node_id cannot be empty")
        if self.response_time_ms < 0:
            raise ValidationError("response_time_ms must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'node_id': self.node_id,
            'is_healthy': self.is_healthy,
            'last_check_time': self.last_check_time.isoformat(),
            'response_time_ms': self.response_time_ms,
            'error_message': self.error_message,
            'monitoring_method': self.monitoring_method
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NodeStatus':
        """Create instance from dictionary."""
        data = data.copy()
        data['last_check_time'] = datetime.fromisoformat(data['last_check_time'])
        return cls(**data)


@dataclass
class RecoveryResult:
    """Result of a recovery action execution."""
    node_id: str
    action_type: str
    command_executed: str
    exit_code: int
    stdout: str
    stderr: str
    execution_time: datetime
    success: bool

    def __post_init__(self):
        """Validate recovery result parameters."""
        if not self.node_id:
            raise ValidationError("node_id cannot be empty")
        if not self.action_type:
            raise ValidationError("action_type cannot be empty")
        if not self.command_executed:
            raise ValidationError("command_executed cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'node_id': self.node_id,
            'action_type': self.action_type,
            'command_executed': self.command_executed,
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
            'execution_time': self.execution_time.isoformat(),
            'success': self.success
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RecoveryResult':
        """Create instance from dictionary."""
        data = data.copy()
        data['execution_time'] = datetime.fromisoformat(data['execution_time'])
        return cls(**data)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'RecoveryResult':
        """Create instance from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class NotificationConfig:
    """Configuration for notification settings."""
    smtp_host: str
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    use_tls: bool = True
    use_ssl: bool = False
    sender_email: str = ""
    recipients: List[str] = field(default_factory=list)
    subject_prefix: str = "[Kafka Self-Healing]"

    def __post_init__(self):
        """Validate notification configuration parameters."""
        if not self.smtp_host:
            raise ValidationError("smtp_host cannot be empty")
        if not (1 <= self.smtp_port <= 65535):
            raise ValidationError("smtp_port must be between 1 and 65535")
        if not self.sender_email:
            raise ValidationError("sender_email cannot be empty")
        if not self.recipients:
            raise ValidationError("recipients list cannot be empty")
        if self.use_tls and self.use_ssl:
            raise ValidationError("use_tls and use_ssl cannot both be True")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'smtp_host': self.smtp_host,
            'smtp_port': self.smtp_port,
            'smtp_username': self.smtp_username,
            'smtp_password': self.smtp_password,
            'use_tls': self.use_tls,
            'use_ssl': self.use_ssl,
            'sender_email': self.sender_email,
            'recipients': self.recipients,
            'subject_prefix': self.subject_prefix
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NotificationConfig':
        """Create instance from dictionary."""
        return cls(**data)


@dataclass
class ClusterConfig:
    """Configuration for Kafka cluster topology."""
    cluster_name: str
    nodes: List[NodeConfig] = field(default_factory=list)
    monitoring_interval_seconds: int = 30
    default_retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    credential_config: CredentialConfig = field(default_factory=CredentialConfig)

    def __post_init__(self):
        """Validate cluster configuration parameters."""
        if not self.cluster_name:
            raise ValidationError("cluster_name cannot be empty")
        if self.monitoring_interval_seconds < 1:
            raise ValidationError("monitoring_interval_seconds must be at least 1")
        if not self.nodes:
            raise ValidationError("nodes list cannot be empty")
        
        # Validate unique node IDs
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValidationError("node_id values must be unique")

    def get_kafka_brokers(self) -> List[NodeConfig]:
        """Get all Kafka broker nodes."""
        return [node for node in self.nodes if node.node_type == 'kafka_broker']

    def get_zookeeper_nodes(self) -> List[NodeConfig]:
        """Get all Zookeeper nodes."""
        return [node for node in self.nodes if node.node_type == 'zookeeper']

    def get_node_by_id(self, node_id: str) -> Optional[NodeConfig]:
        """Get node by ID."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'cluster_name': self.cluster_name,
            'nodes': [node.to_dict() for node in self.nodes],
            'monitoring_interval_seconds': self.monitoring_interval_seconds,
            'default_retry_policy': self.default_retry_policy.to_dict(),
            'credential_config': self.credential_config.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ClusterConfig':
        """Create instance from dictionary."""
        data = data.copy()
        nodes_data = data.pop('nodes', [])
        nodes = [NodeConfig.from_dict(node_data) for node_data in nodes_data]
        
        retry_policy_data = data.pop('default_retry_policy', {})
        default_retry_policy = RetryPolicy.from_dict(retry_policy_data)
        
        credential_config_data = data.pop('credential_config', {})
        credential_config = CredentialConfig.from_dict(credential_config_data)
        
        return cls(nodes=nodes, default_retry_policy=default_retry_policy, 
                  credential_config=credential_config, **data)