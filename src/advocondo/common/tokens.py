import hashlib
import secrets

TOKEN_BYTES = 32


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Only this hash is stored, so a leaked database does not leak usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()
