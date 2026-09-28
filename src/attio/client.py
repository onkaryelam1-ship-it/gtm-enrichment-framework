"""Minimal Attio REST client: auth, throttling, retries, readable errors.

Attio allows about 25 writes and 100 reads per second. The client spaces requests
out, retries 429s using the Retry-After header, and backs off on 5xx errors.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

BASE_URL = "https://api.attio.com/v2"


class AttioError(Exception):
    def __init__(self, status: int, body: dict | str, method: str, path: str):
        self.status = status
        self.body = body
        msg = body.get("message") if isinstance(body, dict) else str(body)
        self.code = body.get("code") if isinstance(body, dict) else None
        super().__init__(f"{method} {path} -> {status}: {msg}")

    @property
    def message(self) -> str:
        return self.body.get("message", "") if isinstance(self.body, dict) else str(self.body)


def retry_after_seconds(value: str | None, default: float = 1.0) -> float:
    """Retry-After may be a number of seconds or an HTTP date. Return seconds to wait."""
    if not value:
        return default
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return default


class AttioClient:
    def __init__(self, api_key: str, writes_per_sec: float = 20, max_retries: int = 5,
                 session: requests.Session | None = None):
        if not api_key:
            raise ValueError("ATTIO_API_KEY is empty. Add it to .env, or run with --dry-run.")
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        self.min_interval = 1.0 / writes_per_sec
        self.max_retries = max_retries
        self._last = 0.0
        self.calls = 0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def request(self, method: str, path: str, params: dict | None = None,
                json: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        for attempt in range(self.max_retries + 1):
            self._throttle()
            self.calls += 1
            resp = self.session.request(method, url, params=params, json=json, timeout=30)
            if resp.status_code == 429 and attempt < self.max_retries:
                time.sleep(retry_after_seconds(resp.headers.get("Retry-After")) + 0.05)
                continue
            if resp.status_code >= 500 and attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 20))
                continue
            try:
                body = resp.json() if resp.content else {}
            except ValueError:
                body = resp.text
            if resp.status_code >= 400:
                raise AttioError(resp.status_code, body, method, path)
            return body
        raise AttioError(429, "retries exhausted", method, path)  # pragma: no cover
