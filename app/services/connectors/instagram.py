"""
Instagram connector — uses the SAME Meta app as Facebook.

Requirements: an Instagram **Business** (or Creator) account linked to a
Facebook Page. Scopes: instagram_basic, instagram_content_publish,
pages_show_list, pages_read_engagement, business_management.

Publishing is two steps and REQUIRES media (Instagram has no text-only post):
  1. POST /{ig-user-id}/media        -> creation_id  (image_url or video_url)
  2. POST /{ig-user-id}/media_publish -> published id
The media URL must be publicly reachable by Meta's servers.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.connectors.base import (
    BaseConnector, TokenBundle, RemoteAccount, MetricsBundle,
)

GRAPH = "https://graph.facebook.com/v21.0"


class InstagramConnector(BaseConnector):
    platform = "instagram"

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        params = {
            "client_id": settings.FACEBOOK_APP_ID,
            "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
            "state": state,
            "scope": (
                "instagram_basic,instagram_content_publish,"
                "pages_show_list,pages_read_engagement,business_management"
            ),
        }
        return "https://www.facebook.com/v21.0/dialog/oauth?" + urlencode(params)

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{GRAPH}/oauth/access_token", params={
                "client_id": settings.FACEBOOK_APP_ID,
                "client_secret": settings.FACEBOOK_APP_SECRET,
                "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
                "code": code,
            })
            r.raise_for_status()
            d = r.json()
        expires = None
        if "expires_in" in d:
            expires = datetime.now(timezone.utc) + timedelta(seconds=d["expires_in"])
        return TokenBundle(access_token=d["access_token"], expires_at=expires)

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        out: list[RemoteAccount] = []
        with httpx.Client(timeout=30) as c:
            pages = c.get(f"{GRAPH}/me/accounts", params={
                "access_token": token.access_token,
                "fields": "id,name,access_token,instagram_business_account",
            }).json().get("data", [])

            for p in pages:
                iga = p.get("instagram_business_account")
                if not iga:
                    continue
                ig_id = iga["id"]
                page_token = p.get("access_token", "")
                detail = c.get(f"{GRAPH}/{ig_id}", params={
                    "access_token": page_token,
                    "fields": "username,profile_picture_url",
                }).json()
                out.append(RemoteAccount(
                    external_id=ig_id,
                    display_name=detail.get("username", p.get("name", "")),
                    avatar_url=detail.get("profile_picture_url", ""),
                    extra={"page_access_token": page_token},
                ))
        return out

    def publish(self, access_token, external_id, body, media, link) -> str:
        if not media:
            raise ValueError("Instagram requires at least one image or video")
        
        import time
        from urllib.parse import urlparse
        from app.config import settings
        
        first = media[0]
        is_video = first.get("type") == "video"
        key = "video_url" if is_video else "image_url"
        
        # Instagram requires a public URL. If we are using localhost/relative URLs, 
        # replace them with the ngrok base URL from settings.
        url = first["url"]
        parsed_url = urlparse(url)
        if parsed_url.hostname in ("localhost", "127.0.0.1") or not parsed_url.hostname:
            base_parsed = urlparse(settings.INSTAGRAM_REDIRECT_URI)
            base_url = f"{base_parsed.scheme}://{base_parsed.netloc}"
            url = base_url + parsed_url.path
        
        with httpx.Client(timeout=120) as c:
            # step 1: create container
            data = {
                "access_token": access_token,
                key: url,
                "caption": body,
            }
            if is_video:
                data["media_type"] = "REELS"
                
            cont = c.post(f"{GRAPH}/{external_id}/media", data=data)
            try:
                cont.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise Exception(f"Instagram media create failed: {e.response.text}") from e
            creation_id = cont.json()["id"]

            # poll container status until it is FINISHED
            for _ in range(15):
                status_res = c.get(f"{GRAPH}/{creation_id}", params={
                    "access_token": access_token,
                    "fields": "status_code"
                })
                status_res.raise_for_status()
                status_code = status_res.json().get("status_code", "FINISHED")
                if status_code == "FINISHED":
                    break
                elif status_code == "ERROR":
                    raise Exception(f"Instagram media container failed with status {status_code}")
                time.sleep(5)

            # step 2: publish container
            pub = c.post(f"{GRAPH}/{external_id}/media_publish", data={
                "access_token": access_token,
                "creation_id": creation_id,
            })
            try:
                pub.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise Exception(f"Instagram media publish failed: {e.response.text}") from e
            return pub.json()["id"]

    def fetch_metrics(self, access_token, external_id) -> MetricsBundle:
        with httpx.Client(timeout=30) as c:
            # Follower count
            r = c.get(f"{GRAPH}/{external_id}", params={
                "access_token": access_token,
                "fields": "followers_count,media_count",
            })
            r.raise_for_status()
            d = r.json()
            followers = d.get("followers_count", 0)

            # Total likes: sum like_count across up to 50 recent media
            total_likes = 0
            try:
                media_r = c.get(f"{GRAPH}/{external_id}/media", params={
                    "access_token": access_token,
                    "fields": "like_count",
                    "limit": 50,
                })
                media_r.raise_for_status()
                for item in media_r.json().get("data", []):
                    total_likes += item.get("like_count", 0)
            except Exception:
                pass  # like count is best-effort

        return MetricsBundle(followers=followers, likes=total_likes)

