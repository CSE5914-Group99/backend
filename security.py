"""Password hashing utilities."""
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    # bcrypt has a 72-byte input limit. Truncate UTF-8 bytes defensively to avoid
    # ValueError from the underlying bcrypt implementation.
    if password is None:
        raise ValueError("password must not be None")
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    return _pwd_context.hash(pw_bytes)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if plain_password is None:
        return False
    pw_bytes = plain_password.encode("utf-8")
    if len(pw_bytes) > 72:
        pw_bytes = pw_bytes[:72]
    return _pwd_context.verify(pw_bytes, hashed_password)
