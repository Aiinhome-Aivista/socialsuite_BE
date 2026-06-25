import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx


def get_media_bytes(url: str) -> bytes:
    """
    Fetches the raw bytes of a media file.
    If the URL points to our local /media endpoint, reads from disk directly
    to avoid a network round-trip.  Otherwise, downloads via HTTP.
    """
    parsed = urlparse(url)
    path = parsed.path  # e.g. "/media/abc123.jpg"

    # Use local disk for any URL whose path is under /media/
    if "/media/" in path:
        filename = path.split("/media/", 1)[-1]
        if filename:
            local_path = Path("media") / filename
            if local_path.exists():
                return local_path.read_bytes()

    # Fallback: HTTP download (needed for external/CDN URLs)
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            return r.content
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to fetch media from {url!r}: {exc}") from exc


def get_media_content_type(url: str) -> str:
    """
    Infers the MIME type of a media file from its URL extension.
    Returns 'application/octet-stream' as fallback.
    """
    path = urlparse(url).path
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def is_video_url(url: str) -> bool:
    """Returns True if the URL appears to be a video file."""
    content_type = get_media_content_type(url)
    return content_type.startswith("video/")