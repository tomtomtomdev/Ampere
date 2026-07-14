"""Read-model view builders for the web UI (SPEC §8). One per screen.

The web layer stays thin (CLAUDE.md): endpoints call these, serialize the returned pydantic DTO,
and do nothing else. Every number comes from the domain via ``score_snapshot`` — recomputed here
from the stored snapshot + catalog at the request's weights, so a moved slider re-scores live and
deterministically (the default weights reproduce exactly what ``run_daily`` persisted, SC3).
Nothing is fabricated: unmatched listings never enter the scored tables — they surface only in the
Catalog "needs mapping" queue (§5.4, invariant #4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

from ampere.application.snapshot import ScoredSnapshot, score_snapshot
from ampere.config import (
    DEFAULT_KEYWORD,
    DEFAULT_PRICE_MAX,
    DEFAULT_PRICE_MIN,
    LONGEVITY_BONUS_ENABLED,
    PERFORMANCE_WEIGHTS,
    SCORING_VERSION,
    TRUST_PENALTY_ENABLED,
)
from ampere.domain.diff import compute_diff
from ampere.domain.models import Chipset, Device, Listing, SnapshotDiff, Weights
from ampere.ports.repositories import UnitOfWork

_SCHEDULE_TIME = "06:00 WIB"  # SPEC §8a: launchd StartCalendarInterval / cron equivalent
_AVAILABLE_SOURCES = ["affiliate", "internal", "fixture"]


# ---------------------------------------------------------------------------
# Request-side params (what the UI controls tune)
# ---------------------------------------------------------------------------
class ViewParams(BaseModel):
    """UI-tunable inputs. Weights + blended re-score; the rest are query context/chrome."""

    weights: Weights = Weights()
    blended: bool = False
    mall_only: bool = False
    keyword: str = DEFAULT_KEYWORD
    price_min: int = DEFAULT_PRICE_MIN
    price_max: int = DEFAULT_PRICE_MAX
    source_kind: str = "fixture"


# ---------------------------------------------------------------------------
# Shared chrome
# ---------------------------------------------------------------------------
class WeightsView(BaseModel):
    w_perf: float
    w_batt: float


class Stats(BaseModel):
    raw: int
    deduped: int
    matched_pct: int


class NavBadges(BaseModel):
    listings: int
    catalog: int
    changes: int


class Schedule(BaseModel):
    active: bool = True
    time: str = _SCHEDULE_TIME
    last_run: date | None = None


class Meta(BaseModel):
    snapshot_date: date | None
    scoring_version: str = SCORING_VERSION
    keyword: str
    price_min: int
    price_max: int
    band_label: str
    source_kind: str
    weights: WeightsView
    stats: Stats
    schedule: Schedule
    nav_badges: NavBadges


# ---------------------------------------------------------------------------
# Screen DTOs
# ---------------------------------------------------------------------------
class Point(BaseModel):
    shopee_id: str
    model: str
    variant: str
    chip: str
    condition: str
    is_mall: bool
    effective_price: int
    capability: float
    value: float
    is_frontier: bool
    verdict: str


class FrontierRow(BaseModel):
    rank: int
    shopee_id: str
    model: str
    variant: str
    chip: str
    effective_price: int
    capability: float
    value: float


class DashboardView(BaseModel):
    meta: Meta
    weights: WeightsView
    blended: bool
    points: list[Point]
    top_frontier: list[FrontierRow]


class ListingRow(BaseModel):
    shopee_id: str
    brand: str
    model: str
    variant: str
    chip: str
    title: str
    condition: str
    effective_price: int
    list_price: int
    capability: float
    value: float
    confidence: str
    is_frontier: bool
    duplicate_count: int
    seller_rating: float | None
    is_mall: bool
    is_star_seller: bool
    seller_location: str | None
    url: str | None
    price_drop: int | None  # magnitude of an effective-price drop vs the prior snapshot


class ListingsView(BaseModel):
    meta: Meta
    rows: list[ListingRow]


class ChipsetRow(BaseModel):
    id: str
    name: str
    vendor: str | None
    gb6_single: float | None
    gb6_multi: float | None
    antutu: float | None
    wildlife: float | None
    source: str | None
    used_by: int


class DeviceRow(BaseModel):
    id: str
    brand: str
    model: str
    variant: str
    chip: str
    active_use_hours: float | None
    battery_metric_kind: str | None
    os_updates_years: int | None
    security_updates_years: int | None
    update_source: str | None


class NeedsMappingRow(BaseModel):
    shopee_id: str
    title: str


class CatalogView(BaseModel):
    meta: Meta
    chipsets: list[ChipsetRow]
    devices: list[DeviceRow]
    needs_mapping: list[NeedsMappingRow]


class PriceDropRow(BaseModel):
    shopee_id: str
    model: str | None
    variant: str | None
    chip: str
    capability: float | None
    effective_price: int
    prior_effective_price: int
    delta: int


class ArrivalRow(BaseModel):
    shopee_id: str
    model: str | None
    variant: str | None
    chip: str
    effective_price: int
    value: float | None
    is_frontier: bool


class ChangesView(BaseModel):
    meta: Meta
    prior_date: date | None
    price_drops: list[PriceDropRow]
    new_arrivals: list[ArrivalRow]


class SettingsView(BaseModel):
    meta: Meta
    keyword: str
    price_min: int
    price_max: int
    weights: WeightsView
    perf_weights: dict[str, float]
    mall_only: bool
    blended: bool
    longevity_bonus_enabled: bool
    trust_penalty_enabled: bool
    source_kind: str
    sources: list[str]
    scoring_version: str
    schedule: Schedule


# ---------------------------------------------------------------------------
# Internal request context — computed once, shared by every builder
# ---------------------------------------------------------------------------
@dataclass
class _Ctx:
    snapshot_date: date | None
    listings: list[Listing]
    listings_by_id: dict[str, Listing]
    scored: ScoredSnapshot
    devices_by_id: dict[str, Device]
    chipsets_by_id: dict[str, Chipset]
    prior_date: date | None
    diff: SnapshotDiff


def current_snapshot(uow: UnitOfWork) -> date | None:
    """The snapshot the UI shows = the most recent successful run (SPEC §8)."""
    return uow.runs.last_successful()


def _jt(idr: int) -> str:
    return f"{idr / 1_000_000:.2f}jt"


def _load_ctx(uow: UnitOfWork, snapshot_date: date | None, params: ViewParams) -> _Ctx:
    devices_by_id = {d.id: d for d in uow.devices.all()}
    chipsets_by_id = {c.id: c for c in uow.chipsets.all()}
    if snapshot_date is None:
        empty_diff = SnapshotDiff(snapshot_date=date.min, prior_date=None)
        return _Ctx(None, [], {}, ScoredSnapshot(), devices_by_id, chipsets_by_id, None, empty_diff)

    listings = uow.listings.for_snapshot(snapshot_date)
    scored = score_snapshot(listings, uow, params.weights, blended=params.blended)
    prior_date = uow.listings.latest_snapshot_before(snapshot_date)
    prior = uow.listings.for_snapshot(prior_date) if prior_date else []
    diff = compute_diff(prior, listings, snapshot_date=snapshot_date, prior_date=prior_date)
    return _Ctx(
        snapshot_date=snapshot_date, listings=listings,
        listings_by_id={ln.shopee_id: ln for ln in listings}, scored=scored,
        devices_by_id=devices_by_id, chipsets_by_id=chipsets_by_id,
        prior_date=prior_date, diff=diff,
    )


def _chip_name(ctx: _Ctx, device_id: str | None) -> str:
    if device_id is None:
        return "—"
    device = ctx.devices_by_id.get(device_id)
    if device is None or device.chipset_id is None:
        return "—"
    chipset = ctx.chipsets_by_id.get(device.chipset_id)
    return chipset.name if chipset else "—"


def _meta(ctx: _Ctx, params: ViewParams) -> Meta:
    raw = len(ctx.listings)
    matched = sum(ln.device_id is not None for ln in ctx.listings)
    unmatched = raw - matched
    deduped = len(ctx.scored.best_listings)
    matched_pct = round(matched / raw * 100) if raw else 0
    changes_count = len(ctx.diff.price_drops) + len(ctx.diff.new_arrivals)
    w = params.weights
    return Meta(
        snapshot_date=ctx.snapshot_date, keyword=params.keyword,
        price_min=params.price_min, price_max=params.price_max,
        band_label=f"{_jt(params.price_min)}–{_jt(params.price_max)}",
        source_kind=params.source_kind,
        weights=WeightsView(w_perf=w.w_perf, w_batt=w.w_batt),
        stats=Stats(raw=raw, deduped=deduped, matched_pct=matched_pct),
        schedule=Schedule(last_run=ctx.snapshot_date),
        nav_badges=NavBadges(listings=deduped, catalog=unmatched, changes=changes_count),
    )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def build_dashboard(
    uow: UnitOfWork, snapshot_date: date | None, params: ViewParams
) -> DashboardView:
    ctx = _load_ctx(uow, snapshot_date, params)
    scored = ctx.scored
    points: list[Point] = []
    for listing in scored.best_listings:
        score = scored.scores_by_id[listing.shopee_id]
        model, variant = scored.sku_of[listing.device_id]  # type: ignore[index]
        points.append(
            Point(
                shopee_id=listing.shopee_id, model=model, variant=variant,
                chip=_chip_name(ctx, listing.device_id), condition=listing.condition.value,
                is_mall=listing.is_mall, effective_price=listing.effective_price,
                capability=score.capability, value=score.value, is_frontier=score.is_frontier,
                verdict="ON FRONTIER" if score.is_frontier else "dominated",
            )
        )
    ranked = sorted((p for p in points if p.is_frontier), key=lambda p: p.value, reverse=True)
    top_frontier = [
        FrontierRow(
            rank=i + 1, shopee_id=p.shopee_id, model=p.model, variant=p.variant, chip=p.chip,
            effective_price=p.effective_price, capability=p.capability, value=p.value,
        )
        for i, p in enumerate(ranked)
    ]
    w = params.weights
    return DashboardView(
        meta=_meta(ctx, params), weights=WeightsView(w_perf=w.w_perf, w_batt=w.w_batt),
        blended=params.blended, points=points, top_frontier=top_frontier,
    )


def build_listings(uow: UnitOfWork, snapshot_date: date | None, params: ViewParams) -> ListingsView:
    ctx = _load_ctx(uow, snapshot_date, params)
    scored = ctx.scored
    dup_of = {r.best_listing_id: r.duplicate_count for r in scored.rollups}
    drop_of = {pc.shopee_id: -pc.delta for pc in ctx.diff.price_drops}  # positive magnitude
    rows: list[ListingRow] = []
    for listing in scored.best_listings:
        score = scored.scores_by_id[listing.shopee_id]
        model, variant = scored.sku_of[listing.device_id]  # type: ignore[index]
        device = ctx.devices_by_id.get(listing.device_id)  # type: ignore[arg-type]
        rows.append(
            ListingRow(
                shopee_id=listing.shopee_id, brand=device.brand if device else "",
                model=model, variant=variant, chip=_chip_name(ctx, listing.device_id),
                title=listing.title, condition=listing.condition.value,
                effective_price=listing.effective_price, list_price=listing.list_price,
                capability=score.capability, value=score.value, confidence=score.confidence.value,
                is_frontier=score.is_frontier, duplicate_count=dup_of.get(listing.shopee_id, 1),
                seller_rating=listing.seller_rating, is_mall=listing.is_mall,
                is_star_seller=listing.is_star_seller, seller_location=listing.seller_location,
                url=listing.url, price_drop=drop_of.get(listing.shopee_id),
            )
        )
    return ListingsView(meta=_meta(ctx, params), rows=rows)


def build_catalog(uow: UnitOfWork, snapshot_date: date | None) -> CatalogView:
    params = ViewParams()
    ctx = _load_ctx(uow, snapshot_date, params)
    used_by: dict[str, int] = {}
    for device in ctx.devices_by_id.values():
        if device.chipset_id:
            used_by[device.chipset_id] = used_by.get(device.chipset_id, 0) + 1
    chipsets = [
        ChipsetRow(
            id=c.id, name=c.name, vendor=c.vendor, gb6_single=c.gb6_single, gb6_multi=c.gb6_multi,
            antutu=c.antutu, wildlife=c.wildlife, source=c.source, used_by=used_by.get(c.id, 0),
        )
        for c in sorted(ctx.chipsets_by_id.values(), key=lambda c: -(c.gb6_single or 0))
    ]
    devices = [
        DeviceRow(
            id=d.id, brand=d.brand, model=d.model, variant=d.variant,
            chip=_chip_name(ctx, d.id),
            active_use_hours=d.active_use_hours,
            battery_metric_kind=d.battery_metric_kind.value if d.battery_metric_kind else None,
            os_updates_years=d.os_updates_years, security_updates_years=d.security_updates_years,
            update_source=d.update_source,
        )
        for d in sorted(ctx.devices_by_id.values(), key=lambda d: (d.brand, d.model, d.variant))
    ]
    needs_mapping = [
        NeedsMappingRow(shopee_id=ln.shopee_id, title=ln.title)
        for ln in ctx.listings if ln.device_id is None
    ]
    return CatalogView(
        meta=_meta(ctx, params), chipsets=chipsets, devices=devices, needs_mapping=needs_mapping,
    )


def build_changes(uow: UnitOfWork, snapshot_date: date | None, params: ViewParams) -> ChangesView:
    ctx = _load_ctx(uow, snapshot_date, params)
    price_drops = [
        PriceDropRow(
            shopee_id=pc.shopee_id, **_names(ctx, pc.shopee_id),
            capability=_cap(ctx, pc.shopee_id), effective_price=pc.current_effective_price,
            prior_effective_price=pc.prior_effective_price, delta=pc.delta,
        )
        for pc in sorted(ctx.diff.price_drops, key=lambda pc: pc.delta)  # biggest drop first
    ]
    new_arrivals = [
        ArrivalRow(
            shopee_id=sid, **_names(ctx, sid),
            effective_price=ctx.listings_by_id[sid].effective_price,
            value=_val(ctx, sid), is_frontier=_is_frontier(ctx, sid),
        )
        for sid in ctx.diff.new_arrivals
    ]
    new_arrivals.sort(key=lambda a: (a.value is None, -(a.value or 0)))
    return ChangesView(
        meta=_meta(ctx, params), prior_date=ctx.prior_date,
        price_drops=price_drops, new_arrivals=new_arrivals,
    )


def build_settings(uow: UnitOfWork, snapshot_date: date | None, params: ViewParams) -> SettingsView:
    ctx = _load_ctx(uow, snapshot_date, params)
    w = params.weights
    return SettingsView(
        meta=_meta(ctx, params), keyword=params.keyword,
        price_min=params.price_min, price_max=params.price_max,
        weights=WeightsView(w_perf=w.w_perf, w_batt=w.w_batt),
        perf_weights=dict(PERFORMANCE_WEIGHTS), mall_only=params.mall_only, blended=params.blended,
        longevity_bonus_enabled=LONGEVITY_BONUS_ENABLED,
        trust_penalty_enabled=TRUST_PENALTY_ENABLED,
        source_kind=params.source_kind, sources=list(_AVAILABLE_SOURCES),
        scoring_version=SCORING_VERSION, schedule=Schedule(last_run=ctx.snapshot_date),
    )


# --- enrichment helpers for the Changes screen (matched -> model/chip/score; else fallbacks) ---
def _names(ctx: _Ctx, shopee_id: str) -> dict[str, str | None]:
    listing = ctx.listings_by_id.get(shopee_id)
    if listing is None or listing.device_id not in ctx.scored.sku_of:
        return {"model": None, "variant": None, "chip": "—"}
    model, variant = ctx.scored.sku_of[listing.device_id]  # type: ignore[index]
    return {"model": model, "variant": variant, "chip": _chip_name(ctx, listing.device_id)}


def _cap(ctx: _Ctx, shopee_id: str) -> float | None:
    score = ctx.scored.scores_by_id.get(shopee_id)
    return score.capability if score else None


def _val(ctx: _Ctx, shopee_id: str) -> float | None:
    score = ctx.scored.scores_by_id.get(shopee_id)
    return score.value if score else None


def _is_frontier(ctx: _Ctx, shopee_id: str) -> bool:
    return shopee_id in ctx.scored.frontier_ids
