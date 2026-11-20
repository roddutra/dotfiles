#!/usr/bin/env python3
"""Small HTTP helpers over the standard library, shared by the adapters."""

import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

USER_AGENT = "video-watcher-skill"
RETRY_STATUSES = (429, 500, 502, 503, 504)


class ApiError(Exception):
    """An HTTP or transport failure, with whatever the server said."""

    def __init__(self, status: int | None, message: str, body: str = ""):
        super().__init__(message)
        self.status = status
        self.message = message
        self.body = body


def _error_message(status: int, body: str) -> str:
    try:
        parsed = json.loads(body)
    except ValueError:
        return f"HTTP {status}: {body[:500].strip()}"
    error = parsed.get("error", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(error, dict):
        detail = error.get("message") or error.get("status") or json.dumps(error)[:500]
        return f"HTTP {status}: {detail}"
    return f"HTTP {status}: {str(error)[:500]}"


def request(
    method: str,
    url: str,
    headers: dict | None = None,
    body: bytes | None = None,
    timeout: float = 120,
    retries: int = 3,
):
    """Send one request. Returns (status, response headers, body bytes).

    Retries rate limits, 5xx and dropped connections with backoff. Raises
    ApiError for anything else that is not a 2xx. Request headers never
    appear in an error, so a key cannot leak through one.
    """
    all_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(url, data=body, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            if exc.code in RETRY_STATUSES and attempt <= retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise ApiError(exc.code, _error_message(exc.code, text), text) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if attempt <= retries:
                time.sleep(min(2 ** attempt, 30))
                continue
            reason = getattr(exc, "reason", exc)
            raise ApiError(None, f"Could not reach {urlsplit(url).hostname}: {reason}") from None


def request_json(
    method: str,
    url: str,
    headers: dict | None = None,
    payload=None,
    timeout: float = 120,
    retries: int = 3,
):
    """JSON in, JSON out. Returns (parsed body or {}, response headers)."""
    send_headers = dict(headers or {})
    body = None
    if payload is not None:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        send_headers.setdefault("Content-Type", "application/json")
    _, response_headers, raw = request(method, url, send_headers, body, timeout, retries)
    if not raw.strip():
        return {}, response_headers
    try:
        return json.loads(raw), response_headers
    except ValueError:
        raise ApiError(None, f"Expected JSON from {method} {url.split('?')[0]}, got: {raw[:200]!r}") from None
