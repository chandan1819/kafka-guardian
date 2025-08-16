"""
Configuration management for the Kafka self-healing system.
"""

import os
import re
import yaml
import json
import configparser
from pathlib import Path
from typing import Dict, Any, Optional, Union
from .models import ClusterConfig, RetryPolicy, NotificationConfig, NodeConfig, CredentialConfig
from .exceptions import ValidationError
from .credentials import CredentialManager, SecureCredentialStore


class ConfigurationManager:
    """Manages loading and validation of system configuration."""
    
    def __init__(self):
        self._config_data: Optional[Dict[str, Any]] = None
        self._cluster_config: Optional[ClusterConfig] = None
        self._notification_config: Optional[NotificationConfig] = None
        self._credential_manager: Optional[CredentialManager] = None
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from YAML, JSON, or INI file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Dictionary containing configuration data
            
        Raises:
            ValidationError: If file cannot be loaded or parsed
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise ValidationError(f"Configuration file not found: {config_path}")
        
        if not config_file.is_file():
            raise ValidationError(f"Configuration path is not a file: {config_path}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Substitute environment variables
            content = self._substitute_env_vars(content)
            
            # Parse based on file extension
            suffix = config_file.suffix.lower()
            if suffix in ['.yaml', '.yml']:
                config_data = yaml.safe_load(content)
            elif suffix == '.json':
                config_data = json.loads(content)
            elif suffix in ['.ini', '.cfg']:
                config_data = self._parse_ini_config(content)
            else:
                raise ValidationError(f"Unsupported configuration file format: {suffix}")
            
            if not isinstance(config_data, dict):
                raise ValidationError("Configuration file must contain a dictionary/object at root level")
            
            self._config_data = config_data
            return config_data
            
        except yaml.YAMLError as e:
            raise ValidationError(f"Failed to parse YAML configuration: {e}")
        except json.JSONDecodeError as e:
            raise ValidationError(f"Failed to parse JSON configuration: {e}")
        except configparser.Error as e:
            raise ValidationError(f"Failed to parse INI configuration: {e}")
        except Exception as e:
            raise ValidationError(f"Failed to load configuration file: {e}")
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate configuration structure and values.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            True if configuration is valid
            
        Raises:
            ValidationError: If configuration is invalid
        """
        if not isinstance(config, dict):
            raise ValidationError("Configuration must be a dictionary")
        
        # Validate required top-level sections
        required_sections = ['cluster', 'notification']
        for section in required_sections:
            if section not in config:
                raise ValidationError(f"Missing required configuration section: {section}")
        
        # Validate cluster configuration
        try:
            cluster_config = ClusterConfig.from_dict(config['cluster'])
            self._cluster_config = cluster_config
        except Exception as e:
            raise ValidationError(f"Invalid cluster configuration: {e}")
        
        # Validate notification configuration
        try:
            notification_config = NotificationConfig.from_dict(config['notification'])
            self._notification_config = notification_config
        except Exception as e:
            raise ValidationError(f"Invalid notification configuration: {e}")
        
        # Initialize credential manager
        try:
            self._initialize_credential_manager()
        except Exception as e:
            raise ValidationError(f"Failed to initialize credential manager: {e}")
        
        return True
    
    def get_cluster_config(self) -> ClusterConfig:
        """
        Get cluster configuration.
        
        Returns:
            ClusterConfig instance
            
        Raises:
            ValidationError: If configuration not loaded or invalid
        """
        if self._cluster_config is None:
            raise ValidationError("Configuration not loaded or cluster config not found")
        return self._cluster_config
    
    def get_notification_config(self) -> NotificationConfig:
        """
        Get notification configuration.
        
        Returns:
            NotificationConfig instance
            
        Raises:
            ValidationError: If configuration not loaded or invalid
        """
        if self._notification_config is None:
            raise ValidationError("Configuration not loaded or notification config not found")
        return self._notification_config
    
    def get_retry_policy(self) -> RetryPolicy:
        """
        Get default retry policy from cluster configuration.
        
        Returns:
            RetryPolicy instance
            
        Raises:
            ValidationError: If configuration not loaded
        """
        cluster_config = self.get_cluster_config()
        return cluster_config.default_retry_policy
    
    def get_credential_manager(self) -> CredentialManager:
        """
        Get credential manager instance.
        
        Returns:
            CredentialManager instance
            
        Raises:
            ValidationError: If credential manager not initialized
        """
        if self._credential_manager is None:
            raise ValidationError("Credential manager not initialized")
        return self._credential_manager
    
    def _initialize_credential_manager(self) -> None:
        """Initialize credential manager based on configuration."""
        if self._cluster_config is None:
            raise ValidationError("Cluster configuration not loaded")
        
        credential_config = self._cluster_config.credential_config
        
        # Create credential store
        store_config = {
            'file_path': credential_config.file_path,
            'encrypted': credential_config.encrypted,
            'prefix': credential_config.env_prefix
        }
        
        if credential_config.encrypted and credential_config.encryption_key_env:
            encryption_key_b64 = os.environ.get(credential_config.encryption_key_env)
            if encryption_key_b64:
                import base64
                store_config['encryption_key'] = base64.urlsafe_b64decode(encryption_key_b64)
        
        credential_store = SecureCredentialStore(credential_config.store_type, **store_config)
        credential_store.initialize()
        
        self._credential_manager = credential_store.get_credential_manager()
    
    def _substitute_env_vars(self, content: str) -> str:
        """
        Substitute environment variables in configuration content.
        
        Supports ${VAR_NAME} and ${VAR_NAME:default_value} syntax.
        
        Args:
            content: Configuration file content
            
        Returns:
            Content with environment variables substituted
        """
        def replace_env_var(match):
            var_expr = match.group(1)
            if ':' in var_expr:
                var_name, default_value = var_expr.split(':', 1)
            else:
                var_name, default_value = var_expr, ''
            
            return os.environ.get(var_name, default_value)
        
        # Pattern matches ${VAR_NAME} or ${VAR_NAME:default}
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, replace_env_var, content)
    
    def _parse_ini_config(self, content: str) -> Dict[str, Any]:
        """
        Parse INI configuration content into nested dictionary.
        
        Args:
            content: INI file content
            
        Returns:
            Nested dictionary representation of INI config
        """
        parser = configparser.ConfigParser()
        parser.read_string(content)
        
        config = {}
        for section_name in parser.sections():
            section = {}
            for key, value in parser.items(section_name):
                # Try to parse as JSON for complex values
                try:
                    section[key] = json.loads(value)
                except json.JSONDecodeError:
                    # Handle boolean values
                    if value.lower() in ('true', 'yes', '1', 'on'):
                        section[key] = True
                    elif value.lower() in ('false', 'no', '0', 'off'):
                        section[key] = False
                    else:
                        # Try to parse as number
                        try:
                            if '.' in value:
                                section[key] = float(value)
                            else:
                                section[key] = int(value)
                        except ValueError:
                            # Keep as string
                            section[key] = value
            
            config[section_name] = section
        
        return config