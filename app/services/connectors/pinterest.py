"""
Pinterest connector.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.connectors.base import (
    BaseConnector, TokenBundle, RemoteAccount, MetricsBundle,
)

PINTEREST_API = (
    "https://api-sandbox.pinterest.com/v5"
    if settings.PINTEREST_ENV == "sandbox"
    else "https://api.pinterest.com/v5"
)

class PinterestConnector(BaseConnector):
    platform = "pinterest"

    def authorize_url(self, state: str, code_challenge: str | None = None) -> str:
        params = {
            "client_id": settings.PINTEREST_APP_ID,
            "redirect_uri": settings.PINTEREST_REDIRECT_URI,
            "response_type": "code",
            "scope": "boards:read,boards:write,pins:read,pins:write,user_accounts:read,video:write",
            "state": state,
        }
        return "https://www.pinterest.com/oauth/?" + urlencode(params)

    def exchange_code(self, code: str, code_verifier: str | None = None) -> TokenBundle:
        auth_string = f"{settings.PINTEREST_APP_ID}:{settings.PINTEREST_APP_SECRET}"
        auth_header = base64.b64encode(auth_string.encode()).decode()

        with httpx.Client(timeout=30) as c:
            r = c.post(f"{PINTEREST_API}/oauth/token", headers={
                "Authorization": f"Basic {auth_header}",
                "Content-Type": "application/x-www-form-urlencoded"
            }, data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.PINTEREST_REDIRECT_URI,
            })
            r.raise_for_status()
            data = r.json()

        expires = None
        if "expires_in" in data:
            expires = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        
        return TokenBundle(
            access_token=data["access_token"], 
            refresh_token=data.get("refresh_token"),
            expires_at=expires
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Like raise_for_status() but includes the Pinterest response body in the message."""
        if response.is_error:
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:500]
            raise httpx.HTTPStatusError(
                f"Pinterest API error {response.status_code} for {response.url} — {detail}",
                request=response.request,
                response=response,
            )

    def fetch_accounts(self, token: TokenBundle) -> list[RemoteAccount]:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{PINTEREST_API}/user_account", headers={
                "Authorization": f"Bearer {token.access_token}"
            })
            r.raise_for_status()
            data = r.json()
            
        return [
            RemoteAccount(
                external_id=data.get("username", "unknown"),
                display_name=data.get("username", "Pinterest Account"),
                avatar_url=data.get("profile_image", ""),
                extra={}
            )
        ]

    def _get_or_create_board(self, c: httpx.Client, access_token: str) -> str:
        """Return the first board ID, creating a default board if the user has none."""
        r_boards = c.get(f"{PINTEREST_API}/boards", headers={
            "Authorization": f"Bearer {access_token}"
        })
        self._raise_for_status(r_boards)
        items = r_boards.json().get("items", [])

        if not items:
            r_create = c.post(f"{PINTEREST_API}/boards", headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }, json={"name": "Social Suite", "description": "Pins from Social Suite"})
            self._raise_for_status(r_create)
            return r_create.json()["id"]

        return items[0]["id"]

    def _upload_video(self, c: httpx.Client, access_token: str, media_bytes: bytes, filename: str) -> str:
        """
        Upload a video to Pinterest using the 4-step async media upload workflow:
          1. Register media  →  2. Upload to S3  →  3. Poll until processed  →  return media_id
        """
        import time

        # Step 1 — Register the media upload
        r_reg = c.post(f"{PINTEREST_API}/media", headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }, json={"media_type": "video"})
        self._raise_for_status(r_reg)
        reg = r_reg.json()
        media_id = reg["media_id"]
        upload_url = reg["upload_url"]
        upload_parameters: dict = reg.get("upload_parameters", {})

        # Step 2 — Upload the .mp4 to Pinterest's S3 bucket (no Auth header needed)
        fields = {k: (None, v) for k, v in upload_parameters.items()}
        fields["file"] = (filename, media_bytes, "video/mp4")

        # Use a fresh client without default headers so we don't send the Bearer token to S3
        with httpx.Client(timeout=300) as s3_client:
            r_s3 = s3_client.post(upload_url, files=fields)
        self._raise_for_status(r_s3)

        # Step 3 — Poll until Pinterest finishes processing the video (max ~5 minutes)
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        for _ in range(60):          # 60 × 5 s = 5 min max
            time.sleep(5)
            r_status = c.get(f"{PINTEREST_API}/media/{media_id}", headers=auth_headers)
            self._raise_for_status(r_status)
            status = r_status.json().get("status", "")
            if status == "succeeded":
                return media_id
            if status == "failed":
                raise RuntimeError(f"Pinterest video processing failed for media_id={media_id}")

        raise TimeoutError(f"Pinterest video processing timed out for media_id={media_id}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        # Only retry on transient network errors (connection reset, DNS failure etc.).
        # HTTPStatusError (4xx/5xx), RuntimeError, TimeoutError, ValueError are
        # permanent failures — retrying them just produces a confusing RetryError wrapper.
        retry=retry_if_exception_type(httpx.NetworkError),
        reraise=True,  # always re-raise the original exception, never wrap in RetryError
    )
    def publish(self, access_token, external_id, body, media, link) -> str:
        if not media:
            raise ValueError("Pinterest requires at least one image/media URL to publish a pin.")

        from app.services.media_helper import get_media_bytes

        media_url: str = media[0]["url"]
        media_bytes = get_media_bytes(media_url)
        is_video = media_url.lower().endswith((".mp4", ".mov", ".m4v"))

        with httpx.Client(
            # No overall timeout — video polling can legitimately take several minutes.
            # Each individual request still has a per-request timeout.
            timeout=httpx.Timeout(connect=10, read=60, write=120, pool=10),
        ) as c:
            board_id = self._get_or_create_board(c, access_token)

            if is_video:
                # Pinterest video pin — multi-step async upload
                filename = media_url.split("/")[-1] or "video.mp4"
                media_id = self._upload_video(c, access_token, media_bytes, filename)
                media_source = {
                    "source_type": "video_id",
                    "media_id": media_id,
                    # Pinterest requires a cover image for videos. We tell it to extract frame 0.
                    "cover_image_key_frame_time": 0,
                }
            else:
                # Pinterest image pin — base64 inline upload
                b64_data = base64.b64encode(media_bytes).decode("utf-8")
                content_type = "image/jpeg"
                if media_url.lower().endswith(".png"):
                    content_type = "image/png"
                elif media_url.lower().endswith(".webp"):
                    content_type = "image/webp"
                media_source = {
                    "source_type": "image_base64",
                    "content_type": content_type,
                    "data": b64_data,
                }

            payload: dict = {
                "board_id": board_id,
                "description": body,
                "media_source": media_source,
            }
            if link:
                payload["link"] = link

            r_pin = c.post(f"{PINTEREST_API}/pins", headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }, json=payload)
            self._raise_for_status(r_pin)

            return r_pin.json().get("id", "")

    def fetch_metrics(self, access_token, external_id) -> MetricsBundle:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{PINTEREST_API}/user_account", headers={
                "Authorization": f"Bearer {access_token}"
            })
            if r.status_code == 200:
                data = r.json()
                return MetricsBundle(followers=data.get("follower_count", 0))
        return MetricsBundle(followers=0)
