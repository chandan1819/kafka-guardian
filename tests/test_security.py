"""
Unit tests for security and authentication functionality.
"""

import ssl
import socket
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import pytest

from src.kafka_self_healing.security import (
    SSLContextManager, SASLAuthenticator, SecureConnectionManager, CredentialFilter
)
from src.kafka_self_healing.models import SecurityConfig
from src.kafka_self_healing.credentials import CredentialManager
from src.kafka_self_healing.exceptions import ValidationError


class TestSSLContextManager:
    """Test cases for SSLContextManager class."""
    
    def test_init(self):
        """Test initialization of SSL context manager."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        
        assert ssl_manager.credential_manager == credential_manager
    
    def test_create_ssl_context_ssl_disabled(self):
        """Test creating SSL context when SSL is disabled raises error."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False)
        
        with pytest.raises(ValidationError, match="SSL is not enabled"):
            ssl_manager.create_ssl_context(security_config)
    
    def test_create_ssl_context_basic(self):
        """Test creating basic SSL context."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True)
        
        context = ssl_manager.create_ssl_context(security_config)
        
        assert isinstance(context, ssl.SSLContext)
        assert context.check_hostname is True
        assert context.verify_mode == ssl.CERT_REQUIRED
    
    def test_create_ssl_context_no_hostname_verification(self):
        """Test creating SSL context with hostname verification disabled."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(
            enable_ssl=True,
            ssl_verify_hostname=False
        )
        
        context = ssl_manager.create_ssl_context(security_config)
        
        assert context.check_hostname is False
        assert context.verify_mode == ssl.CERT_NONE
    
    def test_create_ssl_context_with_ca_cert(self):
        """Test creating SSL context with CA certificate."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        
        # Create temporary CA cert file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
            f.write("-----BEGIN CERTIFICATE-----\ntest_ca_cert\n-----END CERTIFICATE-----")
            ca_cert_path = f.name
        
        try:
            security_config = SecurityConfig(
                enable_ssl=True,
                ssl_ca_cert_path=ca_cert_path
            )
            
            with patch.object(ssl.SSLContext, 'load_verify_locations') as mock_load:
                context = ssl_manager.create_ssl_context(security_config)
                mock_load.assert_called_once_with(cafile=ca_cert_path)
        finally:
            os.unlink(ca_cert_path)
    
    def test_create_ssl_context_ca_cert_not_found(self):
        """Test creating SSL context with non-existent CA certificate raises error."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(
            enable_ssl=True,
            ssl_ca_cert_path="/nonexistent/ca.pem"
        )
        
        with pytest.raises(ValidationError, match="CA certificate file not found"):
            ssl_manager.create_ssl_context(security_config)
    
    def test_create_ssl_context_with_client_cert(self):
        """Test creating SSL context with client certificate."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        
        # Create temporary cert and key files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as cert_f:
            cert_f.write("-----BEGIN CERTIFICATE-----\ntest_cert\n-----END CERTIFICATE-----")
            cert_path = cert_f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as key_f:
            key_f.write("-----BEGIN PRIVATE KEY-----\ntest_key\n-----END PRIVATE KEY-----")
            key_path = key_f.name
        
        try:
            security_config = SecurityConfig(
                enable_ssl=True,
                ssl_cert_path=cert_path,
                ssl_key_path=key_path,
                ssl_key_password="test_password"
            )
            
            with patch.object(ssl.SSLContext, 'load_cert_chain') as mock_load:
                context = ssl_manager.create_ssl_context(security_config)
                mock_load.assert_called_once_with(
                    certfile=cert_path,
                    keyfile=key_path,
                    password="test_password"
                )
        finally:
            os.unlink(cert_path)
            os.unlink(key_path)
    
    def test_create_ssl_context_client_cert_not_found(self):
        """Test creating SSL context with non-existent client certificate raises error."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(
            enable_ssl=True,
            ssl_cert_path="/nonexistent/cert.pem",
            ssl_key_path="/nonexistent/key.pem"
        )
        
        with pytest.raises(ValidationError, match="Client certificate file not found"):
            ssl_manager.create_ssl_context(security_config)
    
    def test_create_kafka_ssl_context(self):
        """Test creating Kafka-specific SSL context."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True)
        
        with patch.object(ssl_manager, 'create_ssl_context') as mock_create:
            mock_create.return_value = MagicMock()
            ssl_manager.create_kafka_ssl_context(security_config)
            mock_create.assert_called_once_with(security_config, "kafka")
    
    def test_create_zookeeper_ssl_context(self):
        """Test creating Zookeeper-specific SSL context."""
        credential_manager = CredentialManager()
        ssl_manager = SSLContextManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True)
        
        with patch.object(ssl_manager, 'create_ssl_context') as mock_create:
            mock_create.return_value = MagicMock()
            ssl_manager.create_zookeeper_ssl_context(security_config)
            mock_create.assert_called_once_with(security_config, "zookeeper")


class TestSASLAuthenticator:
    """Test cases for SASLAuthenticator class."""
    
    def test_init(self):
        """Test initialization of SASL authenticator."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        
        assert sasl_auth.credential_manager == credential_manager
    
    def test_get_kafka_sasl_config_sasl_disabled(self):
        """Test getting Kafka SASL config when SASL is disabled."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(enable_sasl=False)
        
        config = sasl_auth.get_kafka_sasl_config(security_config)
        
        assert config == {}
    
    @patch.dict(os.environ, {
        "KAFKA_SASL_USERNAME": "kafka_user",
        "KAFKA_SASL_PASSWORD": "kafka_pass"
    })
    def test_get_kafka_sasl_config_plain(self):
        """Test getting Kafka SASL config for PLAIN mechanism."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(
            enable_sasl=True,
            sasl_mechanism="PLAIN"
        )
        
        config = sasl_auth.get_kafka_sasl_config(security_config)
        
        assert config["sasl_mechanism"] == "PLAIN"
        assert config["sasl_plain_username"] == "kafka_user"
        assert config["sasl_plain_password"] == "kafka_pass"
    
    @patch.dict(os.environ, {
        "KAFKA_SASL_USERNAME": "kafka_user",
        "KAFKA_SASL_PASSWORD": "kafka_pass"
    })
    def test_get_kafka_sasl_config_scram(self):
        """Test getting Kafka SASL config for SCRAM mechanism."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(
            enable_sasl=True,
            sasl_mechanism="SCRAM-SHA-256"
        )
        
        config = sasl_auth.get_kafka_sasl_config(security_config)
        
        assert config["sasl_mechanism"] == "SCRAM-SHA-256"
        assert config["sasl_plain_username"] == "kafka_user"
        assert config["sasl_plain_password"] == "kafka_pass"
    
    def test_get_kafka_sasl_config_no_credentials(self):
        """Test getting Kafka SASL config without credentials raises error."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(enable_sasl=True)
        
        with pytest.raises(ValidationError, match="SASL credentials not found for Kafka"):
            sasl_auth.get_kafka_sasl_config(security_config)
    
    @patch.dict(os.environ, {"KAFKA_SASL_USERNAME": "kafka_user"})
    def test_get_kafka_sasl_config_missing_password(self):
        """Test getting Kafka SASL config with missing password raises error."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(enable_sasl=True)
        
        with pytest.raises(ValidationError, match="SASL credentials not found for Kafka"):
            sasl_auth.get_kafka_sasl_config(security_config)
    
    @patch.dict(os.environ, {
        "ZOOKEEPER_SASL_USERNAME": "zk_user",
        "ZOOKEEPER_SASL_PASSWORD": "zk_pass"
    })
    def test_get_zookeeper_sasl_config(self):
        """Test getting Zookeeper SASL config."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(enable_sasl=True)
        
        config = sasl_auth.get_zookeeper_sasl_config(security_config)
        
        assert config["username"] == "zk_user"
        assert config["password"] == "zk_pass"
    
    def test_get_zookeeper_sasl_config_sasl_disabled(self):
        """Test getting Zookeeper SASL config when SASL is disabled."""
        credential_manager = CredentialManager()
        sasl_auth = SASLAuthenticator(credential_manager)
        security_config = SecurityConfig(enable_sasl=False)
        
        config = sasl_auth.get_zookeeper_sasl_config(security_config)
        
        assert config == {}


class TestSecureConnectionManager:
    """Test cases for SecureConnectionManager class."""
    
    def test_init(self):
        """Test initialization of secure connection manager."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        
        assert conn_manager.credential_manager == credential_manager
        assert isinstance(conn_manager.ssl_context_manager, SSLContextManager)
        assert isinstance(conn_manager.sasl_authenticator, SASLAuthenticator)
    
    @patch('socket.socket')
    def test_create_secure_socket_no_ssl(self, mock_socket):
        """Test creating secure socket without SSL."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False)
        
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        
        result = conn_manager.create_secure_socket("localhost", 9092, security_config)
        
        assert result == mock_sock
        mock_sock.settimeout.assert_called_once_with(30)
        mock_sock.connect.assert_called_once_with(("localhost", 9092))
    
    @patch('socket.socket')
    def test_create_secure_socket_with_ssl(self, mock_socket):
        """Test creating secure socket with SSL."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True)
        
        mock_sock = MagicMock()
        mock_ssl_sock = MagicMock()
        mock_socket.return_value = mock_sock
        
        with patch.object(conn_manager.ssl_context_manager, 'create_ssl_context') as mock_create_context:
            mock_context = MagicMock()
            mock_context.wrap_socket.return_value = mock_ssl_sock
            mock_create_context.return_value = mock_context
            
            result = conn_manager.create_secure_socket("localhost", 9092, security_config, "kafka")
            
            assert result == mock_ssl_sock
            mock_create_context.assert_called_once_with(security_config, "kafka")
            mock_context.wrap_socket.assert_called_once_with(mock_sock, server_hostname="localhost")
            mock_ssl_sock.connect.assert_called_once_with(("localhost", 9092))
    
    @patch('socket.socket')
    def test_create_secure_socket_connection_error(self, mock_socket):
        """Test creating secure socket with connection error."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False)
        
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = socket.error("Connection refused")
        mock_socket.return_value = mock_sock
        
        with pytest.raises(ValidationError, match="Failed to create secure connection"):
            conn_manager.create_secure_socket("localhost", 9092, security_config)
        
        mock_sock.close.assert_called_once()
    
    def test_get_kafka_connection_config_plaintext(self):
        """Test getting Kafka connection config for plaintext."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False, enable_sasl=False)
        
        config = conn_manager.get_kafka_connection_config(security_config)
        
        assert config["security_protocol"] == "PLAINTEXT"
    
    @patch.dict(os.environ, {
        "KAFKA_SASL_USERNAME": "kafka_user",
        "KAFKA_SASL_PASSWORD": "kafka_pass"
    })
    def test_get_kafka_connection_config_sasl_plaintext(self):
        """Test getting Kafka connection config for SASL plaintext."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False, enable_sasl=True)
        
        config = conn_manager.get_kafka_connection_config(security_config)
        
        assert config["security_protocol"] == "SASL_PLAINTEXT"
        assert config["sasl_mechanism"] == "PLAIN"
        assert config["sasl_plain_username"] == "kafka_user"
        assert config["sasl_plain_password"] == "kafka_pass"
    
    def test_get_kafka_connection_config_ssl(self):
        """Test getting Kafka connection config for SSL."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True, enable_sasl=False)
        
        with patch.object(conn_manager.ssl_context_manager, 'create_kafka_ssl_context') as mock_create:
            mock_context = MagicMock()
            mock_create.return_value = mock_context
            
            config = conn_manager.get_kafka_connection_config(security_config)
            
            assert config["security_protocol"] == "SSL"
            assert config["ssl_context"] == mock_context
            assert config["ssl_check_hostname"] is True
    
    @patch.dict(os.environ, {
        "KAFKA_SASL_USERNAME": "kafka_user",
        "KAFKA_SASL_PASSWORD": "kafka_pass"
    })
    def test_get_kafka_connection_config_sasl_ssl(self):
        """Test getting Kafka connection config for SASL SSL."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True, enable_sasl=True)
        
        with patch.object(conn_manager.ssl_context_manager, 'create_kafka_ssl_context') as mock_create:
            mock_context = MagicMock()
            mock_create.return_value = mock_context
            
            config = conn_manager.get_kafka_connection_config(security_config)
            
            assert config["security_protocol"] == "SASL_SSL"
            assert config["ssl_context"] == mock_context
            assert config["sasl_mechanism"] == "PLAIN"
            assert config["sasl_plain_username"] == "kafka_user"
            assert config["sasl_plain_password"] == "kafka_pass"
    
    def test_get_zookeeper_connection_config_no_ssl(self):
        """Test getting Zookeeper connection config without SSL."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False, enable_sasl=False)
        
        config = conn_manager.get_zookeeper_connection_config(security_config)
        
        assert config == {}
    
    def test_get_zookeeper_connection_config_ssl(self):
        """Test getting Zookeeper connection config with SSL."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=True)
        
        with patch.object(conn_manager.ssl_context_manager, 'create_zookeeper_ssl_context') as mock_create:
            mock_context = MagicMock()
            mock_create.return_value = mock_context
            
            config = conn_manager.get_zookeeper_connection_config(security_config)
            
            assert config["use_ssl"] is True
            assert config["ssl_context"] == mock_context
            assert config["ssl_check_hostname"] is True
    
    def test_test_connection_success(self):
        """Test successful connection test."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False)
        
        with patch.object(conn_manager, 'create_secure_socket') as mock_create:
            mock_sock = MagicMock()
            mock_create.return_value = mock_sock
            
            success, error = conn_manager.test_connection("localhost", 9092, security_config)
            
            assert success is True
            assert error is None
            mock_sock.close.assert_called_once()
    
    def test_test_connection_failure(self):
        """Test failed connection test."""
        credential_manager = CredentialManager()
        conn_manager = SecureConnectionManager(credential_manager)
        security_config = SecurityConfig(enable_ssl=False)
        
        with patch.object(conn_manager, 'create_secure_socket') as mock_create:
            mock_create.side_effect = ValidationError("Connection failed")
            
            success, error = conn_manager.test_connection("localhost", 9092, security_config)
            
            assert success is False
            assert "Connection failed" in error


class TestCredentialFilter:
    """Test cases for CredentialFilter class."""
    
    def test_filter_dict_with_sensitive_keys(self):
        """Test filtering dictionary with sensitive keys."""
        data = {
            "username": "user",
            "password": "secret123",
            "host": "localhost",
            "sasl_plain_password": "sasl_secret",
            "ssl_key_password": "ssl_secret"
        }
        
        filtered = CredentialFilter.filter_dict(data)
        
        assert filtered["username"] == "user"
        assert filtered["password"] == "***MASKED***"
        assert filtered["host"] == "localhost"
        assert filtered["sasl_plain_password"] == "***MASKED***"
        assert filtered["ssl_key_password"] == "***MASKED***"
    
    def test_filter_dict_nested(self):
        """Test filtering nested dictionary."""
        data = {
            "config": {
                "username": "user",
                "password": "secret123"
            },
            "other": "value"
        }
        
        filtered = CredentialFilter.filter_dict(data)
        
        assert filtered["config"]["username"] == "user"
        assert filtered["config"]["password"] == "***MASKED***"
        assert filtered["other"] == "value"
    
    def test_filter_dict_with_list(self):
        """Test filtering dictionary with list containing dictionaries."""
        data = {
            "servers": [
                {"host": "server1", "password": "secret1"},
                {"host": "server2", "password": "secret2"}
            ]
        }
        
        filtered = CredentialFilter.filter_dict(data)
        
        assert filtered["servers"][0]["host"] == "server1"
        assert filtered["servers"][0]["password"] == "***MASKED***"
        assert filtered["servers"][1]["host"] == "server2"
        assert filtered["servers"][1]["password"] == "***MASKED***"
    
    def test_filter_string(self):
        """Test filtering sensitive information from string."""
        text = "username=user password=secret123 host=localhost key=mykey"
        
        filtered = CredentialFilter.filter_string(text)
        
        assert "username=user" in filtered
        assert "password=***MASKED***" in filtered
        assert "host=localhost" in filtered
        assert "key=***MASKED***" in filtered
    
    def test_filter_command_args_with_equals(self):
        """Test filtering command arguments with equals format."""
        args = ["--host=localhost", "--password=secret123", "--port=9092"]
        
        filtered = CredentialFilter.filter_command_args(args)
        
        assert "--host=localhost" in filtered
        assert "--password=***MASKED***" in filtered
        assert "--port=9092" in filtered
    
    def test_filter_command_args_separate_value(self):
        """Test filtering command arguments with separate value."""
        args = ["--host", "localhost", "--password", "secret123", "--port", "9092"]
        
        filtered = CredentialFilter.filter_command_args(args)
        
        expected = ["--host", "localhost", "--password", "***MASKED***", "--port", "9092"]
        assert filtered == expected