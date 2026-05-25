import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

class EncryptionUtils:
    _fernet = None

    @classmethod
    def _get_fernet(cls):
        if cls._fernet is None:
            key = os.getenv("ENCRYPTION_KEY")
            if not key:
                raise RuntimeError("ENCRYPTION_KEY is required; refusing to use exchange-key encryption without it.")
            cls._fernet = Fernet(key.encode())
        return cls._fernet

    @classmethod
    def encrypt(cls, text: str) -> str:
        if not text:
            return None
        f = cls._get_fernet()
        return f.encrypt(text.encode()).decode()

    @classmethod
    def decrypt(cls, encrypted_text: str) -> str:
        if not encrypted_text:
            return None
        f = cls._get_fernet()
        try:
            return f.decrypt(encrypted_text.encode()).decode()
        except Exception:
            return None
