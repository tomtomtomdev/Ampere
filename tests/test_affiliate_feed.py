"""M5 — AffiliateFeedSource, written test-first.

The affiliate feed (Involve Asia / Accesstrade) is the ToS-safe, *preferred* source (SPEC §6),
but its exact schema is pending access confirmation (open question). It is deliberately **narrower**
than the internal endpoint: it carries a clean price + an affiliate tracking URL (§11.2) but no
reliable Mall / seller-trust signals — so we map what the feed gives and never fabricate the rest
(invariant #4). Transport is injected as a ``fetch`` callable; these payloads mirror the assumed
Involve-Asia-style ``{data:{data:[...]}}`` shape.
"""

from __future__ import annotations

from ampere.adapters.sources.affiliate_feed import (
    AffiliateFeedSource,
    parse_feed,
    parse_offer,
)
from ampere.domain.models import RawListing


def _offer(pid="p1", name="Redmi Note 13 8/256", price=1_899_000, **kw):
    o = {"product_id": pid, "offer_name": name, "price": price}
    o.update(kw)
    return o


def _feed(offers, *, current_page=1, last_page=1):
    return {"data": {"data": offers, "current_page": current_page, "last_page": last_page}}


def _noop(*_a, **_k):
    return None


class TestParseOffer:
    def test_maps_core_fields(self):
        rl = parse_offer(
            _offer(pid="p1", name="Redmi Note 13", price=1_899_000, brand="Xiaomi",
                   tracking_link="https://invol.co/aff_x")
        )
        assert isinstance(rl, RawListing)
        assert rl.shopee_id == "p1"
        assert rl.title == "Redmi Note 13"
        assert rl.list_price == 1_899_000  # whole IDR — affiliate feeds are NOT micro-units
        assert rl.brand == "Xiaomi"
        assert rl.url == "https://invol.co/aff_x"  # affiliate link preserved (§11.2)

    def test_prefers_sale_price_over_list_price(self):
        assert parse_offer(_offer(price=1_899_000, sale_price=1_799_000)).list_price == 1_799_000

    def test_zero_sale_price_falls_back_to_price(self):
        assert parse_offer(_offer(price=1_899_000, sale_price=0)).list_price == 1_899_000

    def test_narrow_feed_has_no_fabricated_mall_or_trust(self):
        rl = parse_offer(_offer())
        assert rl.is_mall is False
        assert rl.seller_rating is None
        assert rl.is_star_seller is False

    def test_returns_none_when_incomplete(self):
        assert parse_offer({"offer_name": "x"}) is None  # no id
        assert parse_offer({"product_id": "p"}) is None  # no price/name


class TestParseFeed:
    def test_parses_nested_data_array(self):
        payload = _feed([_offer(pid="a"), _offer(pid="b")])
        assert {r.shopee_id for r in parse_feed(payload)} == {"a", "b"}

    def test_tolerates_empty(self):
        assert parse_feed({}) == []
        assert parse_feed(_feed([])) == []


class TestSearch:
    def test_filters_to_price_band(self):
        feed = _feed([_offer(pid="a", price=1_400_000), _offer(pid="b", price=2_500_000)])
        out = AffiliateFeedSource(fetch=lambda _p: feed, sleep=_noop).search(
            "android", 1_000_000, 2_000_000
        )
        assert {r.shopee_id for r in out} == {"a"}

    def test_paginates_until_last_page(self):
        pages = {
            "1": _feed([_offer(pid="a", price=1_400_000)], current_page=1, last_page=2),
            "2": _feed([_offer(pid="b", price=1_500_000)], current_page=2, last_page=2),
        }
        calls: list[str] = []

        def fake(params):
            calls.append(params["page"])
            return pages[params["page"]]

        out = AffiliateFeedSource(fetch=fake, sleep=_noop).search("android", 1_000_000, 2_000_000)
        assert calls == ["1", "2"]
        assert {r.shopee_id for r in out} == {"a", "b"}

    def test_respects_max_pages_cap(self):
        calls: list[str] = []

        def fake(params):  # last_page always beyond the cap
            calls.append(params["page"])
            n = params["page"]
            return _feed([_offer(pid=n, price=1_400_000)], current_page=int(n), last_page=999)

        AffiliateFeedSource(fetch=fake, max_pages=3, sleep=_noop).search(
            "android", 1_000_000, 2_000_000
        )
        assert len(calls) == 3

    def test_kind_is_affiliate(self):
        assert AffiliateFeedSource(fetch=lambda _p: _feed([])).kind == "affiliate"
