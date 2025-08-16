"""
Secure credential management for the Kafka self-healing system.
"""

import os
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional, Union
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from .exceptions import ValidationError


class CredentialManager:
    """Manages secure storage and retrieval of credentials."""
    
    def __init__(self, encryption_key: Optional[bytes] = None):
        """
        Initialize credential manager.
        
        Args:
            encryption_key: Optional encryption key for file-based credentials.
                          If None, will attempt to derive from environment.
        """
        self._credentials: Dict[str, Any] = {}
        self._encryption_key = encryption_key
        self._fernet: Optional[Fernet] = None
        
        if encryption_key:
            self._fernet = Fernet(encryption_key)
    
    def set_credential(self, key: str, value: Union[str, Dict[str, Any]]) -> None:
        """
        Store a credential in memory.
        
        Args:
            key: Credential identifier
            value: Credential value (string or dictionary)
        """
        if not key:
            raise ValidationError("Credential key cannot be empty")
        
        self._credentials[key] = value
    
    def get_credential(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a credential.
        
        First checks environment variables, then in-memory storage.
        
        Args:
            key: Credential identifier
            default: Default value if credential not found
            
        Returns:
            Credential value or default
        """
        # Check environment variables first
        env_value = os.environ.get(key)
        if env_value is not None:
            return env_value
        
        # Check in-memory storage
        return self._credentials.get(key, default)
    
    def load_from_env(self, prefix: str = "") -> None:
        """
        Load credentials from environment variables.
        
        Args:
            prefix: Optional prefix to filter environment variables
        """
        for key, value in os.environ.items():
            if not prefix or key.startswith(prefix):
                credential_key = key[len(prefix):] if prefix else key
                self._credentials[credential_key] = value
    
    def load_from_file(self, file_path: str, encrypted: bool = False) -> None:
        """
        Load credentials from a file.
        
        Args:
            file_path: Path to credentials file
            encrypted: Whether the file is encrypted
            
        Raises:
            ValidationError: If file cannot be loaded or decrypted
        """
        credential_file = Path(file_path)
        
        if not credential_file.exists():
            raise ValidationError(f"Credential file not found: {file_path}")
        
        try:
            with open(credential_file, 'rb') as f:
                content = f.read()
            
            if encrypted:
                if not self._fernet:
                    raise ValidationError("No encryption key available for decrypting credentials")
                content = self._fernet.decrypt(content)
            
            # Parse JSON content
            credentials_data = json.loads(content.decode('utf-8'))
            
            if not isinstance(credentials_data, dict):
                raise ValidationError("Credentials file must contain a JSON object")
            
            self._credentials.update(credentials_data)
            
        except json.JSONDecodeError as e:
            raise ValidationError(f"Failed to parse credentials file as JSON: {e}")
        except Exception as e:
            raise ValidationError(f"Failed to load credentials file: {e}")
    
    def save_to_file(self, file_path: str, encrypted: bool = False) -> None:
        """
        Save credentials to a file.
        
        Args:
            file_path: Path to save credentials file
            encrypted: Whether to encrypt the file
            
        Raises:
            ValidationError: If file cannot be saved or encrypted
        """
        try:
            # Convert to JSON
            content = json.dumps(self._credentials, indent=2).encode('utf-8')
            
            if encrypted:
                if not self._fernet:
                    raise ValidationError("No encryption key available for encrypting credentials")
                content = self._fernet.encrypt(content)
            
            # Ensure directory exists
            credential_file = Path(file_path)
            credential_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file with restricted permissions
            with open(credential_file, 'wb') as f:
                f.write(content)
            
            # Set file permissions to be readable only by owner
            credential_file.chmod(0o600)
            
        except Exception as e:
            raise ValidationError(f"Failed to save credentials file: {e}")
    
    def validate_credential(self, key: str, required_fields: Optional[list] = None) -> bool:
        """
        Validate that a credential exists and has required fields.
        
        Args:
            key: Credential identifier
            required_fields: List of required fields for dictionary credentials
            
        Returns:
            True if credential is valid
            
        Raises:
            ValidationError: If credential is invalid
        """
        credential = self.get_credential(key)
        
        if credential is None:
            raise ValidationError(f"Required credential not found: {key}")
        
        if required_fields and isinstance(credential, dict):
            missing_fields = [field for field in required_fields if field not in credential]
            if missing_fields:
                raise ValidationError(f"Credential '{key}' missing required fields: {missing_fields}")
        
        return True
    
    def get_kafka_credentials(self) -> Dict[str, Any]:
        """
        Get Kafka-specific credentials.
        
        Returns:
            Dictionary containing Kafka credentials
        """
        credentials = {}
        
        # SASL credentials
        sasl_username = self.get_credential('KAFKA_SASL_USERNAME')
        sasl_password = self.get_credential('KAFKA_SASL_PASSWORD')
        sasl_mechanism = self.get_credential('KAFKA_SASL_MECHANISM', 'PLAIN')
        
        if sasl_username and sasl_password:
            credentials['sasl'] = {
                'username': sasl_username,
                'password': sasl_password,
                'mechanism': sasl_mechanism
            }
        
        # SSL credentials
        ssl_keystore_path = self.get_credential('KAFKA_SSL_KEYSTORE_PATH')
        ssl_keystore_password = self.get_credential('KAFKA_SSL_KEYSTORE_PASSWORD')
        ssl_truststore_path = self.get_credential('KAFKA_SSL_TRUSTSTORE_PATH')
        ssl_truststore_password = self.get_credential('KAFKA_SSL_TRUSTSTORE_PASSWORD')
        
        if ssl_keystore_path or ssl_truststore_path:
            credentials['ssl'] = {
                'keystore_path': ssl_keystore_path,
                'keystore_password': ssl_keystore_password,
                'truststore_path': ssl_truststore_path,
                'truststore_password': ssl_truststore_password
            }
        
        return credentials
    
    def get_zookeeper_credentials(self) -> Dict[str, Any]:
        """
        Get Zookeeper-specific credentials.
        
        Returns:
            Dictionary containing Zookeeper credentials
        """
        credentials = {}
        
        # SASL credentials
        sasl_username = self.get_credential('ZOOKEEPER_SASL_USERNAME')
        sasl_password = self.get_credential('ZOOKEEPER_SASL_PASSWORD')
        
        if sasl_username and sasl_password:
            credentials['sasl'] = {
                'username': sasl_username,
                'password': sasl_password
            }
        
        # SSL credentials
        ssl_keystore_path = self.get_credential('ZOOKEEPER_SSL_KEYSTORE_PATH')
        ssl_keystore_password = self.get_credential('ZOOKEEPER_SSL_KEYSTORE_PASSWORD')
        ssl_truststore_path = self.get_credential('ZOOKEEPER_SSL_TRUSTSTORE_PATH')
        ssl_truststore_password = self.get_credential('ZOOKEEPER_SSL_TRUSTSTORE_PASSWORD')
        
        if ssl_keystore_path or ssl_truststore_path:
            credentials['ssl'] = {
                'keystore_path': ssl_keystore_path,
                'keystore_password': ssl_keystore_password,
                'truststore_path': ssl_truststore_path,
                'truststore_password': ssl_truststore_password
            }
        
        return credentials
    
    def get_smtp_credentials(self) -> Dict[str, Any]:
        """
        Get SMTP-specific credentials.
        
        Returns:
            Dictionary containing SMTP credentials
        """
        return {
            'username': self.get_credential('SMTP_USERNAME'),
            'password': self.get_credential('SMTP_PASSWORD')
        }
    
    def clear_credentials(self) -> None:
        """Clear all stored credentials from memory."""
        self._credentials.clear()
    
    def has_credential(self, key: str) -> bool:
        """
        Check if a credential exists.
        
        Args:
            key: Credential identifier
            
        Returns:
            True if credential exists
        """
        return self.get_credential(key) is not None
    
    @staticmethod
    def generate_encryption_key() -> bytes:
        """
        Generate a new encryption key for file-based credentials.
        
        Returns:
            32-byte encryption key
        """
        return Fernet.generate_key()
    
    @staticmethod
    def derive_key_from_password(password: str, salt: bytes = None) -> bytes:
        """
        Derive an encryption key from a password.
        
        Args:
            password: Password to derive key from
            salt: Optional salt bytes (generates random if None)
            
        Returns:
            32-byte encryption key
        """
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key


class SecureCredentialStore:
    """External credential store interface for advanced credential management."""
    
    def __init__(self, store_type: str = "file", **kwargs):
        """
        Initialize credential store.
        
        Args:
            store_type: Type of credential store ('file', 'env', 'vault')
            **kwargs: Store-specific configuration
        """
        self.store_type = store_type
        self.config = kwargs
        self._credential_manager = CredentialManager()
    
    def initialize(self) -> None:
        """Initialize the credential store."""
        if self.store_type == "file":
            file_path = self.config.get('file_path', 'credentials.json')
            encrypted = self.config.get('encrypted', False)
            
            if encrypted:
                encryption_key = self.config.get('encryption_key')
                if not encryption_key:
                    # Try to get key from environment
                    key_env = os.environ.get('CREDENTIAL_ENCRYPTION_KEY')
                    if key_env:
                        encryption_key = base64.urlsafe_b64decode(key_env)
                    else:
                        raise ValidationError("Encryption key required for encrypted credential store")
                
                self._credential_manager = CredentialManager(encryption_key)
            
            try:
                self._credential_manager.load_from_file(file_path, encrypted)
            except ValidationError:
                # File doesn't exist or is empty, that's okay
                pass
        
        elif self.store_type == "env":
            prefix = self.config.get('prefix', '')
            self._credential_manager.load_from_env(prefix)
        
        elif self.store_type == "vault":
            # Placeholder for HashiCorp Vault integration
            raise ValidationError("Vault credential store not yet implemented")
        
        else:
            raise ValidationError(f"Unsupported credential store type: {self.store_type}")
    
    def get_credential_manager(self) -> CredentialManager:
        """
        Get the underlying credential manager.
        
        Returns:
            CredentialManager instance
        """
        return self._credential_manager