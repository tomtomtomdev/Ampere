"""Entity resolution — SPEC §7. Where most of the build effort goes.

Turns a noisy title ("Redmi Note 13 Pro 5G 8/256 NFC Garansi Resmi HP Murah COD") into a
canonical ``(brand, model, variant, condition)``, then fuzzy-matches to the device catalog.

STATUS: M2 stubs, TDD first. The ID-market domain knowledge (brand/model aliases, RAM/ROM variant
rules, noise-token lexicon, condition words) lives in the **``id-android-market`` skill**
(.claude/skills/) — prefer extending that ruleset over hard-coding brand rules here (CLAUDE.md
"Domain knowledge"). ``AliasCatalog`` / ``DeviceCatalog`` are injected ports so this stays pure.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ampere.domain.models import Condition


class CleanedTitle(BaseModel):
    brand: str | None = None
    model: str | None = None
    variant: str | None = None  # normalized RAM/ROM + qualifiers (5G/NFC)
    condition: Condition = Condition.UNKNOWN
    leftover_tokens: list[str] = []


class ResolutionResult(BaseModel):
    device_id: str | None = None  # None => unmatched -> needs-mapping queue
    cleaned: CleanedTitle
    match_score: float | None = None  # rapidfuzz score of the accepted match


class DeviceCatalogPort(Protocol):
    """Read-only view of the device catalog for matching (a domain-facing port)."""

    def candidates_for(self, brand: str | None) -> list[tuple[str, str]]:
        """Return ``[(device_id, "brand model variant")]`` to fuzzy-match against."""
        ...


class AliasCatalogPort(Protocol):
    """Learned raw-pattern -> device_id overrides, closing the long tail (SPEC §7 step 5)."""

    def lookup(self, raw_pattern: str) -> str | None: ...


def clean_title(title: str) -> CleanedTitle:
    """Strip promo/noise tokens, extract brand/model/variant/condition (SPEC §7 steps 1–3)."""
    raise NotImplementedError("M2: TDD from SPEC §7 + id-android-market skill")


def resolve(
    title: str,
    devices: DeviceCatalogPort,
    aliases: AliasCatalogPort,
    *,
    threshold: float = 85.0,
) -> ResolutionResult:
    """Full pipeline: clean -> alias override -> fuzzy match -> accept/reject vs threshold."""
    raise NotImplementedError("M2: TDD from SPEC §7")
