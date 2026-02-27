"""
Symmetric encryption for storing sensitive credentials (IMAP passwords).
Key is generated once and stored in data/secret.key inside the project folder.
Nothing is ever written outside the project folder.
"""
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from app.config import SECRET_KEY_PATH


def _get_or_create_key() -> bytes:
    """Load the Fernet key or generate a new one."""
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_PATH.write_bytes(key)
    return key


def _fernet() -> Fernet:
    return Fernet(_get_or_create_key())


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string and return a base64-safe ciphertext string."""
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return base64.urlsafe_b64encode(token).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string back to plaintext."""
    raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    return _fernet().decrypt(raw).decode("utf-8")
