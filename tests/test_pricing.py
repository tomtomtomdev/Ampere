"""M3 — effective price (SPEC §5.7), written test-first. Pure, deterministic, zero I/O.

``effective_price = list_price + shipping_est - voucher_est - cashback_est``; strikethrough
"harga coret" is never an input (``RawListing`` drops it — SPEC Appendix A). Confidence is
``partial`` unless every cost component is present, which is the v1 norm (search payload is sparse).
"""

from __future__ import annotations

from ampere.domain import pricing
from ampere.domain.models import PriceConfidence, RawListing


def _raw(**kw) -> RawListing:
    base = dict(shopee_id="X", title="t", list_price=1_500_000)
    base.update(kw)
    return RawListing(**base)


class TestEffectivePrice:
    def test_bare_list_price_when_no_adjustments(self):
        assert pricing.effective_price(_raw(list_price=1_500_000)) == 1_500_000

    def test_adds_shipping_subtracts_voucher_and_cashback(self):
        raw = _raw(
            list_price=1_500_000, shipping_est=20_000, voucher_est=50_000, cashback_est=30_000
        )
        # 1_500_000 + 20_000 - 50_000 - 30_000
        assert pricing.effective_price(raw) == 1_440_000

    def test_voucher_only(self):
        assert pricing.effective_price(_raw(list_price=1_899_000, voucher_est=50_000)) == 1_849_000


class TestPriceConfidence:
    def test_partial_when_components_missing(self):
        # the v1 default — search payload rarely carries shipping/voucher/cashback (Appendix A).
        assert pricing.price_confidence(_raw()) is PriceConfidence.PARTIAL

    def test_partial_when_only_some_present(self):
        assert pricing.price_confidence(_raw(voucher_est=50_000)) is PriceConfidence.PARTIAL

    def test_full_when_all_components_present(self):
        raw = _raw(shipping_est=20_000, voucher_est=50_000, cashback_est=30_000)
        assert pricing.price_confidence(raw) is PriceConfidence.FULL
