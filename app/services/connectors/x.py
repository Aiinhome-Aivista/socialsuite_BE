"""
X (Twitter) connector — OAuth2 with PKCE, posting via API v2.

Requires an X developer app on a **paid API tier** (the free tier does not allow
posting at meaningful volume). Scopes: tweet.read tweet.write users.read
offline.access.

Media (images/video) uploads use the v1.1 media/upload endpoint, then the
returned media_ids are attached to the v2 tweet. Text posting is implemented
fully; the media step is noted inline.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.connectors.base import (
    BaseConnector, TokenBundle, RemoteAccount, MetricsBundle,
)

AUTH = "https://twitter.com/i/oauth2/authorize"
TOKEN = "https://api.twitter.com/2/oauth2/token"
API = "https://api.twitter.com/2"


class XConnector(BaseConnector):
    platform = "x"
    uses_pkce = True

    def _basic_auth_header(self) -> dict:
        raw = f"{settings.X_CLIENT_ID}:{settings.X_CLIENT_SECRET}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.X_CLIENT_ID,
            "redirect_uri": settings.X_REDIRECT_URI,
            "scope": "tweet.read tweet.write users.read offline.access",
            "state": state,
            "code_challenge": code_challenge or "",
            "code_challenge_method": "S256",
        }
        return f"{AUTH}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.X_REDIRECT_URI,
                "code_verifier": code_verifier or "",
                "client_id": settings.X_CLIENT_ID,
            }, headers={
                **self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 7200))
        return TokenBundle(d["access_token"], d.get("refresh_token"), expires)

    def refresh(self, token: TokenBundle) -> TokenBundle:
        if not token.refresh_token:
            return token
        with httpx.Client(timeout=30) as c:
            r = c.post(TOKEN, data={
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": settings.X_CLIENT_ID,
            }, headers={
                **self._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            })
            r.raise_for_status()
            d = r.json()
        expires = datetime.now(timezone.utc) + timedelta(seconds=d.get("expires_in", 7200))
        return TokenBundle(d["access_token"], d.get("refresh_token", token.refresh_token), expires)

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{API}/users/me",
                      params={"user.fields": "profile_image_url,username"},
                      headers={"Authorization": f"Bearer {token.access_token}"})
            r.raise_for_status()
            d = r.json()["data"]
        return [RemoteAccount(
            external_id=d["id"],
            display_name=f"@{d.get('username', '')}",
            avatar_url=d.get("profile_image_url", ""),
        )]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def publish(self, access_token, external_id, body, media, link) -> str:
        payload: dict = {"text": body if not link else f"{body}\n{link}"}
        # For media: upload via v1.1 media/upload, then:
        # payload["media"] = {"media_ids": [uploaded_id, ...]}
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{API}/tweets", json=payload,
                       headers={"Authorization": f"Bearer {access_token}"})
            r.raise_for_status()
            return r.json()["data"]["id"]

    def fetch_metrics(self, access_token, external_id) -> MetricsBundle:
        with httpx.Client(timeout=30) as c:
            # Follower count from user public metrics
            r = c.get(f"{API}/users/me",
                      params={"user.fields": "public_metrics"},
                      headers={"Authorization": f"Bearer {access_token}"})
            r.raise_for_status()
            pm = r.json()["data"].get("public_metrics", {})
            followers = pm.get("followers_count", 0)

            # Total likes: sum like_count from up to 100 recent tweets
            total_likes = 0
            try:
                user_id = r.json()["data"]["id"]
                tweets_r = c.get(f"{API}/users/{user_id}/tweets", params={
                    "tweet.fields": "public_metrics",
                    "max_results": 100,
                }, headers={"Authorization": f"Bearer {access_token}"})
                tweets_r.raise_for_status()
                for tweet in tweets_r.json().get("data", []):
                    total_likes += tweet.get("public_metrics", {}).get("like_count", 0)
            except Exception:
                pass  # like count is best-effort; free tier may not allow timeline reads

        return MetricsBundle(followers=followers, likes=total_likes)

