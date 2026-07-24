"""
sapt.config.keystore
Encrypted API key storage using Fernet symmetric encryption.
Derives encryption key from machine-id + username so keys are
not stored in plain text, while avoiding desktop keyring dependencies.
"""

import base64
import hashlib
import getpass

from cryptography.fernet import Fernet, InvalidToken

from sapt.utils.system import get_machine_id


class KeyStore:
    """Encrypt/decrypt API keys using a machine-derived key."""

    def __init__(self):
        self._fernet = Fernet(self._derive_key())

    def encrypt(self, api_key: str) -> str:
        """Encrypt an API key and return base64-encoded ciphertext."""
        return self._fernet.encrypt(api_key.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        """Decrypt an encrypted API key.

        Returns the plain-text key, or raises ValueError if decryption fails.
        """
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except InvalidToken:
            raise ValueError(
                "Failed to decrypt API key. This can happen if the config "
                "was created on a different machine or by a different user. "
                "Run 'sapt config --reset' to reconfigure."
            )

    def _derive_key(self) -> bytes:
        """Derive a Fernet key from machine-id + username.

        This isn't perfect security (someone with access to the machine
        can derive the same key), but it prevents plain-text key storage
        and protects against casual file-copying between machines.
        """
        machine_id = get_machine_id()
        username = getpass.getuser()
        seed = f"sapt::{machine_id}::{username}::v1".encode()

        # SHA-256 → 32 bytes → base64-encode for Fernet
        digest = hashlib.sha256(seed).digest()
        return base64.urlsafe_b64encode(digest)

    @staticmethod
    def mask_key(api_key: str) -> str:
        """Mask an API key for display (e.g., sk-ant-***...***3fgh)."""
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return api_key[:6] + "*" * (len(api_key) - 10) + api_key[-4:]
