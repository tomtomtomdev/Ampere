"""``InternalEndpointSource`` — Shopee's reverse-engineered ``search_items`` endpoint (SPEC Appendix
A, shopee-marketplace skill).

This is the *fragile, best-effort, ToS-sensitive* path (prefer the affiliate feed where it
suffices). The concrete contract — endpoint, ``fe_filter_options`` (Mall + price ``▶◀`` band),
micro-unit prices, the ``item_basic`` field map — is HAR-verified and lives here.

The live transport is intentionally NOT baked in: Shopee's ``search_items`` requests carry signed,
device-fingerprinted headers minted by an anti-bot SDK that expire, so the robust production
transport drives a logged-in browser session (Playwright with a persisted profile — Appendix A).
That transport is injected as ``fetch``; the default is a plain-``httpx`` best-effort fetcher.
Everything below the transport (``parse_item`` / pagination / filtering / dedup / caching / backoff)
is pure and unit-tested offline against saved-shape payloads.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping

from ampere.adapters.sources._common import (
    Cache,
    InMemoryCache,
    SourceFetchError,
    fetch_with_backoff,
    logger,
)
from ampere.domain.models import RawListing

SEARCH_URL = "https://shopee.co.id/api/v4/search/search_items"
PAGE_LIMIT = 60  # what the Shopee web app itself uses (Appendix A)
PRICE_DELIM = "▶◀"  # the literal ▶◀ price-range delimiter, min▶◀max in whole IDR
_MICRO = 100_000  # prices are micro-units: 185900000000 → Rp 1,859,000

# RAM/ROM in a tier_variations option: "8/256", "8GB/256GB", "RAM 6GB / 128GB". GB tokens optional.
_VARIANT_RE = re.compile(r"(\d+)\s*(?:gb)?\s*/\s*(\d+)\s*(?:gb)?", re.IGNORECASE)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def _extract_variant(tier_variations: object) -> str | None:
    """Pull a normalized ``RAM/ROM`` from any variation axis; ignore color/other axes (Appendix A).

    Scans every option string (axis name + format both vary) and returns the first RAM/ROM pair as
    seen — magnitude normalization (``256/8`` → ``8/256``) is the resolver's job (M2), not ours.
    """
    if not isinstance(tier_variations, list):
        return None
    for axis in tier_variations:
        if not isinstance(axis, dict):
            continue
        for opt in axis.get("options") or []:
            match = _VARIANT_RE.search(str(opt))
            if match:
                return f"{match.group(1)}/{match.group(2)}"
    return None


def parse_item(item_basic: dict) -> RawListing | None:
    """Map one HAR-verified ``item_basic`` object to a source-agnostic ``RawListing``.

    Returns ``None`` for a row missing the identity/price essentials. ``price_before_discount``
    (harga coret) is deliberately never read — it is marketing fiction (§5.7). Absent trust signals
    stay ``None``/``False``; we never fabricate them (invariant #4).
    """
    itemid = item_basic.get("itemid")
    price = item_basic.get("price")
    if itemid is None or price is None:
        return None

    shopid = item_basic.get("shopid")
    rating = item_basic.get("item_rating") or {}
    counts = rating.get("rating_count") or []
    return RawListing(
        shopee_id=str(itemid),
        title=item_basic.get("name") or "",
        brand=(item_basic.get("brand") or None),
        variant_raw=_extract_variant(item_basic.get("tier_variations")),
        list_price=int(price) // _MICRO,
        is_mall=bool(
            item_basic.get("is_official_shop") or item_basic.get("show_official_shop_label")
        ),
        seller_rating=rating.get("rating_star"),
        seller_review_count=(counts[0] if counts else None),  # index 0 = total (Appendix A)
        is_star_seller=bool(item_basic.get("is_preferred_plus_seller")),
        historical_sold=item_basic.get("historical_sold") or item_basic.get("sold"),
        shop_location=item_basic.get("shop_location"),
        can_use_cod=bool(item_basic.get("can_use_cod")),
        url=(f"https://shopee.co.id/product/{shopid}/{itemid}" if shopid is not None else None),
    )


def parse_search_items(payload: dict) -> list[RawListing]:
    """Parse a full ``search_items`` response into ``RawListing``\\ s (skips malformed rows)."""
    out: list[RawListing] = []
    for entry in payload.get("items") or []:
        if not isinstance(entry, dict):
            continue
        basic = entry.get("item_basic")
        if not isinstance(basic, dict):
            continue
        listing = parse_item(basic)
        if listing is not None:
            out.append(listing)
    return out


class _HttpxPageFetcher:
    """Best-effort live transport (plain ``httpx`` GET). Kept simple on purpose.

    NOTE: this will hit Shopee's anti-bot wall once its signed headers are required — it is the
    low-effort default, not the robust path. The robust ``InternalEndpointSource`` transport drives
    a logged-in Playwright session so tokens are minted for you (SPEC Appendix A); drop such a
    fetcher in via ``fetch`` without touching any parsing/pagination code. Not exercised in tests.
    """

    def __init__(self, *, url: str = SEARCH_URL, timeout: float = 20.0) -> None:
        self._url = url
        self._timeout = timeout

    def __call__(self, params: Mapping[str, str]) -> dict:
        import httpx  # lazy: only the live path needs it

        headers = {
            "User-Agent": _UA,
            "Referer": "https://shopee.co.id/",
            "Accept": "application/json",
        }
        try:
            resp = httpx.get(self._url, params=dict(params), headers=headers, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:  # transient → retryable
            raise SourceFetchError(str(exc)) from exc


class InternalEndpointSource:
    """A ``SearchSource`` over Shopee's internal ``search_items`` endpoint (Appendix A).

    One ``search`` is a single bounded pagination burst per keyword (low volume, cache hard — the
    daily cadence is the safety margin). Pages are cached and fetched with backoff; every page is
    parsed then band-filtered client-side (defensive — variant price ranges can leak out of band).
    """

    kind = "internal"

    def __init__(
        self,
        *,
        fetch: Callable[[Mapping[str, str]], dict] | None = None,
        cache: Cache | None = None,
        max_pages: int = 12,
        max_retries: int = 3,
        base_delay: float = 1.0,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._fetch = fetch or _HttpxPageFetcher()
        self._cache = cache or InMemoryCache()
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
        fe = self._fe_filter_options(price_min, price_max, mall_only)
        seen: dict[str, RawListing] = {}
        raw_count = 0
        pages = 0
        offset = 0
        while pages < self._max_pages:
            payload = self._page(keyword, price_min, price_max, mall_only, fe, offset)
            listings = parse_search_items(payload)
            raw_count += len(listings)
            for listing in listings:
                if price_min <= listing.list_price <= price_max:
                    seen.setdefault(listing.shopee_id, listing)  # dedup by shopee_id, first wins
            pages += 1
            offset += PAGE_LIMIT
            if payload.get("nomore") or not payload.get("items"):
                break
            total = payload.get("total_count")
            if total is not None and offset >= total:
                break

        result = list(seen.values())
        logger.info(
            "internal search kw=%r band=%d-%d mall=%s pages=%d raw=%d in_band=%d",
            keyword, price_min, price_max, mall_only, pages, raw_count, len(result),
        )
        return result

    def _page(
        self, keyword: str, price_min: int, price_max: int, mall_only: bool, fe: str, offset: int
    ) -> dict:
        key = f"internal:{keyword}:{price_min}-{price_max}:mall={mall_only}:off={offset}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        payload = fetch_with_backoff(
            self._fetch,
            self._params(keyword, fe, offset),
            max_retries=self._max_retries,
            base_delay=self._base_delay,
            sleep=self._sleep,
        )
        self._cache.set(key, payload)
        return payload

    @staticmethod
    def _fe_filter_options(price_min: int, price_max: int, mall_only: bool) -> str:
        """Build the ``fe_filter_options`` JSON: Mall filter (the "new" proxy) + the price band."""
        groups: list[dict] = []
        if mall_only:
            groups.append({"group_name": "SHOP_TYPE", "values": ["OFFICIAL_MALL"]})
        groups.append(
            {"group_name": "PRICE_RANGE", "values": [f"{price_min}{PRICE_DELIM}{price_max}"]}
        )
        return json.dumps(groups, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _params(keyword: str, fe: str, offset: int) -> dict[str, str]:
        return {
            "keyword": keyword,
            "limit": str(PAGE_LIMIT),
            "newest": str(offset),  # pagination OFFSET, not a page index (Appendix A)
            "by": "relevancy",
            "order": "desc",
            "page_type": "search",
            "scenario": "PAGE_GLOBAL_SEARCH",
            "source": "SRP",
            "version": "2",
            "fe_filter_options": fe,
        }
