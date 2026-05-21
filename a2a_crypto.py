#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a Message Encryption — End-to-end encrypted messaging (v1.3).

Provides optional encryption for sensitive messages using cryptography library.
Supports symmetric (shared key) and asymmetric (public key) encryption.
"""

import json
import base64
from typing import Optional, Tuple
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class CryptoClient:
    """End-to-end encryption for a2a messages."""

    def __init__(self, project: str, agent_id: str, key_dir: Optional[str] = None):
        """Initialize crypto client.

        Args:
            project: Project name
            agent_id: This agent's ID
            key_dir: Directory for storing keys (defaults to ~/.a2a/{project}/keys)
        """
        if not HAS_CRYPTO:
            raise ImportError(
                "cryptography library required: pip install cryptography"
            )

        self.project = project
        self.agent_id = agent_id
        self.key_dir = Path(key_dir or Path.home() / ".a2a" / project / "keys")
        self.key_dir.mkdir(parents=True, exist_ok=True)

        self.private_key_path = self.key_dir / f"{agent_id}_private.pem"
        self.public_key_path = self.key_dir / f"{agent_id}_public.pem"
        self.symmetric_key_path = self.key_dir / "shared_key"

    # Symmetric Encryption (Shared Key)

    def generate_symmetric_key(self) -> str:
        """Generate a symmetric encryption key.

        Returns:
            Base64-encoded key
        """
        key = Fernet.generate_key()
        key_b64 = base64.b64encode(key).decode()

        # Optionally save shared key (not recommended for production)
        # self.symmetric_key_path.write_bytes(key)

        return key_b64

    def encrypt_message(
        self, message: str, symmetric_key: str
    ) -> str:
        """Encrypt message using symmetric key.

        Args:
            message: Message to encrypt
            symmetric_key: Base64-encoded symmetric key

        Returns:
            Encrypted message (base64-encoded)
        """
        try:
            key = base64.b64decode(symmetric_key)
            cipher = Fernet(key)
            encrypted = cipher.encrypt(message.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {e}")

    def decrypt_message(
        self, encrypted_message: str, symmetric_key: str
    ) -> str:
        """Decrypt message using symmetric key.

        Args:
            encrypted_message: Encrypted message (base64-encoded)
            symmetric_key: Base64-encoded symmetric key

        Returns:
            Decrypted message
        """
        try:
            key = base64.b64decode(symmetric_key)
            cipher = Fernet(key)
            encrypted = base64.b64decode(encrypted_message)
            decrypted = cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    # Asymmetric Encryption (Public/Private Key)

    def generate_keypair(self) -> Tuple[str, str]:
        """Generate RSA public/private keypair.

        Returns:
            (public_key, private_key) both as PEM strings
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )

        # Save private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.private_key_path.write_bytes(private_pem)

        # Save public key
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.public_key_path.write_bytes(public_pem)

        return public_pem.decode(), private_pem.decode()

    def encrypt_with_public_key(
        self, message: str, public_key_pem: str
    ) -> str:
        """Encrypt message using recipient's public key.

        Args:
            message: Message to encrypt
            public_key_pem: Recipient's public key (PEM format)

        Returns:
            Encrypted message (base64-encoded)
        """
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode()
            )
            encrypted = public_key.encrypt(
                message.encode(),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {e}")

    def decrypt_with_private_key(
        self, encrypted_message: str, private_key_pem: Optional[str] = None
    ) -> str:
        """Decrypt message using private key.

        Args:
            encrypted_message: Encrypted message (base64-encoded)
            private_key_pem: Private key (PEM format, defaults to agent's key)

        Returns:
            Decrypted message
        """
        try:
            if private_key_pem is None:
                private_key_pem = self.private_key_path.read_text()

            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(), password=None
            )
            encrypted = base64.b64decode(encrypted_message)
            decrypted = private_key.decrypt(
                encrypted,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def get_public_key(self) -> str:
        """Get this agent's public key.

        Returns:
            Public key in PEM format
        """
        if not self.public_key_path.exists():
            self.generate_keypair()
        return self.public_key_path.read_text()

    # Message Wrapping (Transparent Encryption)

    def wrap_encrypted_message(
        self, message: str, recipient_public_key: str, include_sender: bool = True
    ) -> str:
        """Wrap message with encryption metadata for transparent handling.

        Args:
            message: Original message
            recipient_public_key: Recipient's public key
            include_sender: Include sender's public key in wrapper

        Returns:
            JSON string with encryption metadata
        """
        encrypted = self.encrypt_with_public_key(message, recipient_public_key)

        wrapper = {
            "type": "encrypted",
            "version": "1",
            "algorithm": "RSA-2048-OAEP-SHA256",
            "sender": self.agent_id,
            "encrypted_body": encrypted,
        }

        if include_sender:
            wrapper["sender_public_key"] = self.get_public_key()

        return json.dumps(wrapper)

    @staticmethod
    def unwrap_encrypted_message(
        wrapped_message: str, crypto_client: "CryptoClient"
    ) -> Optional[str]:
        """Unwrap and decrypt encrypted message.

        Args:
            wrapped_message: Wrapped message JSON
            crypto_client: CryptoClient for decryption

        Returns:
            Decrypted message or None if not encrypted
        """
        try:
            wrapper = json.loads(wrapped_message)
            if wrapper.get("type") == "encrypted":
                encrypted_body = wrapper.get("encrypted_body")
                return crypto_client.decrypt_with_private_key(encrypted_body)
        except Exception:
            pass
        return None


def encrypt_file(filepath: str, symmetric_key: str) -> None:
    """Encrypt a file's contents.

    Args:
        filepath: Path to file
        symmetric_key: Base64-encoded symmetric key
    """
    crypto = CryptoClient("files", "fileenc")
    content = Path(filepath).read_text()
    encrypted = crypto.encrypt_message(content, symmetric_key)
    Path(filepath).write_text(encrypted)


def decrypt_file(filepath: str, symmetric_key: str) -> str:
    """Decrypt a file's contents.

    Args:
        filepath: Path to encrypted file
        symmetric_key: Base64-encoded symmetric key

    Returns:
        Decrypted content
    """
    crypto = CryptoClient("files", "filedec")
    encrypted = Path(filepath).read_text()
    return crypto.decrypt_message(encrypted, symmetric_key)
