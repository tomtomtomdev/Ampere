"""SearchSource port — the swappable listing source (SPEC §6, SC4).

Every implementation (``AffiliateFeedSource``, ``InternalEndpointSource``, ``FixtureSource``)
satisfies this identical contract and passes the same contract test suite (invariant #5). Scoring
and UI must never learn which source produced a listing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ampere.domain.models import RawListing


@runtime_checkable
class SearchSource(Protocol):
    """A daily listing feed for one keyword within a price band."""

    kind: str  # "affiliate" | "internal" | "fixture" — recorded in runs.source_kind

    def search(
        self,
        keyword: str,
        price_min: int,
        price_max: int,
        *,
        mall_only: bool = False,
    ) -> list[RawListing]:
        """Return raw listings for ``keyword`` within ``[price_min, price_max]`` (whole IDR).

        ``mall_only`` maps to Shopee's ``SHOP_TYPE=OFFICIAL_MALL`` filter — the practical "new"
        proxy (SPEC Appendix A). Implementations own caching/backoff; callers assume it may break.
        """
        ...
