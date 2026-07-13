"""FixtureSource — canned listings for offline dev + tests (SPEC §6).

Zero network, fully deterministic. Data is a representative subset of the design prototype's 23
real 1jt–2jt listings (``design/Ampere.dc.html``) — new/used, Mall/non-Mall, and two deliberately
unmatched titles for the needs-mapping queue. Expand from the prototype when M1/M3 want the full
golden set. These numbers are ILLUSTRATIVE, not authoritative (real data comes from SPEC §6).
"""

from __future__ import annotations

from ampere.domain.models import RawListing

_FIXTURE: list[RawListing] = [
    RawListing(
        shopee_id="L01", title="Xiaomi Redmi Note 13 8/256 NFC Garansi Resmi HP Murah Promo COD",
        brand="Xiaomi", variant_raw="8/256", list_price=1_899_000, is_mall=True,
        seller_rating=4.9, seller_review_count=1243, is_star_seller=True,
        historical_sold=2500, shop_location="Jakarta Pusat", can_use_cod=True, voucher_est=50_000,
    ),
    RawListing(
        shopee_id="L04", title="Redmi Note 13 8/256 SECOND bekas mulus fullset ex-inter",
        brand="Xiaomi", variant_raw="8/256", list_price=1_420_000, is_mall=False,
        seller_rating=4.6, seller_review_count=87, historical_sold=53,
        shop_location="Surabaya", shipping_est=20_000,
    ),
    RawListing(
        shopee_id="L05", title="POCO M6 5G 6/128 Snapdragon 4 Gen 2 Garansi Resmi Poco Indonesia",
        brand="Xiaomi", variant_raw="6/128", list_price=1_699_000, is_mall=True,
        seller_rating=4.8, seller_review_count=512, is_star_seller=True,
        historical_sold=920, shop_location="Tangerang", cashback_est=30_000,
    ),
    RawListing(
        shopee_id="L09", title="Infinix Hot 40 Pro 8/256 NFC Helio G99 Garansi Resmi",
        brand="Infinix", variant_raw="8/256", list_price=1_599_000, is_mall=True,
        seller_rating=4.7, seller_review_count=388, is_star_seller=True,
        historical_sold=760, shop_location="Jakarta Pusat",
    ),
    RawListing(
        shopee_id="L11", title="Samsung Galaxy A15 8/256 Super AMOLED Garansi Resmi SEIN",
        brand="Samsung", variant_raw="8/256", list_price=1_999_000, is_mall=True,
        seller_rating=4.9, seller_review_count=1502, is_star_seller=True,
        historical_sold=3100, shop_location="Jakarta Pusat",
    ),
    RawListing(
        shopee_id="L13", title="Xiaomi Redmi 13C 8/256 50MP Garansi Resmi Murah",
        brand="Xiaomi", variant_raw="8/256", list_price=1_399_000, is_mall=True,
        seller_rating=4.7, seller_review_count=520, historical_sold=1420, shop_location="Bekasi",
    ),
    RawListing(
        shopee_id="L18", title="Redmi Note 13R 8/256 Dimensity 6300 5G Garansi Resmi",
        brand="Xiaomi", variant_raw="8/256", list_price=1_799_000, is_mall=True,
        seller_rating=4.6, seller_review_count=174, historical_sold=290, shop_location="Bekasi",
    ),
    # Deliberately unmatched -> needs-mapping queue (SPEC §7 step 5).
    RawListing(
        shopee_id="L22",
        title="HP Android RAM 8/256 Baru Garansi Murah Meriah Promo COD Bisa Bayar Ditempat",
        variant_raw="8/256", list_price=1_550_000, is_mall=False, seller_rating=4.2,
        seller_review_count=19, historical_sold=44, shop_location="Jakarta Barat",
    ),
    RawListing(
        shopee_id="L23", title="Smartphone Android 6/128 Layar Besar Baterai Awet Kamera Jernih",
        variant_raw="6/128", list_price=1_290_000, is_mall=False,
        seller_rating=4.0, seller_review_count=8, historical_sold=12, shop_location="Cikarang",
    ),
]


class FixtureSource:
    """A ``SearchSource`` backed by the canned ``_FIXTURE`` set."""

    kind = "fixture"

    def __init__(self, listings: list[RawListing] | None = None) -> None:
        self._listings = list(listings) if listings is not None else list(_FIXTURE)

    def search(
        self,
        keyword: str,
        price_min: int,
        price_max: int,
        *,
        mall_only: bool = False,
    ) -> list[RawListing]:
        rows = [r for r in self._listings if price_min <= r.list_price <= price_max]
        if mall_only:
            rows = [r for r in rows if r.is_mall]
        return rows
