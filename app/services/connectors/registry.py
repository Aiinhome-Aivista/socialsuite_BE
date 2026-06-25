"""
Registry of platform connectors. Facebook, Instagram, LinkedIn, X and YouTube
are implemented. Pinterest remains a stub — implement it against base.py using
the others as templates (standard OAuth2, no PKCE).
"""
from app.services.connectors.base import BaseConnector
from app.services.connectors.facebook import FacebookConnector
from app.services.connectors.instagram import InstagramConnector
from app.services.connectors.linkedin import LinkedInConnector
from app.services.connectors.x import XConnector
from app.services.connectors.youtube import YouTubeConnector
from app.services.connectors.pinterest import PinterestConnector


class _NotImplementedConnector(BaseConnector):
    def __init__(self, platform: str):
        self.platform = platform

    def _todo(self):
        raise NotImplementedError(f"{self.platform} connector not implemented yet")

    def authorize_url(self, state, code_challenge=None): self._todo()
    def exchange_code(self, code, code_verifier=None): self._todo()
    def fetch_accounts(self, token): self._todo()
    def publish(self, access_token, external_id, body, media, link): self._todo()
    def fetch_metrics(self, access_token, external_id): self._todo()


_REGISTRY: dict[str, BaseConnector] = {
    "facebook": FacebookConnector(),
    "instagram": InstagramConnector(),
    "linkedin": LinkedInConnector(),
    "x": XConnector(),
    "youtube": YouTubeConnector(),
    "pinterest": PinterestConnector(),
}


def get_connector(platform: str) -> BaseConnector:
    if platform not in _REGISTRY:
        raise ValueError(f"Unknown platform: {platform}")
    return _REGISTRY[platform]
