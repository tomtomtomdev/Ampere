"""Shared transport infrastructure for the live ``SearchSource`` adapters (SPEC §6).

The fragile/networked part of a source (Shopee's expiring anti-bot headers, Involve-Asia auth) is
kept behind an injectable ``fetch`` callable so the parsing + pagination logic is unit-testable
offline (shopee-marketplace skill guidance). This module holds the cross-source concerns that live
*around* that callable: caching hard (daily cadence, SPEC §6), bounded backoff on transient
failures, and a single retryable-error type. Everything here is pure orchestration — no I/O of its
own beyond the optional on-disk cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger("ampere.sources")


class SourceFetchError(Exception):
    """A transient transport failure worth retrying (bad status, timeout, network blip).

    Live fetchers translate their transport's errors into this so sources retry uniformly without
    knowing the transport. A non-retryable programming error should NOT be raised as this type.
    """


@runtime_checkable
class Cache(Protocol):
    """A raw-page cache keyed by a request signature. Values are decoded JSON payloads."""

    def get(self, key: str) -> dict | None: ...

    def set(self, key: str, value: dict) -> None: ...


class InMemoryCache:
    """Process-lifetime cache (the default). Enough to dedup pages within one run."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self._store.get(key)

    def set(self, key: str, value: dict) -> None:
        self._store[key] = value


class JsonFileCache:
    """On-disk cache so re-runs (or a same-day re-trigger) don't re-hit the source — "cache hard"
    (SPEC §6). One JSON file per request signature; the daily cadence is the freshness policy."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self._dir / f"{digest}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, key: str, value: dict) -> None:
        self._path(key).write_text(json.dumps(value), encoding="utf-8")


def fetch_with_backoff(
    fetch: Callable[[Mapping[str, str]], dict],
    params: Mapping[str, str],
    *,
    max_retries: int,
    base_delay: float,
    sleep: Callable[[float], None],
) -> dict:
    """Call ``fetch(params)``, retrying ``SourceFetchError`` with exponential backoff.

    Up to ``max_retries`` retries (so ``max_retries + 1`` attempts). ``sleep`` is injected so tests
    never actually wait. Non-``SourceFetchError`` exceptions propagate immediately (they are bugs,
    not transient failures).
    """
    attempt = 0
    while True:
        try:
            return fetch(params)
        except SourceFetchError:
            if attempt >= max_retries:
                logger.warning("source fetch failed after %d retries", max_retries)
                raise
            sleep(base_delay * (2**attempt))
            attempt += 1
