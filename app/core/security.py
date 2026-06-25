from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError
from cryptography.fernet import Fernet

from app.config import settings

ALGORITHM = "HS256"


# ---------- Passwords ----------
def hash_password(password: str) -> str:
    # Use bcrypt directly to avoid passlib issues with bcrypt >= 4.0.0
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------- JWT ----------
def create_access_token(subject: str, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ---------- OAuth token encryption at rest ----------
# Social access/refresh tokens must never be stored in plaintext.
_fernet = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode()) if settings.TOKEN_ENCRYPTION_KEY else None


def encrypt_token(token: str) -> str:
    if not _fernet:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(token_enc: str) -> str:
    if not _fernet:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    return _fernet.decrypt(token_enc.encode()).decode()