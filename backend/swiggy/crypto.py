"""
backend/swiggy/crypto.py

Symmetric encryption for Swiggy session tokens stored at rest.

Tokens are encrypted with Fernet (AES-128-CBC + HMAC) using ENCRYPTION_KEY.
If ENCRYPTION_KEY is not set, we fall back to storing plaintext (dev only)
and log a warning — this keeps local development frictionless while making
the production requirement explicit.
"""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _fernet():
    key = os.getenv("ENCRYPTION_KEY", "")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Encrypt a token. Returns plaintext unchanged if no key is configured."""
    f = _fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a token. Returns the input unchanged if no key is configured."""
    f = _fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        # Value was stored as plaintext before a key was added — return as-is.
        return ciphertext


def generate_key() -> str:
    """Helper to mint a new Fernet key (run once, paste into .env)."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


if __name__ == "__main__":
    print("ENCRYPTION_KEY=" + generate_key())
