"""Boundary data models (pydantic). Structure only — no scoring logic lives here.

These types are the vocabulary shared across layers. Field names track the SPEC data model
(PLAN "Data model") and the HAR-verified Shopee field map (SPEC Appendix A).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Condition(StrEnum):
    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    FULL = "full"  # all 4 perf metrics + battery present
    PARTIAL = "partial"  # some missing, pillars re-weighted — expected default in this band
    UNMATCHED = "unmatched"  # no device resolved — excluded from frontier, "needs mapping"


class BatteryMetricKind(StrEnum):
    ACTIVE_USE_V2 = "active_use_v2"  # GSMArena Active Use Score, hours (test revised 2023)
    LEGACY_ENDURANCE = "endurance"  # older legacy rating — never mix with v2 (SPEC §5.1)


class PriceConfidence(StrEnum):
    FULL = "full"
    PARTIAL = "partial"  # shipping/voucher/cashback unknown — usual case in v1 (SPEC Appendix A)


# ---------------------------------------------------------------------------
# Reference DB (slowly-changing; monthly refresh)
# ---------------------------------------------------------------------------
class Chipset(BaseModel):
    """A SoC. Benchmarks belong HERE, not on the device (SPEC §5.5, SC7)."""

    id: str
    name: str
    vendor: str | None = None
    gb6_single: float | None = None
    gb6_multi: float | None = None
    antutu: float | None = None  # v10 total
    wildlife: float | None = None  # Wild Life Extreme (Highest)
    source: str | None = None
    fetched_at: datetime | None = None


class Device(BaseModel):
    """A phone SKU. References a chipset for perf; battery + longevity stay per-device."""

    id: str
    brand: str
    model: str
    variant: str  # RAM/ROM, e.g. "8/256"
    chipset_id: str | None = None
    throttle_modifier: float = 1.0  # 0.85–1.0, applied after norm, before perf blend (§5.5)
    active_use_hours: float | None = None
    legacy_endurance: float | None = None
    battery_metric_kind: BatteryMetricKind | None = None
    os_updates_years: int | None = None
    security_updates_years: int | None = None
    update_source: str | None = None
    scoring_notes: str | None = None


# ---------------------------------------------------------------------------
# Listings (daily; the only fast-moving data — SPEC §2)
# ---------------------------------------------------------------------------
class RawListing(BaseModel):
    """Source-agnostic raw listing as returned by any ``SearchSource``.

    Every ``SearchSource`` impl (affiliate / internal / fixture) emits this exact shape so scoring
    and UI never learn which source produced it (SPEC §6, SC4). Prices are whole IDR (adapters
    convert Shopee micro-units ÷100000, SPEC Appendix A).
    """

    shopee_id: str
    title: str
    brand: str | None = None
    variant_raw: str | None = None  # unnormalized RAM/ROM from tier_variations
    list_price: int  # whole IDR; harga-coret / price_before_discount is intentionally dropped
    is_mall: bool = False
    seller_rating: float | None = None
    seller_review_count: int | None = None
    is_star_seller: bool = False  # is_preferred_plus_seller
    historical_sold: int | None = None
    shop_location: str | None = None
    can_use_cod: bool = False
    shipping_est: int = 0
    voucher_est: int = 0
    cashback_est: int = 0
    url: str | None = None


class Listing(BaseModel):
    """A resolved, priced listing — RawListing + entity resolution + effective price."""

    shopee_id: str
    snapshot_date: date
    title: str
    device_id: str | None = None  # None => unmatched
    condition: Condition = Condition.UNKNOWN
    list_price: int
    effective_price: int
    price_confidence: PriceConfidence = PriceConfidence.PARTIAL
    shipping_est: int = 0
    voucher_est: int = 0
    cashback_est: int = 0
    is_mall: bool = False
    seller_rating: float | None = None
    seller_review_count: int | None = None
    is_star_seller: bool = False
    trust_score: float | None = None
    seller_location: str | None = None
    url: str | None = None
    confidence: Confidence = Confidence.UNMATCHED
    duplicate_count: int = 1


class Score(BaseModel):
    """Deterministic two-axis score for one listing at one snapshot (SPEC §5)."""

    listing_id: str
    snapshot_date: date
    performance: float
    battery: float
    capability: float
    value: float
    is_frontier: bool = False
    confidence: Confidence = Confidence.PARTIAL
    scoring_version: str


class Candidate(BaseModel):
    """A scored, deduped candidate — the unit the frontier is computed over (§5.3, §5.8).

    Carries just the axes the Pareto calc needs plus identity, so ``frontier`` stays pure.
    """

    listing_id: str
    model: str
    variant: str
    condition: Condition
    effective_price: int  # x-axis: lower is better
    capability: float  # y-axis: higher is better


class Weights(BaseModel):
    """UI-tunable capability weighting. ``w_perf + w_batt`` should equal 1.0 (SPEC §5.2)."""

    w_perf: float = Field(default=0.55, ge=0.0, le=1.0)

    @property
    def w_batt(self) -> float:
        return 1.0 - self.w_perf


class SkuRollup(BaseModel):
    """One deduped SKU = the cheapest listing for a ``(model, variant, condition)`` (SPEC §5.8).

    ``best_listing_id`` is the lowest-effective-price instance; ``duplicate_count`` records how
    many listings collapsed into it. The frontier is computed over the ``best_listing_id`` set.
    """

    snapshot_date: date
    model: str
    variant: str
    condition: Condition
    best_listing_id: str
    duplicate_count: int = 1


# ---------------------------------------------------------------------------
# Snapshot diff (SPEC G5, §8 "Changes"): what changed vs the prior snapshot.
# ---------------------------------------------------------------------------
class PriceChange(BaseModel):
    """An effective-price move for one listing between two snapshots (§5.7 is the value axis)."""

    shopee_id: str
    prior_effective_price: int
    current_effective_price: int

    @property
    def delta(self) -> int:
        return self.current_effective_price - self.prior_effective_price


class SnapshotDiff(BaseModel):
    """Diff of the current snapshot vs the most recent prior one (arrivals, price moves)."""

    snapshot_date: date
    prior_date: date | None = None
    new_arrivals: list[str] = []  # shopee_ids present today, absent in prior
    removed: list[str] = []  # shopee_ids present in prior, absent today
    price_drops: list[PriceChange] = []  # effective_price fell (the buyer-relevant move)
    price_increases: list[PriceChange] = []


class RunResult(BaseModel):
    """Outcome of one ``run_daily`` — returned for the caller/UI and mirrors the ``runs`` row."""

    snapshot_date: date
    status: str  # "ok" | "failed"
    source_kind: str
    listing_count: int  # all resolved listings persisted for the snapshot
    matched_count: int  # listings that resolved to a device (scoreable)
    frontier_size: int  # non-dominated best-per-SKU points
    diff: SnapshotDiff
