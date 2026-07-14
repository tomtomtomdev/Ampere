"""``AffiliateFeedSource`` — the ToS-safe, *preferred* Shopee product feed (SPEC §6, §11.2).

This is the clean path: an affiliate network (Involve Asia / Accesstrade) that both keeps us inside
ToS and doubles as the monetization channel — its ``tracking_link`` is the outbound affiliate URL
(§11.2). The trade-off (SPEC §6) is that it is **narrower** than the internal endpoint: it gives a
real price + an affiliate link but no reliable Shopee-Mall / seller-trust signals, so those stay
unset rather than fabricated (invariant #4).

> Schema caveat: affiliate access is still an open question, so the exact feed shape is *assumed*
> (a common ``{data:{data:[...], current_page, last_page}}`` product-feed envelope). The mapping is
> deliberately defensive and isolated in ``parse_offer`` — the single place to adjust once a real
> feed is captured. Transport is injected as ``fetch`` (same seam as the internal source).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ampere.adapters.sources._common import (
    Cache,
    InMemoryCache,
    SourceFetchError,
    fetch_with_backoff,
    logger,
)
from ampere.domain.models import RawListing

FEED_URL = "https://api.involve.asia/api/product/all"  # assumed — pending access confirmation


def parse_offer(offer: dict) -> RawListing | None:
    """Map one affiliate offer to a ``RawListing``; ``None`` if id/name/price are missing.

    Prefers the current/sale price over the (possibly higher) list price. Mall/trust are absent by
    design (the feed does not carry them reliably) — left unset, never invented (invariant #4).
    """
    pid = offer.get("product_id") or offer.get("offer_id") or offer.get("id")
    name = offer.get("offer_name") or offer.get("product_name") or offer.get("name")
    price = offer.get("sale_price") or offer.get("price")  # sale price wins; 0/None → list price
    if pid is None or not name or not price:
        return None
    return RawListing(
        shopee_id=str(pid),
        title=str(name),
        brand=(offer.get("brand") or None),
        list_price=int(round(float(price))),  # whole IDR — affiliate feeds are NOT micro-units
        url=(offer.get("tracking_link") or offer.get("product_url")),  # affiliate link (§11.2)
    )


def parse_feed(payload: dict) -> list[RawListing]:
    """Parse one feed page (``{data:{data:[...]}}``) into ``RawListing``\\ s (skips bad rows)."""
    data = payload.get("data")
    rows = data.get("data") if isinstance(data, dict) else data
    out: list[RawListing] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        listing = parse_offer(row)
        if listing is not None:
            out.append(listing)
    return out


class _HttpxFeedFetcher:
    """Best-effort live transport (plain ``httpx`` GET with bearer auth). Not exercised in tests.

    The real Involve Asia API is token-authenticated; wire the token in when access is confirmed.
    Swappable via the ``fetch`` argument without touching parsing/pagination.
    """

    def __init__(
        self, *, url: str = FEED_URL, token: str | None = None, timeout: float = 20.0
    ) -> None:
        self._url = url
        self._token = token
        self._timeout = timeout

    def __call__(self, params: Mapping[str, str]) -> dict:
        import httpx  # lazy: only the live path needs it

        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            resp = httpx.get(self._url, params=dict(params), headers=headers, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise SourceFetchError(str(exc)) from exc


class AffiliateFeedSource:
    """A ``SearchSource`` over the affiliate product feed.

    ``mall_only`` is a no-op here (the feed carries no Mall distinction — documented narrowness,
    SPEC §6); band filtering is applied client-side. Pages are cached and fetched with backoff.
    """

    kind = "affiliate"

    def __init__(
        self,
        *,
        fetch: Callable[[Mapping[str, str]], dict] | None = None,
        cache: Cache | None = None,
        page_size: int = 100,
        max_pages: int = 20,
        max_retries: int = 3,
        base_delay: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._fetch = fetch or _HttpxFeedFetcher()
        self._cache = cache or InMemoryCache()
        self._page_size = page_size
        self._max_pages = max_pages
        self._max_retries = max_retries
        self._base_delay = base_delay
        if sleep is None:
            import time

            sleep = time.sleep
        self._sleep = sleep

    def search(
        self,
        keyword: str,
        price_min: int,
        price_max: int,
        *,
        mall_only: bool = False,
    ) -> list[RawListing]:
        seen: dict[str, RawListing] = {}
        raw_count = 0
        pages = 0
        page = 1
        while pages < self._max_pages:
            payload = self._page(keyword, page)
            listings = parse_feed(payload)
            raw_count += len(listings)
            for listing in listings:
                if price_min <= listing.list_price <= price_max:
                    seen.setdefault(listing.shopee_id, listing)
            pages += 1
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            last_page = data.get("last_page")
            if not listings or (last_page is not None and page >= last_page):
                break
            page += 1

        result = list(seen.values())
        logger.info(
            "affiliate search kw=%r band=%d-%d pages=%d raw=%d in_band=%d",
            keyword, price_min, price_max, pages, raw_count, len(result),
        )
        return result

    def _page(self, keyword: str, page: int) -> dict:
        key = f"affiliate:{keyword}:page={page}:size={self._page_size}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        params = {"keyword": keyword, "page": str(page), "limit": str(self._page_size)}
        payload = fetch_with_backoff(
            self._fetch,
            params,
            max_retries=self._max_retries,
            base_delay=self._base_delay,
            sleep=self._sleep,
        )
        self._cache.set(key, payload)
        return payload
