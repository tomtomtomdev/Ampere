"""The daily use-case + headless entrypoint (SPEC §2, §8a; SC6, SC8).

Pipeline:  fetch -> resolve -> effective_price -> dedup-cheapest-per-SKU -> score -> frontier
           -> diff vs prior snapshot -> persist (idempotent + transactional per snapshot_date).

STATUS: M3 stub. ``main()`` is the single code path the OS scheduler (launchd/cron) AND the UI's
fallback "Run now" both call. Catch-up on launch (if no successful run for today) lands here too.
"""

from __future__ import annotations

from datetime import date

from ampere.ports.repositories import (
    AliasRepo,
    ChipsetRepo,
    DeviceRepo,
    ListingRepo,
    RunRepo,
    ScoreRepo,
)
from ampere.ports.search_source import SearchSource


def run_daily(
    *,
    source: SearchSource,
    chipsets: ChipsetRepo,
    devices: DeviceRepo,
    aliases: AliasRepo,
    listings: ListingRepo,
    scores: ScoreRepo,
    runs: RunRepo,
    snapshot_date: date,
    keyword: str,
    price_min: int,
    price_max: int,
) -> None:
    """Run one idempotent daily snapshot. Re-running the same date replaces, never duplicates."""
    raise NotImplementedError("M3: TDD from PLAN M3 + SPEC §2/§5.8/SC6")


def main() -> int:
    """Headless entrypoint (``ampere-run-daily``) for the OS scheduler + launch-time catch-up."""
    raise NotImplementedError("M6: wire config + adapters, then call run_daily()")
