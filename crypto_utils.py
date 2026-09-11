"""
Cryptographic utilities for secure staff credential encryption at rest.
Uses Fernet (AES-128-CBC with HMAC-SHA256 authenticated symmetric encryption).
Keys are derived from server-side SECRET_KEY / CREDENTIAL_ENCRYPTION_KEY.
"""

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_CIPHER_INSTANCE: Optional[Fernet] = None
_BACKUP_CIPHER_INSTANCE: Optional[Fernet] = None


def get_credential_cipher() -> Fernet:
    """Return a singleton Fernet cipher instance based on server-side secret keys."""
    global _CIPHER_INSTANCE
    if _CIPHER_INSTANCE is not None:
        return _CIPHER_INSTANCE

    custom_key = os.getenv("CREDENTIAL_ENCRYPTION_KEY")
    if custom_key and len(custom_key.strip()) == 44:
        try:
            _CIPHER_INSTANCE = Fernet(custom_key.strip().encode())
            return _CIPHER_INSTANCE
        except Exception:
            logger.warning("Invalid CREDENTIAL_ENCRYPTION_KEY format, falling back to derived key.")

    # Derive a 32-byte URL-safe base64 key deterministically from SECRET_KEY
    secret = os.getenv("SECRET_KEY", "dawaiflow-secure-staff-credential-vault-key")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    _CIPHER_INSTANCE = Fernet(fernet_key)
    return _CIPHER_INSTANCE


def get_backup_cipher() -> Fernet:
    """Return a Fernet cipher instance for backup encryption & decryption."""
    global _BACKUP_CIPHER_INSTANCE
    if _BACKUP_CIPHER_INSTANCE is not None:
        return _BACKUP_CIPHER_INSTANCE

    custom_key = os.getenv("BACKUP_ENCRYPTION_KEY")
    if custom_key and len(custom_key.strip()) == 44:
        try:
            _BACKUP_CIPHER_INSTANCE = Fernet(custom_key.strip().encode())
            return _BACKUP_CIPHER_INSTANCE
        except Exception:
            logger.warning("Invalid BACKUP_ENCRYPTION_KEY format, falling back to derived key.")

    # Deterministically derive a backup encryption key from SECRET_KEY
    secret = os.getenv("SECRET_KEY", "dawaiflow-secure-backup-vault-key") + ":backup"
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    _BACKUP_CIPHER_INSTANCE = Fernet(fernet_key)
    return _BACKUP_CIPHER_INSTANCE



def encrypt_staff_password(plain_password: Optional[str]) -> Optional[str]:
    """
    Encrypt a plaintext staff password using authenticated symmetric encryption.
    Returns URL-safe ciphertext string, or None if input is empty.
    """
    if not plain_password:
        return None
    try:
        cipher = get_credential_cipher()
        encrypted_bytes = cipher.encrypt(plain_password.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encrypt staff password: {e}")
        return None


def decrypt_staff_password(token: Optional[str]) -> Optional[str]:
    """
    Decrypt an encrypted staff password token.
    Returns the original plaintext password, or None if decryption fails or token is empty.
    """
    if not token:
        return None
    try:
        cipher = get_credential_cipher()
        decrypted_bytes = cipher.decrypt(token.strip().encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Invalid token when decrypting staff password.")
        return None
    except Exception as e:
        logger.error(f"Error decrypting staff password: {e}")
        return None
