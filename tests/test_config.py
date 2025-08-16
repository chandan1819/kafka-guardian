"""
Unit tests for configuration management system.
"""

import os
import json
import yaml
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from kafka_self_healing.config import ConfigurationManager
from kafka_self_healing.models import ClusterConfig, NotificationConfig, NodeConfig, RetryPolicy
from kafka_self_healing.exceptions import ValidationError


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config_manager = ConfigurationManager()
        self.sample_config = {
            'cluster': {
                'cluster_name': 'test-cluster',
                'monitoring_interval_seconds': 30,
                'default_retry_policy': {
                    'max_attempts': 3,
                    'initial_delay_seconds': 30,
                    'backoff_multiplier': 2.0,
                    'max_delay_seconds': 300
                },
                'nodes': [
                    {
                        'node_id': 'kafka-1',
                        'node_type': 'kafka_broker',
                        'host': 'kafka1.example.com',
                        'port': 9092,
                        'jmx_port': 9999,
                        'monitoring_methods': ['jmx', 'socket'],
                        'recovery_actions': ['restart_service']
                    },
                    {
                        'node_id': 'zk-1',
                        'node_type': 'zookeeper',
                        'host': 'zk1.example.com',
                        'port': 2181,
                        'monitoring_methods': ['socket', 'cli'],
                        'recovery_actions': ['restart_service']
                    }
                ]
            },
            'notification': {
                'smtp_host': 'smtp.example.com',
                'smtp_port': 587,
                'smtp_username': 'alerts@example.com',
                'smtp_password': 'secret123',
                'use_tls': True,
                'sender_email': 'alerts@example.com',
                'recipients': ['admin@example.com', 'ops@example.com'],
                'subject_prefix': '[Kafka Self-Healing]'
            }
        }
    
    def test_load_yaml_config(self):
        """Test loading YAML configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.sample_config, f)
            temp_path = f.name
        
        try:
            config = self.config_manager.load_config(temp_path)
            assert config == self.sample_config
        finally:
            os.unlink(temp_path)
    
    def test_load_json_config(self):
        """Test loading JSON configuration file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_config, f)
            temp_path = f.name
        
        try:
            config = self.config_manager.load_config(temp_path)
            assert config == self.sample_config
        finally:
            os.unlink(temp_path)
    
    def test_load_ini_config(self):
        """Test loading INI configuration file."""
        ini_content = """
[cluster]
cluster_name = test-cluster
monitoring_interval_seconds = 30
nodes = [{"node_id": "kafka-1", "node_type": "kafka_broker", "host": "kafka1.example.com", "port": 9092}]

[notification]
smtp_host = smtp.example.com
smtp_port = 587
use_tls = true
sender_email = alerts@example.com
recipients = ["admin@example.com"]
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write(ini_content)
            temp_path = f.name
        
        try:
            config = self.config_manager.load_config(temp_path)
            assert config['cluster']['cluster_name'] == 'test-cluster'
            assert config['cluster']['monitoring_interval_seconds'] == 30
            assert config['notification']['smtp_host'] == 'smtp.example.com'
            assert config['notification']['use_tls'] is True
        finally:
            os.unlink(temp_path)
    
    def test_environment_variable_substitution(self):
        """Test environment variable substitution in configuration."""
        config_with_env = {
            'cluster': {
                'cluster_name': '${CLUSTER_NAME:default-cluster}',
                'monitoring_interval_seconds': 30,
                'nodes': []
            },
            'notification': {
                'smtp_host': '${SMTP_HOST}',
                'smtp_password': '${SMTP_PASSWORD:default-password}',
                'sender_email': 'alerts@example.com',
                'recipients': ['admin@example.com']
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_with_env, f)
            temp_path = f.name
        
        try:
            with patch.dict(os.environ, {'SMTP_HOST': 'smtp.test.com', 'CLUSTER_NAME': 'prod-cluster'}):
                config = self.config_manager.load_config(temp_path)
                assert config['cluster']['cluster_name'] == 'prod-cluster'
                assert config['notification']['smtp_host'] == 'smtp.test.com'
                assert config['notification']['smtp_password'] == 'default-password'
        finally:
            os.unlink(temp_path)
    
    def test_load_nonexistent_file(self):
        """Test loading non-existent configuration file."""
        with pytest.raises(ValidationError, match="Configuration file not found"):
            self.config_manager.load_config('/nonexistent/config.yaml')
    
    def test_load_unsupported_format(self):
        """Test loading unsupported file format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("some content")
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="Unsupported configuration file format"):
                self.config_manager.load_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_validate_valid_config(self):
        """Test validation of valid configuration."""
        assert self.config_manager.validate_config(self.sample_config) is True
        
        # Verify that cluster and notification configs are created
        cluster_config = self.config_manager.get_cluster_config()
        assert cluster_config.cluster_name == 'test-cluster'
        assert len(cluster_config.nodes) == 2
        
        notification_config = self.config_manager.get_notification_config()
        assert notification_config.smtp_host == 'smtp.example.com'
        assert len(notification_config.recipients) == 2
    
    def test_validate_missing_cluster_section(self):
        """Test validation with missing cluster section."""
        invalid_config = {
            'notification': self.sample_config['notification']
        }
        
        with pytest.raises(ValidationError, match="Missing required configuration section: cluster"):
            self.config_manager.validate_config(invalid_config)
    
    def test_validate_missing_notification_section(self):
        """Test validation with missing notification section."""
        invalid_config = {
            'cluster': self.sample_config['cluster']
        }
        
        with pytest.raises(ValidationError, match="Missing required configuration section: notification"):
            self.config_manager.validate_config(invalid_config)
    
    def test_validate_invalid_cluster_config(self):
        """Test validation with invalid cluster configuration."""
        invalid_config = {
            'cluster': {
                'cluster_name': '',  # Invalid empty name
                'nodes': []
            },
            'notification': self.sample_config['notification']
        }
        
        with pytest.raises(ValidationError, match="Invalid cluster configuration"):
            self.config_manager.validate_config(invalid_config)
    
    def test_validate_invalid_notification_config(self):
        """Test validation with invalid notification configuration."""
        invalid_config = {
            'cluster': self.sample_config['cluster'],
            'notification': {
                'smtp_host': '',  # Invalid empty host
                'sender_email': 'test@example.com',
                'recipients': ['admin@example.com']
            }
        }
        
        with pytest.raises(ValidationError, match="Invalid notification configuration"):
            self.config_manager.validate_config(invalid_config)
    
    def test_validate_non_dict_config(self):
        """Test validation with non-dictionary configuration."""
        with pytest.raises(ValidationError, match="Configuration must be a dictionary"):
            self.config_manager.validate_config("not a dict")
    
    def test_get_cluster_config_before_validation(self):
        """Test getting cluster config before validation."""
        with pytest.raises(ValidationError, match="Configuration not loaded or cluster config not found"):
            self.config_manager.get_cluster_config()
    
    def test_get_notification_config_before_validation(self):
        """Test getting notification config before validation."""
        with pytest.raises(ValidationError, match="Configuration not loaded or notification config not found"):
            self.config_manager.get_notification_config()
    
    def test_get_retry_policy(self):
        """Test getting retry policy from cluster configuration."""
        self.config_manager.validate_config(self.sample_config)
        retry_policy = self.config_manager.get_retry_policy()
        
        assert retry_policy.max_attempts == 3
        assert retry_policy.initial_delay_seconds == 30
        assert retry_policy.backoff_multiplier == 2.0
        assert retry_policy.max_delay_seconds == 300
    
    def test_load_invalid_yaml(self):
        """Test loading invalid YAML file."""
        invalid_yaml = "invalid: yaml: content: ["
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="Failed to parse YAML configuration"):
                self.config_manager.load_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_invalid_json(self):
        """Test loading invalid JSON file."""
        invalid_json = '{"invalid": json, "content"}'
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(invalid_json)
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="Failed to parse JSON configuration"):
                self.config_manager.load_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_non_dict_root(self):
        """Test loading configuration with non-dict root."""
        non_dict_config = ["not", "a", "dict"]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(non_dict_config, f)
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="Configuration file must contain a dictionary/object at root level"):
                self.config_manager.load_config(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_environment_variable_substitution_missing_var(self):
        """Test environment variable substitution with missing variable."""
        config_with_env = {
            'cluster': {
                'cluster_name': '${MISSING_VAR}',
                'monitoring_interval_seconds': 30,
                'nodes': []
            },
            'notification': {
                'smtp_host': 'smtp.example.com',
                'sender_email': 'alerts@example.com',
                'recipients': ['admin@example.com']
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_with_env, f)
            temp_path = f.name
        
        try:
            config = self.config_manager.load_config(temp_path)
            # Missing env var should result in empty string, but YAML may interpret as None
            assert config['cluster']['cluster_name'] in ('', None)
        finally:
            os.unlink(temp_path)
    
    def test_ini_config_with_complex_values(self):
        """Test INI configuration with complex JSON values."""
        ini_content = """
[cluster]
cluster_name = test-cluster
monitoring_interval_seconds = 30
default_retry_policy = {"max_attempts": 5, "initial_delay_seconds": 60}
nodes = [{"node_id": "kafka-1", "node_type": "kafka_broker", "host": "kafka1.example.com", "port": 9092}]

[notification]
smtp_host = smtp.example.com
smtp_port = 587
use_tls = true
use_ssl = false
sender_email = alerts@example.com
recipients = ["admin@example.com", "ops@example.com"]
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write(ini_content)
            temp_path = f.name
        
        try:
            config = self.config_manager.load_config(temp_path)
            assert config['cluster']['cluster_name'] == 'test-cluster'
            assert config['cluster']['monitoring_interval_seconds'] == 30
            assert isinstance(config['cluster']['default_retry_policy'], dict)
            assert config['cluster']['default_retry_policy']['max_attempts'] == 5
            assert isinstance(config['cluster']['nodes'], list)
            assert len(config['cluster']['nodes']) == 1
            assert config['notification']['use_tls'] is True
            assert config['notification']['use_ssl'] is False
            assert isinstance(config['notification']['recipients'], list)
            assert len(config['notification']['recipients']) == 2
        finally:
            os.unlink(temp_path)
    
    def test_load_directory_instead_of_file(self):
        """Test loading a directory instead of a file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValidationError, match="Configuration path is not a file"):
                self.config_manager.load_config(temp_dir)