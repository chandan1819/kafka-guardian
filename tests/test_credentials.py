"""
Unit tests for credential management functionality.
"""

import os
import json
import tempfile
import base64
from pathlib import Path
from unittest.mock import patch, mock_open
import pytest
from cryptography.fernet import Fernet

from src.kafka_self_healing.credentials import CredentialManager, SecureCredentialStore
from src.kafka_self_healing.exceptions import ValidationError


class TestCredentialManager:
    """Test cases for CredentialManager class."""
    
    def test_init_without_encryption_key(self):
        """Test initialization without encryption key."""
        manager = CredentialManager()
        assert manager._encryption_key is None
        assert manager._fernet is None
        assert manager._credentials == {}
    
    def test_init_with_encryption_key(self):
        """Test initialization with encryption key."""
        key = Fernet.generate_key()
        manager = CredentialManager(key)
        assert manager._encryption_key == key
        assert manager._fernet is not None
    
    def test_set_and_get_credential(self):
        """Test setting and getting credentials."""
        manager = CredentialManager()
        
        # Test string credential
        manager.set_credential("test_key", "test_value")
        assert manager.get_credential("test_key") == "test_value"
        
        # Test dictionary credential
        cred_dict = {"username": "user", "password": "pass"}
        manager.set_credential("test_dict", cred_dict)
        assert manager.get_credential("test_dict") == cred_dict
    
    def test_set_credential_empty_key(self):
        """Test setting credential with empty key raises error."""
        manager = CredentialManager()
        with pytest.raises(ValidationError, match="Credential key cannot be empty"):
            manager.set_credential("", "value")
    
    def test_get_credential_default(self):
        """Test getting non-existent credential returns default."""
        manager = CredentialManager()
        assert manager.get_credential("nonexistent") is None
        assert manager.get_credential("nonexistent", "default") == "default"
    
    @patch.dict(os.environ, {"TEST_ENV_VAR": "env_value"})
    def test_get_credential_from_env(self):
        """Test getting credential from environment variable."""
        manager = CredentialManager()
        manager.set_credential("TEST_ENV_VAR", "memory_value")
        
        # Environment variable should take precedence
        assert manager.get_credential("TEST_ENV_VAR") == "env_value"
    
    @patch.dict(os.environ, {"PREFIX_VAR1": "value1", "PREFIX_VAR2": "value2", "OTHER_VAR": "other"}, clear=True)
    def test_load_from_env_with_prefix(self):
        """Test loading credentials from environment with prefix."""
        manager = CredentialManager()
        manager.load_from_env("PREFIX_")
        
        assert manager.get_credential("VAR1") == "value1"
        assert manager.get_credential("VAR2") == "value2"
        # Check that OTHER_VAR was loaded into memory storage (since it's in env)
        # but VAR1 and VAR2 were loaded with prefix stripped
        assert "VAR1" in manager._credentials
        assert "VAR2" in manager._credentials
        assert "OTHER_VAR" not in manager._credentials
    
    @patch.dict(os.environ, {"VAR1": "value1", "VAR2": "value2"})
    def test_load_from_env_without_prefix(self):
        """Test loading credentials from environment without prefix."""
        manager = CredentialManager()
        manager.load_from_env()
        
        assert manager.get_credential("VAR1") == "value1"
        assert manager.get_credential("VAR2") == "value2"
    
    def test_load_from_file_unencrypted(self):
        """Test loading credentials from unencrypted file."""
        manager = CredentialManager()
        credentials = {"key1": "value1", "key2": {"nested": "value"}}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(credentials, f)
            temp_path = f.name
        
        try:
            manager.load_from_file(temp_path, encrypted=False)
            assert manager.get_credential("key1") == "value1"
            assert manager.get_credential("key2") == {"nested": "value"}
        finally:
            os.unlink(temp_path)
    
    def test_load_from_file_encrypted(self):
        """Test loading credentials from encrypted file."""
        key = Fernet.generate_key()
        manager = CredentialManager(key)
        credentials = {"key1": "value1", "key2": "value2"}
        
        # Create encrypted file
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(json.dumps(credentials).encode())
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(encrypted_data)
            temp_path = f.name
        
        try:
            manager.load_from_file(temp_path, encrypted=True)
            assert manager.get_credential("key1") == "value1"
            assert manager.get_credential("key2") == "value2"
        finally:
            os.unlink(temp_path)
    
    def test_load_from_file_not_found(self):
        """Test loading from non-existent file raises error."""
        manager = CredentialManager()
        with pytest.raises(ValidationError, match="Credential file not found"):
            manager.load_from_file("/nonexistent/path.json")
    
    def test_load_from_file_invalid_json(self):
        """Test loading from file with invalid JSON raises error."""
        manager = CredentialManager()
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="Failed to parse credentials file as JSON"):
                manager.load_from_file(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_load_from_file_encrypted_without_key(self):
        """Test loading encrypted file without encryption key raises error."""
        manager = CredentialManager()  # No encryption key
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"encrypted content")
            temp_path = f.name
        
        try:
            with pytest.raises(ValidationError, match="No encryption key available"):
                manager.load_from_file(temp_path, encrypted=True)
        finally:
            os.unlink(temp_path)
    
    def test_save_to_file_unencrypted(self):
        """Test saving credentials to unencrypted file."""
        manager = CredentialManager()
        manager.set_credential("key1", "value1")
        manager.set_credential("key2", {"nested": "value"})
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "credentials.json")
            manager.save_to_file(file_path, encrypted=False)
            
            # Verify file was created and has correct permissions
            assert os.path.exists(file_path)
            file_stat = os.stat(file_path)
            assert oct(file_stat.st_mode)[-3:] == '600'  # Owner read/write only
            
            # Verify content
            with open(file_path, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data["key1"] == "value1"
            assert saved_data["key2"] == {"nested": "value"}
    
    def test_save_to_file_encrypted(self):
        """Test saving credentials to encrypted file."""
        key = Fernet.generate_key()
        manager = CredentialManager(key)
        manager.set_credential("key1", "value1")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "credentials.json")
            manager.save_to_file(file_path, encrypted=True)
            
            # Verify file was created
            assert os.path.exists(file_path)
            
            # Verify content is encrypted (should not be readable as JSON)
            with open(file_path, 'rb') as f:
                content = f.read()
            
            with pytest.raises(json.JSONDecodeError):
                json.loads(content.decode())
            
            # Verify we can decrypt and read it
            fernet = Fernet(key)
            decrypted = fernet.decrypt(content)
            data = json.loads(decrypted.decode())
            assert data["key1"] == "value1"
    
    def test_save_to_file_encrypted_without_key(self):
        """Test saving encrypted file without encryption key raises error."""
        manager = CredentialManager()  # No encryption key
        manager.set_credential("key1", "value1")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "credentials.json")
            with pytest.raises(ValidationError, match="No encryption key available"):
                manager.save_to_file(file_path, encrypted=True)
    
    def test_validate_credential_exists(self):
        """Test validating existing credential."""
        manager = CredentialManager()
        manager.set_credential("test_key", "test_value")
        
        assert manager.validate_credential("test_key") is True
    
    def test_validate_credential_not_exists(self):
        """Test validating non-existent credential raises error."""
        manager = CredentialManager()
        
        with pytest.raises(ValidationError, match="Required credential not found"):
            manager.validate_credential("nonexistent")
    
    def test_validate_credential_with_required_fields(self):
        """Test validating credential with required fields."""
        manager = CredentialManager()
        cred_dict = {"username": "user", "password": "pass", "host": "localhost"}
        manager.set_credential("test_cred", cred_dict)
        
        # Should pass with existing fields
        assert manager.validate_credential("test_cred", ["username", "password"]) is True
        
        # Should fail with missing fields
        with pytest.raises(ValidationError, match="missing required fields"):
            manager.validate_credential("test_cred", ["username", "api_key"])
    
    @patch.dict(os.environ, {
        "KAFKA_SASL_USERNAME": "kafka_user",
        "KAFKA_SASL_PASSWORD": "kafka_pass",
        "KAFKA_SASL_MECHANISM": "SCRAM-SHA-256"
    })
    def test_get_kafka_credentials(self):
        """Test getting Kafka-specific credentials."""
        manager = CredentialManager()
        
        credentials = manager.get_kafka_credentials()
        
        assert "sasl" in credentials
        assert credentials["sasl"]["username"] == "kafka_user"
        assert credentials["sasl"]["password"] == "kafka_pass"
        assert credentials["sasl"]["mechanism"] == "SCRAM-SHA-256"
    
    @patch.dict(os.environ, {
        "KAFKA_SSL_KEYSTORE_PATH": "/path/to/keystore",
        "KAFKA_SSL_KEYSTORE_PASSWORD": "keystore_pass"
    })
    def test_get_kafka_ssl_credentials(self):
        """Test getting Kafka SSL credentials."""
        manager = CredentialManager()
        
        credentials = manager.get_kafka_credentials()
        
        assert "ssl" in credentials
        assert credentials["ssl"]["keystore_path"] == "/path/to/keystore"
        assert credentials["ssl"]["keystore_password"] == "keystore_pass"
    
    @patch.dict(os.environ, {
        "ZOOKEEPER_SASL_USERNAME": "zk_user",
        "ZOOKEEPER_SASL_PASSWORD": "zk_pass"
    })
    def test_get_zookeeper_credentials(self):
        """Test getting Zookeeper-specific credentials."""
        manager = CredentialManager()
        
        credentials = manager.get_zookeeper_credentials()
        
        assert "sasl" in credentials
        assert credentials["sasl"]["username"] == "zk_user"
        assert credentials["sasl"]["password"] == "zk_pass"
    
    @patch.dict(os.environ, {
        "SMTP_USERNAME": "smtp_user",
        "SMTP_PASSWORD": "smtp_pass"
    })
    def test_get_smtp_credentials(self):
        """Test getting SMTP credentials."""
        manager = CredentialManager()
        
        credentials = manager.get_smtp_credentials()
        
        assert credentials["username"] == "smtp_user"
        assert credentials["password"] == "smtp_pass"
    
    def test_clear_credentials(self):
        """Test clearing all credentials."""
        manager = CredentialManager()
        manager.set_credential("key1", "value1")
        manager.set_credential("key2", "value2")
        
        assert len(manager._credentials) == 2
        
        manager.clear_credentials()
        
        assert len(manager._credentials) == 0
        assert manager.get_credential("key1") is None
    
    def test_has_credential(self):
        """Test checking if credential exists."""
        manager = CredentialManager()
        
        assert not manager.has_credential("test_key")
        
        manager.set_credential("test_key", "test_value")
        assert manager.has_credential("test_key")
    
    @patch.dict(os.environ, {"TEST_ENV": "env_value"})
    def test_has_credential_from_env(self):
        """Test checking credential existence from environment."""
        manager = CredentialManager()
        
        assert manager.has_credential("TEST_ENV")
    
    def test_generate_encryption_key(self):
        """Test generating encryption key."""
        key = CredentialManager.generate_encryption_key()
        
        assert isinstance(key, bytes)
        assert len(key) == 44  # Base64 encoded 32-byte key
        
        # Should be able to create Fernet instance
        fernet = Fernet(key)
        assert fernet is not None
    
    def test_derive_key_from_password(self):
        """Test deriving encryption key from password."""
        password = "test_password"
        salt = b"test_salt_16byte"
        
        key1 = CredentialManager.derive_key_from_password(password, salt)
        key2 = CredentialManager.derive_key_from_password(password, salt)
        
        # Same password and salt should produce same key
        assert key1 == key2
        
        # Different salt should produce different key
        key3 = CredentialManager.derive_key_from_password(password, b"different_salt16")
        assert key1 != key3
        
        # Should be valid Fernet key
        fernet = Fernet(key1)
        assert fernet is not None
    
    def test_derive_key_from_password_no_salt(self):
        """Test deriving key without providing salt."""
        password = "test_password"
        
        key1 = CredentialManager.derive_key_from_password(password)
        key2 = CredentialManager.derive_key_from_password(password)
        
        # Without fixed salt, keys should be different
        assert key1 != key2
        
        # Both should be valid Fernet keys
        fernet1 = Fernet(key1)
        fernet2 = Fernet(key2)
        assert fernet1 is not None
        assert fernet2 is not None


class TestSecureCredentialStore:
    """Test cases for SecureCredentialStore class."""
    
    def test_init_file_store(self):
        """Test initialization of file-based credential store."""
        store = SecureCredentialStore("file", file_path="test.json")
        
        assert store.store_type == "file"
        assert store.config["file_path"] == "test.json"
    
    def test_init_env_store(self):
        """Test initialization of environment-based credential store."""
        store = SecureCredentialStore("env", prefix="TEST_")
        
        assert store.store_type == "env"
        assert store.config["prefix"] == "TEST_"
    
    def test_init_unsupported_store(self):
        """Test initialization with unsupported store type."""
        store = SecureCredentialStore("unsupported")
        
        with pytest.raises(ValidationError, match="Unsupported credential store type"):
            store.initialize()
    
    def test_initialize_file_store_unencrypted(self):
        """Test initializing file store without encryption."""
        credentials = {"key1": "value1", "key2": "value2"}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(credentials, f)
            temp_path = f.name
        
        try:
            store = SecureCredentialStore("file", file_path=temp_path, encrypted=False)
            store.initialize()
            
            manager = store.get_credential_manager()
            assert manager.get_credential("key1") == "value1"
            assert manager.get_credential("key2") == "value2"
        finally:
            os.unlink(temp_path)
    
    def test_initialize_file_store_encrypted(self):
        """Test initializing encrypted file store."""
        key = Fernet.generate_key()
        credentials = {"key1": "value1", "key2": "value2"}
        
        # Create encrypted file
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(json.dumps(credentials).encode())
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(encrypted_data)
            temp_path = f.name
        
        try:
            store = SecureCredentialStore("file", file_path=temp_path, 
                                        encrypted=True, encryption_key=key)
            store.initialize()
            
            manager = store.get_credential_manager()
            assert manager.get_credential("key1") == "value1"
            assert manager.get_credential("key2") == "value2"
        finally:
            os.unlink(temp_path)
    
    @patch.dict(os.environ, {"CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(Fernet.generate_key()).decode()})
    def test_initialize_file_store_encrypted_from_env(self):
        """Test initializing encrypted file store with key from environment."""
        key_b64 = os.environ["CREDENTIAL_ENCRYPTION_KEY"]
        key = base64.urlsafe_b64decode(key_b64)
        credentials = {"key1": "value1"}
        
        # Create encrypted file
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(json.dumps(credentials).encode())
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(encrypted_data)
            temp_path = f.name
        
        try:
            store = SecureCredentialStore("file", file_path=temp_path, encrypted=True)
            store.initialize()
            
            manager = store.get_credential_manager()
            assert manager.get_credential("key1") == "value1"
        finally:
            os.unlink(temp_path)
    
    def test_initialize_file_store_encrypted_no_key(self):
        """Test initializing encrypted file store without key raises error."""
        store = SecureCredentialStore("file", file_path="test.json", encrypted=True)
        
        with pytest.raises(ValidationError, match="Encryption key required"):
            store.initialize()
    
    def test_initialize_file_store_nonexistent_file(self):
        """Test initializing file store with non-existent file."""
        store = SecureCredentialStore("file", file_path="/nonexistent/path.json")
        
        # Should not raise error - missing file is acceptable
        store.initialize()
        
        manager = store.get_credential_manager()
        assert manager is not None
    
    @patch.dict(os.environ, {"PREFIX_VAR1": "value1", "PREFIX_VAR2": "value2"})
    def test_initialize_env_store(self):
        """Test initializing environment-based credential store."""
        store = SecureCredentialStore("env", prefix="PREFIX_")
        store.initialize()
        
        manager = store.get_credential_manager()
        assert manager.get_credential("VAR1") == "value1"
        assert manager.get_credential("VAR2") == "value2"
    
    def test_initialize_vault_store_not_implemented(self):
        """Test that vault store raises not implemented error."""
        store = SecureCredentialStore("vault")
        
        with pytest.raises(ValidationError, match="Vault credential store not yet implemented"):
            store.initialize()
    
    def test_get_credential_manager(self):
        """Test getting credential manager instance."""
        store = SecureCredentialStore("env")
        store.initialize()
        
        manager = store.get_credential_manager()
        assert isinstance(manager, CredentialManager)