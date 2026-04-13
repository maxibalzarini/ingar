"""
Ingar - Módulo de cifrado AES-256-GCM.

Cada sesión genera su propia clave de 256 bits.
Los datos cifrados tienen el formato: nonce (12 bytes) + ciphertext + tag (16 bytes).
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SessionCrypto:
    """Cifrado simétrico AES-256-GCM para una sesión."""

    def __init__(self, key: bytes | None = None):
        self._key = key if key is not None else os.urandom(32)
        self._aesgcm = AESGCM(self._key)

    # ------------------------------------------------------------------
    # Serialización de clave
    # ------------------------------------------------------------------

    @property
    def key_b64(self) -> str:
        return base64.urlsafe_b64encode(self._key).decode()

    @classmethod
    def from_key_b64(cls, key_b64: str) -> "SessionCrypto":
        key = base64.urlsafe_b64decode(key_b64.encode())
        return cls(key=key)

    # ------------------------------------------------------------------
    # Cifrar / descifrar
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: bytes) -> bytes:
        """Cifra datos y devuelve nonce + ciphertext (con tag incluido)."""
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        """Descifra datos con formato nonce + ciphertext."""
        nonce = data[:12]
        ciphertext = data[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None)

    # ------------------------------------------------------------------
    # Conveniencia: encrypt/decrypt de strings base64
    # ------------------------------------------------------------------

    def encrypt_b64(self, plaintext: bytes) -> str:
        return base64.b64encode(self.encrypt(plaintext)).decode()

    def decrypt_b64(self, data_b64: str) -> bytes:
        return self.decrypt(base64.b64decode(data_b64))
