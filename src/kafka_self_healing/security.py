"""
Security and authentication utilities for Kafka and Zookeeper connections.
"""

import ssl
import socket
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from .models import SecurityConfig
from .credentials import CredentialManager
from .exceptions import ValidationError


class SSLContextManager:
    """Manages SSL context creation for secure connections."""
    
    def __init__(self, credential_manager: CredentialManager):
        """
        Initialize SSL context manager.
        
        Args:
            credential_manager: Credential manager instance
        """
        self.credential_manager = credential_manager
    
    def create_ssl_context(self, security_config: SecurityConfig, 
                          service_type: str = "kafka") -> ssl.SSLContext:
        """
        Create SSL context for secure connections.
        
        Args:
            security_config: Security configuration
            service_type: Service type ('kafka' or 'zookeeper')
            
        Returns:
            Configured SSL context
            
        Raises:
            ValidationError: If SSL configuration is invalid
        """
        if not security_config.enable_ssl:
            raise ValidationError("SSL is not enabled in security configuration")
        
        # Create SSL context
        context = ssl.create_default_context()
        
        # Configure hostname verification
        if not security_config.ssl_verify_hostname:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        # Load CA certificate if provided
        if security_config.ssl_ca_cert_path:
            ca_cert_path = Path(security_config.ssl_ca_cert_path)
            if not ca_cert_path.exists():
                raise ValidationError(f"CA certificate file not found: {security_config.ssl_ca_cert_path}")
            context.load_verify_locations(cafile=str(ca_cert_path))
        
        # Load client certificate and key if provided
        if security_config.ssl_cert_path and security_config.ssl_key_path:
            cert_path = Path(security_config.ssl_cert_path)
            key_path = Path(security_config.ssl_key_path)
            
            if not cert_path.exists():
                raise ValidationError(f"Client certificate file not found: {security_config.ssl_cert_path}")
            if not key_path.exists():
                raise ValidationError(f"Client key file not found: {security_config.ssl_key_path}")
            
            # Get key password from credentials if needed
            key_password = security_config.ssl_key_password
            if not key_password:
                key_password = self.credential_manager.get_credential(f"{service_type.upper()}_SSL_KEY_PASSWORD")
            
            context.load_cert_chain(
                certfile=str(cert_path),
                keyfile=str(key_path),
                password=key_password
            )
        
        return context
    
    def create_kafka_ssl_context(self, security_config: SecurityConfig) -> ssl.SSLContext:
        """
        Create SSL context specifically for Kafka connections.
        
        Args:
            security_config: Security configuration
            
        Returns:
            Configured SSL context for Kafka
        """
        return self.create_ssl_context(security_config, "kafka")
    
    def create_zookeeper_ssl_context(self, security_config: SecurityConfig) -> ssl.SSLContext:
        """
        Create SSL context specifically for Zookeeper connections.
        
        Args:
            security_config: Security configuration
            
        Returns:
            Configured SSL context for Zookeeper
        """
        return self.create_ssl_context(security_config, "zookeeper")


class SASLAuthenticator:
    """Handles SASL authentication for Kafka and Zookeeper."""
    
    def __init__(self, credential_manager: CredentialManager):
        """
        Initialize SASL authenticator.
        
        Args:
            credential_manager: Credential manager instance
        """
        self.credential_manager = credential_manager
    
    def get_kafka_sasl_config(self, security_config: SecurityConfig) -> Dict[str, Any]:
        """
        Get SASL configuration for Kafka connections.
        
        Args:
            security_config: Security configuration
            
        Returns:
            Dictionary containing SASL configuration
            
        Raises:
            ValidationError: If SASL configuration is invalid
        """
        if not security_config.enable_sasl:
            return {}
        
        kafka_credentials = self.credential_manager.get_kafka_credentials()
        
        if 'sasl' not in kafka_credentials:
            raise ValidationError("SASL credentials not found for Kafka")
        
        sasl_creds = kafka_credentials['sasl']
        
        config = {
            'sasl_mechanism': security_config.sasl_mechanism,
            'sasl_plain_username': sasl_creds.get('username'),
            'sasl_plain_password': sasl_creds.get('password')
        }
        
        # Validate required fields
        if not config['sasl_plain_username'] or not config['sasl_plain_password']:
            raise ValidationError("SASL username and password are required")
        
        # Add mechanism-specific configuration
        if security_config.sasl_mechanism in ['SCRAM-SHA-256', 'SCRAM-SHA-512']:
            config['sasl_mechanism'] = security_config.sasl_mechanism
        elif security_config.sasl_mechanism == 'GSSAPI':
            # Kerberos configuration would go here
            config['sasl_kerberos_service_name'] = 'kafka'
        
        return config
    
    def get_zookeeper_sasl_config(self, security_config: SecurityConfig) -> Dict[str, Any]:
        """
        Get SASL configuration for Zookeeper connections.
        
        Args:
            security_config: Security configuration
            
        Returns:
            Dictionary containing SASL configuration
            
        Raises:
            ValidationError: If SASL configuration is invalid
        """
        if not security_config.enable_sasl:
            return {}
        
        zk_credentials = self.credential_manager.get_zookeeper_credentials()
        
        if 'sasl' not in zk_credentials:
            raise ValidationError("SASL credentials not found for Zookeeper")
        
        sasl_creds = zk_credentials['sasl']
        
        config = {
            'username': sasl_creds.get('username'),
            'password': sasl_creds.get('password')
        }
        
        # Validate required fields
        if not config['username'] or not config['password']:
            raise ValidationError("SASL username and password are required for Zookeeper")
        
        return config


class SecureConnectionManager:
    """Manages secure connections to Kafka and Zookeeper."""
    
    def __init__(self, credential_manager: CredentialManager):
        """
        Initialize secure connection manager.
        
        Args:
            credential_manager: Credential manager instance
        """
        self.credential_manager = credential_manager
        self.ssl_context_manager = SSLContextManager(credential_manager)
        self.sasl_authenticator = SASLAuthenticator(credential_manager)
    
    def create_secure_socket(self, host: str, port: int, 
                           security_config: SecurityConfig,
                           service_type: str = "kafka") -> socket.socket:
        """
        Create a secure socket connection.
        
        Args:
            host: Target host
            port: Target port
            security_config: Security configuration
            service_type: Service type ('kafka' or 'zookeeper')
            
        Returns:
            Configured socket (SSL-wrapped if SSL is enabled)
            
        Raises:
            ValidationError: If connection cannot be established
        """
        try:
            # Create base socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)  # 30 second timeout
            
            if security_config.enable_ssl:
                # Wrap with SSL
                ssl_context = self.ssl_context_manager.create_ssl_context(
                    security_config, service_type
                )
                sock = ssl_context.wrap_socket(sock, server_hostname=host)
            
            # Connect to the server
            sock.connect((host, port))
            
            return sock
            
        except Exception as e:
            if 'sock' in locals():
                sock.close()
            raise ValidationError(f"Failed to create secure connection to {host}:{port}: {e}")
    
    def get_kafka_connection_config(self, security_config: SecurityConfig) -> Dict[str, Any]:
        """
        Get complete connection configuration for Kafka.
        
        Args:
            security_config: Security configuration
            
        Returns:
            Dictionary containing all connection parameters
        """
        config = {}
        
        # SSL configuration
        if security_config.enable_ssl:
            ssl_context = self.ssl_context_manager.create_kafka_ssl_context(security_config)
            config.update({
                'security_protocol': 'SSL' if not security_config.enable_sasl else 'SASL_SSL',
                'ssl_context': ssl_context,
                'ssl_check_hostname': security_config.ssl_verify_hostname,
                'ssl_cafile': security_config.ssl_ca_cert_path,
                'ssl_certfile': security_config.ssl_cert_path,
                'ssl_keyfile': security_config.ssl_key_path
            })
        else:
            config['security_protocol'] = 'SASL_PLAINTEXT' if security_config.enable_sasl else 'PLAINTEXT'
        
        # SASL configuration
        if security_config.enable_sasl:
            sasl_config = self.sasl_authenticator.get_kafka_sasl_config(security_config)
            config.update(sasl_config)
        
        return config
    
    def get_zookeeper_connection_config(self, security_config: SecurityConfig) -> Dict[str, Any]:
        """
        Get complete connection configuration for Zookeeper.
        
        Args:
            security_config: Security configuration
            
        Returns:
            Dictionary containing all connection parameters
        """
        config = {}
        
        # SSL configuration
        if security_config.enable_ssl:
            ssl_context = self.ssl_context_manager.create_zookeeper_ssl_context(security_config)
            config.update({
                'use_ssl': True,
                'ssl_context': ssl_context,
                'ssl_check_hostname': security_config.ssl_verify_hostname
            })
        
        # SASL configuration
        if security_config.enable_sasl:
            sasl_config = self.sasl_authenticator.get_zookeeper_sasl_config(security_config)
            config.update(sasl_config)
        
        return config
    
    def test_connection(self, host: str, port: int, 
                       security_config: SecurityConfig,
                       service_type: str = "kafka") -> Tuple[bool, Optional[str]]:
        """
        Test a secure connection to verify configuration.
        
        Args:
            host: Target host
            port: Target port
            security_config: Security configuration
            service_type: Service type ('kafka' or 'zookeeper')
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            sock = self.create_secure_socket(host, port, security_config, service_type)
            sock.close()
            return True, None
        except Exception as e:
            return False, str(e)


class CredentialFilter:
    """Filters sensitive information from logs and outputs."""
    
    SENSITIVE_KEYS = {
        'password', 'passwd', 'pwd', 'secret', 'key', 'token', 'auth',
        'sasl_plain_password', 'ssl_key_password', 'keystore_password',
        'truststore_password', 'smtp_password'
    }
    
    @classmethod
    def filter_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive information from a dictionary.
        
        Args:
            data: Dictionary to filter
            
        Returns:
            Dictionary with sensitive values masked
        """
        filtered = {}
        
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in cls.SENSITIVE_KEYS):
                filtered[key] = "***MASKED***"
            elif isinstance(value, dict):
                filtered[key] = cls.filter_dict(value)
            elif isinstance(value, list):
                filtered[key] = [cls.filter_dict(item) if isinstance(item, dict) else item 
                               for item in value]
            else:
                filtered[key] = value
        
        return filtered
    
    @classmethod
    def filter_string(cls, text: str) -> str:
        """
        Filter sensitive information from a string.
        
        Args:
            text: String to filter
            
        Returns:
            String with sensitive patterns masked
        """
        import re
        
        # Pattern to match key=value pairs with sensitive keys
        pattern = r'(\b(?:' + '|'.join(cls.SENSITIVE_KEYS) + r')\s*[=:]\s*)([^\s,;]+)'
        
        def replace_sensitive(match):
            return match.group(1) + "***MASKED***"
        
        return re.sub(pattern, replace_sensitive, text, flags=re.IGNORECASE)
    
    @classmethod
    def filter_command_args(cls, args: list) -> list:
        """
        Filter sensitive information from command arguments.
        
        Args:
            args: List of command arguments
            
        Returns:
            List with sensitive arguments masked
        """
        filtered_args = []
        mask_next = False
        
        for arg in args:
            if mask_next:
                filtered_args.append("***MASKED***")
                mask_next = False
            elif any(f"--{sensitive}" in arg.lower() or f"-{sensitive}" in arg.lower() 
                    for sensitive in cls.SENSITIVE_KEYS):
                if '=' in arg:
                    # Format: --password=value
                    key, _ = arg.split('=', 1)
                    filtered_args.append(f"{key}=***MASKED***")
                else:
                    # Format: --password value (next arg is the value)
                    filtered_args.append(arg)
                    mask_next = True
            else:
                filtered_args.append(arg)
        
        return filtered_args