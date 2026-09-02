"""Shared HTTP session/retry helpers."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(
    *,
    retries: int = 5,
    backoff_factor: float = 0.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
    headers: dict[str, str] | None = None,
) -> requests.Session:
    """Create a requests session with consistent retry behavior."""

    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
        respect_retry_after_header=True,
        allowed_methods=frozenset({"GET", "HEAD", "OPTIONS"}),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if headers:
        session.headers.update(headers)
    return session
