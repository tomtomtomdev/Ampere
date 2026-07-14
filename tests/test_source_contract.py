"""M5 — the shared ``SearchSource`` contract suite (invariant #5, SC4).

Every source implementation satisfies this ONE parametrized suite, so scoring/UI can swap sources
freely. Fixture runs offline as-is; the two live sources run through an injected fake ``fetch`` so
no test touches the network. Each source is pre-loaded with the same logical in-band set plus one
deliberately out-of-band item, to prove band filtering is honored uniformly.
"""

from __future__ import annotations

import pytest
from ampere.adapters.sources import build_source
from ampere.adapters.sources.affiliate_feed import AffiliateFeedSource
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.adapters.sources.internal_endpoint import InternalEndpointSource
from ampere.domain.models import RawListing
from ampere.ports.search_source import SearchSource


def _noop(*_a, **_k):
    return None


def _internal() -> InternalEndpointSource:
    page = {
        "items": [
            {"item_basic": {"itemid": 1, "shopid": 1, "name": "Redmi Note 13 8/256",
                            "price": 142_000_000_000, "is_official_shop": True}},
            {"item_basic": {"itemid": 2, "shopid": 1, "name": "Galaxy A15 8/256",
                            "price": 189_900_000_000, "is_official_shop": False}},
            {"item_basic": {"itemid": 3, "shopid": 1, "name": "Out Of Band",
                            "price": 250_000_000_000, "is_official_shop": True}},
        ],
        "nomore": True,
    }
    return InternalEndpointSource(fetch=lambda _p: page, sleep=_noop)


def _affiliate() -> AffiliateFeedSource:
    feed = {"data": {"data": [
        {"product_id": "1", "offer_name": "Redmi Note 13 8/256", "price": 1_420_000},
        {"product_id": "2", "offer_name": "Galaxy A15 8/256", "price": 1_899_000},
        {"product_id": "3", "offer_name": "Out Of Band", "price": 2_500_000},
    ], "current_page": 1, "last_page": 1}}
    return AffiliateFeedSource(fetch=lambda _p: feed, sleep=_noop)


SOURCE_FACTORIES = {"fixture": FixtureSource, "internal": _internal, "affiliate": _affiliate}


@pytest.fixture(params=list(SOURCE_FACTORIES), ids=list(SOURCE_FACTORIES))
def source(request) -> SearchSource:
    return SOURCE_FACTORIES[request.param]()


class TestSearchSourceContract:
    def test_is_a_search_source(self, source):
        assert isinstance(source, SearchSource)
        assert isinstance(source.kind, str) and source.kind

    def test_returns_raw_listings(self, source):
        rows = source.search("android", 1_000_000, 2_000_000)
        assert rows and all(isinstance(r, RawListing) for r in rows)

    def test_respects_price_band(self, source):
        rows = source.search("android", 1_000_000, 2_000_000)
        assert all(1_000_000 <= r.list_price <= 2_000_000 for r in rows)

    def test_narrower_band_returns_subset(self, source):
        wide = {r.shopee_id for r in source.search("android", 1_000_000, 2_000_000)}
        narrow_rows = source.search("android", 1_000_000, 1_500_000)
        narrow = {r.shopee_id for r in narrow_rows}
        assert narrow <= wide
        assert all(r.list_price <= 1_500_000 for r in narrow_rows)

    def test_mall_only_returns_subset(self, source):
        allrows = {r.shopee_id for r in source.search("android", 1_000_000, 2_000_000)}
        mall = {r.shopee_id for r in source.search("android", 1_000_000, 2_000_000, mall_only=True)}
        assert mall <= allrows

    def test_deterministic(self, source):
        assert source.search("android", 1_000_000, 2_000_000) == source.search(
            "android", 1_000_000, 2_000_000
        )


class TestBuildSource:
    @pytest.mark.parametrize("kind", ["fixture", "internal", "affiliate"])
    def test_builds_each_registered_kind(self, kind):
        src = build_source(kind)
        assert isinstance(src, SearchSource)
        assert src.kind == kind

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="unknown source"):
            build_source("nope")
