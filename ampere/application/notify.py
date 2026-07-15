"""Daily push digest — build + render + send (SPEC §11.2, M8).

The natural output of a daily run is "the best-value phone in the band this week + the Pareto
frontier" (§11.2); this is a read model for the push channel, the sibling of the web view builders
in ``views.py``. It is computed from the SAME ``score_snapshot`` core at the default weights (both
bonus toggles off), so the pushed frontier is exactly what ``run_daily`` persisted and what the
dashboard shows (deterministic, SC3). Outbound URLs are carried through so the digest can ship
affiliate links (§11.2) without scoring ever depending on them.

Orchestration only — every number comes from the domain via ``score_snapshot`` (invariant #1);
nothing is fabricated (unscoreable listings simply never reach the frontier, invariant #4). The
channel is an injected ``Notifier`` port, so this module holds no I/O and stays adapter-free.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from ampere.application.snapshot import score_snapshot
from ampere.config import (
    DEFAULT_KEYWORD,
    DEFAULT_PRICE_MAX,
    DEFAULT_PRICE_MIN,
    NOTIFY_FRONTIER_LIMIT,
    SCORING_VERSION,
)
from ampere.domain.diff import compute_diff
from ampere.domain.models import Chipset, Device, Weights
from ampere.ports.notifier import Notifier
from ampere.ports.repositories import UnitOfWork


class PushItem(BaseModel):
    """One phone in the pushed digest — a frontier point, enriched for a human reader."""

    rank: int
    shopee_id: str
    model: str
    variant: str
    chip: str
    condition: str
    effective_price: int
    capability: float
    value: float
    url: str | None = None  # outbound (affiliate) link, §11.2 — never influences scoring


class PushDigest(BaseModel):
    """The daily push payload: header context + best-value pick + frontier + change counts."""

    snapshot_date: date
    keyword: str
    price_min: int
    price_max: int
    source_kind: str
    scoring_version: str
    best_value: PushItem | None  # the #1 frontier point by value; None when the frontier is empty
    frontier: list[PushItem]  # top-N frontier points, ranked by value (highest first)
    new_arrivals: int
    price_drops: int


def _jt(idr: int) -> str:
    return f"{idr / 1_000_000:.2f}jt"


def _chip_name(
    devices_by_id: dict[str, Device], chipsets_by_id: dict[str, Chipset], device_id: str | None
) -> str:
    if device_id is None:
        return "—"
    device = devices_by_id.get(device_id)
    if device is None or device.chipset_id is None:
        return "—"
    chipset = chipsets_by_id.get(device.chipset_id)
    return chipset.name if chipset else "—"


def build_push_digest(
    uow: UnitOfWork,
    snapshot_date: date | None,
    *,
    keyword: str = DEFAULT_KEYWORD,
    price_min: int = DEFAULT_PRICE_MIN,
    price_max: int = DEFAULT_PRICE_MAX,
    source_kind: str = "fixture",
    frontier_limit: int = NOTIFY_FRONTIER_LIMIT,
) -> PushDigest | None:
    """Build the digest for ``snapshot_date`` at the persisted (default) scoring, or ``None``.

    Returns ``None`` when there is no snapshot to report. When the snapshot has no scoreable
    listings the digest is still returned (empty frontier / no ``best_value``) — the *send* guard
    lives in ``notify_daily`` so callers can also use this for a preview.
    """
    if snapshot_date is None:
        return None

    devices_by_id = {d.id: d for d in uow.devices.all()}
    chipsets_by_id = {c.id: c for c in uow.chipsets.all()}
    listings = uow.listings.for_snapshot(snapshot_date)
    scored = score_snapshot(listings, uow, Weights())  # defaults ⇒ matches persisted output (SC3)

    frontier_listings = [ln for ln in scored.best_listings if ln.shopee_id in scored.frontier_ids]
    frontier_listings.sort(key=lambda ln: scored.scores_by_id[ln.shopee_id].value, reverse=True)

    frontier: list[PushItem] = []
    for rank, listing in enumerate(frontier_listings[:frontier_limit], start=1):
        score = scored.scores_by_id[listing.shopee_id]
        model, variant = scored.sku_of[listing.device_id]  # type: ignore[index]
        frontier.append(
            PushItem(
                rank=rank, shopee_id=listing.shopee_id, model=model, variant=variant,
                chip=_chip_name(devices_by_id, chipsets_by_id, listing.device_id),
                condition=listing.condition.value, effective_price=listing.effective_price,
                capability=score.capability, value=score.value, url=listing.url,
            )
        )

    prior_date = uow.listings.latest_snapshot_before(snapshot_date)
    prior = uow.listings.for_snapshot(prior_date) if prior_date else []
    diff = compute_diff(prior, listings, snapshot_date=snapshot_date, prior_date=prior_date)

    return PushDigest(
        snapshot_date=snapshot_date, keyword=keyword, price_min=price_min, price_max=price_max,
        source_kind=source_kind, scoring_version=SCORING_VERSION,
        best_value=frontier[0] if frontier else None, frontier=frontier,
        new_arrivals=len(diff.new_arrivals), price_drops=len(diff.price_drops),
    )


def render_digest(digest: PushDigest) -> str:
    """Render the digest to a channel-neutral plain-text message (Telegram auto-links bare URLs).

    Pure + deterministic: same digest ⇒ same text. Kept plain (no Markdown) so no channel-specific
    escaping can corrupt it; the affiliate URLs ride inline (§11.2).
    """
    band = f"{_jt(digest.price_min)}–{_jt(digest.price_max)}"
    lines = [
        f'📱 Ampere — best value in "{digest.keyword}" ({band})',
        f"{digest.snapshot_date.isoformat()} · {digest.source_kind} · {digest.scoring_version}",
        "",
    ]
    if digest.best_value is None:
        lines.append("No phones on the Pareto frontier for this snapshot.")
        return "\n".join(lines)

    bv = digest.best_value
    lines += [
        f"🏆 Best value: {bv.model} {bv.variant} ({bv.chip}, {bv.condition})",
        f"   {_jt(bv.effective_price)} · capability {bv.capability:.1f} · value {bv.value:.1f}",
    ]
    if bv.url:
        lines.append(f"   {bv.url}")
    lines += ["", f"Pareto frontier (top {len(digest.frontier)}):"]
    for item in digest.frontier:
        lines.append(
            f"{item.rank}. {item.model} {item.variant} — {_jt(item.effective_price)} "
            f"· val {item.value:.1f}"
        )
        if item.url:
            lines.append(f"   {item.url}")
    lines += ["", f"Since the prior snapshot: {digest.new_arrivals} new · "
              f"{digest.price_drops} price drop(s)"]
    return "\n".join(lines)


def notify_daily(
    uow: UnitOfWork,
    notifier: Notifier,
    *,
    snapshot_date: date | None,
    keyword: str = DEFAULT_KEYWORD,
    price_min: int = DEFAULT_PRICE_MIN,
    price_max: int = DEFAULT_PRICE_MAX,
    source_kind: str = "fixture",
    frontier_limit: int = NOTIFY_FRONTIER_LIMIT,
) -> PushDigest | None:
    """Build + render + push the daily digest, returning it when sent (else ``None``).

    Sends nothing — and returns ``None`` — when there is no snapshot or the frontier is empty (a
    daily run with nothing scoreable is not worth a push). A ``Notifier.send`` failure propagates;
    the composition root isolates it so a push outage never fails an already-persisted run.
    """
    digest = build_push_digest(
        uow, snapshot_date, keyword=keyword, price_min=price_min, price_max=price_max,
        source_kind=source_kind, frontier_limit=frontier_limit,
    )
    if digest is None or not digest.frontier:
        return None
    notifier.send(render_digest(digest))
    return digest
