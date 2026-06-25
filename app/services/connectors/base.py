"""
Every social platform implements this interface. The rest of the app (publisher,
connector routes, analytics worker) only talks to BaseConnector, so adding a new
network = writing one subclass.

OAuth flow:
  1. authorize_url(state)        -> redirect the user to the platform
  2. exchange_code(code)         -> returns TokenBundle after callback
  3. fetch_accounts(token)       -> list of pages/profiles the user granted

Publishing:
  4. publish(account, post)      -> returns external_post_id

Analytics:
  5. fetch_metrics(account)      -> MetricsBundle
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class RemoteAccount:
    external_id: str
    display_name: str
    avatar_url: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class MetricsBundle:
    followers: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0
    watch_time_seconds: int = 0
    demographics: dict = field(default_factory=dict)


class BaseConnector(ABC):
    platform: str = "base"
    uses_pkce: bool = False   # X sets this True

    @abstractmethod
    def authorize_url(self, state: str, code_challenge: str | None = None) -> str: ...

    @abstractmethod
    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle: ...

    @abstractmethod
    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]: ...

    @abstractmethod
    def publish(self, access_token: str, external_id: str, body: str,
                media: list[dict], link: str | None) -> str: ...

    @abstractmethod
    def fetch_metrics(self, access_token: str, external_id: str) -> MetricsBundle: ...

    # Optional: override when the platform supports refresh tokens
    def refresh(self, token: TokenBundle) -> TokenBundle:
        return token
