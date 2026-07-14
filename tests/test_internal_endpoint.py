"""M5 — InternalEndpointSource, written test-first from SPEC Appendix A + the shopee-marketplace
skill field map.

The live transport (anti-bot headers / Playwright — SPEC Appendix A) is injected as a ``fetch``
callable, so the parsing + pagination + filtering logic is fully unit-testable offline against
saved-shape ``search_items`` JSON — never touching Shopee (skill guidance). These payloads mirror
the HAR-verified ``item_basic`` shape; the numbers are illustrative.
"""

from __future__ import annotations

import json

import pytest
from ampere.adapters.sources._common import InMemoryCache, SourceFetchError
from ampere.adapters.sources.internal_endpoint import (
    PRICE_DELIM,
    InternalEndpointSource,
    parse_item,
    parse_search_items,
)
from ampere.domain.models import RawListing


def _basic(itemid=101, shopid=9, name="Redmi Note 13 8/256", price=189_900_000_000, **kw):
    """One ``item_basic`` object. ``price`` is in Shopee micro-units (×100000)."""
    b = {"itemid": itemid, "shopid": shopid, "name": name, "price": price}
    b.update(kw)
    return b


def _page(items, *, nomore=False, total_count=None):
    payload: dict = {"items": [{"item_basic": b} for b in items], "nomore": nomore}
    if total_count is not None:
        payload["total_count"] = total_count
    return payload


def _noop(*_a, **_k):
    return None


class TestParseItem:
    def test_price_is_micro_units_divided_by_100000(self):
        assert parse_item(_basic(price=185_900_000_000)).list_price == 1_859_000

    def test_ignores_harga_coret_price_before_discount(self):
        # price_before_discount is marketing fiction — never used as a real price (§5.7).
        rl = parse_item(_basic(price=185_900_000_000, price_before_discount=329_900_000_000))
        assert rl.list_price == 1_859_000

    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            (["8/256"], "8/256"),
            (["8GB/256GB"], "8/256"),
            (["4/64"], "4/64"),
            (["RAM 6GB / 128GB"], "6/128"),
        ],
    )
    def test_variant_extracted_from_tier_variations(self, options, expected):
        # Axis name + option format both vary (STORAGE/PENYIMPANAN/Kapasitas; 8/256, 8GB/256GB).
        b = _basic(tier_variations=[{"name": "PENYIMPANAN", "options": options}])
        assert parse_item(b).variant_raw == expected

    def test_variant_ignores_color_axis(self):
        b = _basic(tier_variations=[{"name": "Warna", "options": ["Hitam", "Biru"]}])
        assert parse_item(b).variant_raw is None

    def test_no_tier_variations_leaves_variant_none(self):
        assert parse_item(_basic()).variant_raw is None

    def test_mall_from_official_shop_flags(self):
        assert parse_item(_basic(is_official_shop=True)).is_mall is True
        assert parse_item(_basic(show_official_shop_label=True)).is_mall is True
        assert parse_item(_basic()).is_mall is False

    def test_trust_signals_mapped(self):
        b = _basic(
            item_rating={"rating_star": 4.8, "rating_count": [1243, 1, 2, 3, 4, 5]},
            is_preferred_plus_seller=True,
        )
        rl = parse_item(b)
        assert rl.seller_rating == 4.8
        assert rl.seller_review_count == 1243  # rating_count[0] = total (Appendix A)
        assert rl.is_star_seller is True

    def test_missing_trust_is_none_not_fabricated(self):
        rl = parse_item(_basic())
        assert rl.seller_rating is None
        assert rl.seller_review_count is None
        assert rl.is_star_seller is False

    def test_context_fields(self):
        rl = parse_item(
            _basic(historical_sold=2500, shop_location="Jakarta Pusat", can_use_cod=True)
        )
        assert rl.historical_sold == 2500
        assert rl.shop_location == "Jakarta Pusat"
        assert rl.can_use_cod is True

    def test_url_built_from_shop_and_item_ids(self):
        rl = parse_item(_basic(itemid=101, shopid=9))
        assert rl.url is not None
        assert "9" in rl.url and "101" in rl.url

    def test_blank_brand_is_none(self):
        assert parse_item(_basic(brand="")).brand is None
        assert parse_item(_basic(brand="Xiaomi")).brand == "Xiaomi"

    def test_returns_none_without_id_or_price(self):
        assert parse_item({"name": "x", "price": 1}) is None
        assert parse_item({"itemid": 1, "name": "x"}) is None


class TestParseSearchItems:
    def test_parses_items_array(self):
        payload = {"items": [{"item_basic": _basic(itemid=1)}, {"item_basic": _basic(itemid=2)}]}
        rows = parse_search_items(payload)
        assert [r.shopee_id for r in rows] == ["1", "2"]
        assert all(isinstance(r, RawListing) for r in rows)

    def test_tolerates_empty_and_malformed(self):
        assert parse_search_items({}) == []
        assert parse_search_items({"items": [{"foo": 1}, None, {"item_basic": None}]}) == []


class TestSearch:
    def test_fe_filter_options_carries_price_range_and_mall(self):
        captured: dict = {}

        def fake(params):
            captured.update(params)
            return _page([], nomore=True)

        InternalEndpointSource(fetch=fake, sleep=_noop).search(
            "android", 1_000_000, 2_000_000, mall_only=True
        )
        groups = {g["group_name"]: g["values"] for g in json.loads(captured["fe_filter_options"])}
        assert groups["PRICE_RANGE"] == [f"1000000{PRICE_DELIM}2000000"]  # min▶◀max, whole IDR
        assert groups["SHOP_TYPE"] == ["OFFICIAL_MALL"]
        assert captured["keyword"] == "android"
        assert captured["limit"] == "60"

    def test_mall_off_omits_shop_type_group(self):
        captured: dict = {}

        def fake(params):
            captured.update(params)
            return _page([], nomore=True)

        InternalEndpointSource(fetch=fake, sleep=_noop).search("android", 1_000_000, 2_000_000)
        groups = [g["group_name"] for g in json.loads(captured["fe_filter_options"])]
        assert "SHOP_TYPE" not in groups
        assert "PRICE_RANGE" in groups

    def test_paginates_by_newest_offset_until_nomore(self):
        pages = {
            "0": _page([_basic(itemid=1, price=142_000_000_000)], total_count=120),
            "60": _page([_basic(itemid=2, price=150_000_000_000)], nomore=True, total_count=120),
        }
        calls: list[str] = []

        def fake(params):
            calls.append(params["newest"])
            return pages[params["newest"]]

        src = InternalEndpointSource(fetch=fake, sleep=_noop)
        out = src.search("android", 1_000_000, 2_000_000)
        assert calls == ["0", "60"]  # offset cursor, not a page index
        assert {r.shopee_id for r in out} == {"1", "2"}

    def test_stops_when_offset_reaches_total_count(self):
        pages = {
            "0": _page([_basic(itemid=1, price=142_000_000_000)], total_count=60),
        }
        calls: list[str] = []

        def fake(params):
            calls.append(params["newest"])
            return pages[params["newest"]]

        InternalEndpointSource(fetch=fake, sleep=_noop).search("android", 1_000_000, 2_000_000)
        assert calls == ["0"]  # ceil(60/60) == 1 page

    def test_respects_max_pages_cap(self):
        calls: list[str] = []

        def fake(params):  # never signals nomore, huge total
            calls.append(params["newest"])
            off = int(params["newest"])
            return _page([_basic(itemid=off, price=142_000_000_000)], total_count=100_000)

        InternalEndpointSource(fetch=fake, max_pages=3, sleep=_noop).search(
            "android", 1_000_000, 2_000_000
        )
        assert len(calls) == 3  # one-burst-per-keyword is bounded

    def test_client_side_band_filter_drops_out_of_band(self):
        page = _page(
            [
                _basic(itemid=1, price=142_000_000_000),  # 1.42jt in-band
                _basic(itemid=2, price=250_000_000_000),  # 2.5jt out-of-band (defensive drop)
            ],
            nomore=True,
        )
        out = InternalEndpointSource(fetch=lambda _p: page, sleep=_noop).search(
            "android", 1_000_000, 2_000_000
        )
        assert {r.shopee_id for r in out} == {"1"}

    def test_dedups_by_shopee_id(self):
        page = _page(
            [
                _basic(itemid=1, price=142_000_000_000),
                _basic(itemid=1, price=142_000_000_000),
            ],
            nomore=True,
        )
        out = InternalEndpointSource(fetch=lambda _p: page, sleep=_noop).search(
            "android", 1_000_000, 2_000_000
        )
        assert len(out) == 1

    def test_caches_pages_across_calls(self):
        page = _page([_basic(itemid=1, price=142_000_000_000)], nomore=True)
        calls: list[int] = []

        def fake(_params):
            calls.append(1)
            return page

        src = InternalEndpointSource(fetch=fake, cache=InMemoryCache(), sleep=_noop)
        src.search("android", 1_000_000, 2_000_000)
        src.search("android", 1_000_000, 2_000_000)  # identical request → served from cache
        assert len(calls) == 1

    def test_backoff_retries_then_succeeds(self):
        page = _page([_basic(itemid=1, price=142_000_000_000)], nomore=True)
        attempts: list[int] = []
        slept: list[float] = []

        def flaky(_params):
            attempts.append(1)
            if len(attempts) < 3:
                raise SourceFetchError("transient")
            return page

        out = InternalEndpointSource(
            fetch=flaky, max_retries=3, base_delay=0.01, sleep=slept.append
        ).search("android", 1_000_000, 2_000_000)
        assert len(out) == 1
        assert len(attempts) == 3
        assert slept  # actually backed off (injected sleep, no real wait)

    def test_backoff_gives_up_after_max_retries(self):
        def always_fail(_params):
            raise SourceFetchError("source down")

        src = InternalEndpointSource(fetch=always_fail, max_retries=2, base_delay=0.01, sleep=_noop)
        with pytest.raises(SourceFetchError):
            src.search("android", 1_000_000, 2_000_000)

    def test_kind_is_internal(self):
        assert InternalEndpointSource(fetch=lambda _p: _page([], nomore=True)).kind == "internal"
