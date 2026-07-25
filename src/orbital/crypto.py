"""Encryption for App.secrets_toml at rest (issue #73).

`SecretsCipher` is an abstraction over the platform's encryption-key
material, so a future KMS/envelope-encryption backend can replace
`FernetSecretsCipher` without touching call sites in api/apps.py or
k8s/resources.py.
"""

from cryptography.fernet import Fernet

from .config import Settings


class SecretsCipher:
    def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError

    def decrypt(self, ciphertext: str) -> str:
        raise NotImplementedError


class FernetSecretsCipher(SecretsCipher):
    """Authenticated encryption (AES-128-CBC + HMAC) via a single symmetric
    key (Settings.secrets_encryption_key / ORBITAL_SECRETS_ENCRYPTION_KEY)."""

    def __init__(self, key: str):
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()


def _cipher(settings: Settings) -> SecretsCipher:
    return FernetSecretsCipher(settings.secrets_encryption_key)


def encrypt(plaintext: str, settings: Settings) -> str:
    return _cipher(settings).encrypt(plaintext)


def decrypt(ciphertext: str, settings: Settings) -> str:
    return _cipher(settings).decrypt(ciphertext)
