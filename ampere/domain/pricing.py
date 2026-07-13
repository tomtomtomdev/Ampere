"""Effective price — SPEC §5.7. PURE, deterministic, zero I/O.

The value axis (§5.3) uses ``effective_price``, a best-effort true cost, NOT the raw list price and
never the strikethrough "harga coret" (marketing fiction — dropped upstream in ``RawListing``,
Appendix A). Each adjustment is optional; a missing component is zero and flags the price
``partial``. Shipping/voucher/cashback are largely absent from the Shopee search payload, so
``partial`` is the v1 norm (Appendix A) — this is honesty about the data, not a defect.
"""

from __future__ import annotations

from ampere.domain.models import PriceConfidence, RawListing


def effective_price(raw: RawListing) -> int:
    """``list_price + shipping_est - voucher_est - cashback_est`` (SPEC §5.7)."""
    return raw.list_price + raw.shipping_est - raw.voucher_est - raw.cashback_est


def price_confidence(raw: RawListing) -> PriceConfidence:
    """``full`` only when every cost component is present; otherwise ``partial`` (§5.7, Appendix A).

    We cannot distinguish "0 because unknown" from "0 because free" in the search payload, so a
    zero on any component keeps the price ``partial`` rather than overstating confidence.
    """
    if raw.shipping_est > 0 and raw.voucher_est > 0 and raw.cashback_est > 0:
        return PriceConfidence.FULL
    return PriceConfidence.PARTIAL
