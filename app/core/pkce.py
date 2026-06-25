"""PKCE (RFC 7636) helpers — required by X (Twitter) OAuth2."""
import base64
import hashlib
import os


def generate_pkce_pair() -> tuple[str, str]:
    """Returns (code_verifier, code_challenge)."""
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def random_state() -> str:
    return base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("=")
