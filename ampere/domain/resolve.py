"""Entity resolution — SPEC §7. Where most of the build effort goes.

Turns a noisy title ("Redmi Note 13 Pro 5G 8/256 NFC Garansi Resmi HP Murah COD") into a
canonical ``(brand, model, variant, condition)``, then fuzzy-matches to the device catalog.

STATUS: M2 stubs, TDD first. The ID-market domain knowledge (brand/model aliases, RAM/ROM variant
rules, noise-token lexicon, condition words) lives in the **``id-android-market`` skill**
(.claude/skills/) — prefer extending that ruleset over hard-coding brand rules here (CLAUDE.md
"Domain knowledge"). ``AliasCatalog`` / ``DeviceCatalog`` are injected ports so this stays pure.
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel
from rapidfuzz import fuzz

from ampere.domain import lexicon
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
    # rapidfuzz score of the best candidate considered: the accepted match when ``device_id`` is
    # set, otherwise the top near-miss (for a "closest was 78%" hint), or None if no candidates.
    match_score: float | None = None


class DeviceCatalogPort(Protocol):
    """Read-only view of the device catalog for matching (a domain-facing port)."""

    def candidates_for(self, brand: str | None) -> list[tuple[str, str]]:
        """Return ``[(device_id, "brand model variant")]`` to fuzzy-match against."""
        ...


class AliasCatalogPort(Protocol):
    """Learned raw-pattern -> device_id overrides, closing the long tail (SPEC §7 step 5)."""

    def lookup(self, raw_pattern: str) -> str | None: ...


# --- pure helpers (ID-market rules live in ampere.domain.lexicon) ---------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize_ws(s: str) -> str:
    return " ".join(s.lower().split())


def alias_key(title: str) -> str:
    """The normalization key an alias is stored/looked up under (SPEC §7 step 5a).

    Public so the ``application`` layer (e.g. the Catalog "needs mapping" resolver) records an alias
    under the exact key ``resolve`` will later look it up by — one source of truth for the key.
    """
    return _normalize_ws(title)


def _dedup_tokens(s: str) -> str:
    """Order-preserving unique tokens. Neutralizes brand-repeat artifacts ("realme realme C67",
    or a query that prepends a brand the catalog model already carries) before fuzzy scoring —
    duplicate tokens add no identity information."""
    return " ".join(dict.fromkeys(s.split()))


def _detect_condition(lower: str) -> Condition:
    """SPEC §7 step: condition FIRST, from title tokens only. Precedence refurb > used > new;
    unknown when no condition word is present (skill pitfall: never assume ``new``)."""
    tokens = set(_TOKEN_RE.findall(lower))
    if tokens & lexicon.CONDITION_REFURBISHED:
        return Condition.REFURBISHED
    used = bool(tokens & lexicon.CONDITION_USED) or any(
        p in lower for p, c in lexicon.CONDITION_PHRASES if c is Condition.USED
    )
    if used:  # used token wins over any co-occurring new-ish word ("bekas seperti baru")
        return Condition.USED
    new = bool(tokens & lexicon.CONDITION_NEW) or any(
        p in lower for p, c in lexicon.CONDITION_PHRASES if c is Condition.NEW
    )
    return Condition.NEW if new else Condition.UNKNOWN


def _extract_variant(text: str) -> tuple[str | None, list[str], str]:
    """Pull RAM/ROM + SKU qualifiers (5G/NFC). Returns (variant, qualifiers, text-minus-RAM/ROM).

    RAM vs ROM is decided by magnitude, not position, so ``256/8`` normalizes to ``8/256``
    (skill rule). A bare ROM with no RAM stays partial (``?/256``) — never invent the RAM.
    """
    quals = [q for q in lexicon.QUALIFIER_TOKENS if re.search(rf"\b{q.lower()}\b", text)]
    variant: str | None = None
    m = (
        re.search(r"ram\s*(\d+)\s*(?:gb)?\s*rom\s*(\d+)", text)
        or re.search(r"(\d+)\s*gb\s*/?\s*(\d+)\s*gb", text)
        or re.search(r"(\d+)\s*[/+]\s*(\d+)", text)
    )
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        variant = f"{min(a, b)}/{max(a, b)}"
        text = text[: m.start()] + " " + text[m.end():]
    else:
        bare = re.search(r"\b(\d{2,4})\s*gb\b", text)
        if bare and int(bare.group(1)) >= 32:
            variant = f"?/{int(bare.group(1))}"
            text = text[: bare.start()] + " " + text[bare.end():]
    return variant, quals, text


def clean_title(title: str) -> CleanedTitle:
    """Strip promo/noise tokens, extract brand/model/variant/condition (SPEC §7 steps 1–3)."""
    lower = title.lower()
    condition = _detect_condition(lower)  # step 2: detect BEFORE stripping condition words

    text = lower
    for phrase, token in lexicon.BRAND_PHRASES.items():
        text = text.replace(phrase, token)
    text = lexicon.SPEC_PHRASE_RE.sub(" ", text)  # drop chipset/camera/battery phrases + digits
    variant, quals, text = _extract_variant(text)

    tokens = _TOKEN_RE.findall(text)
    brand = next((lexicon.BRAND_ALIASES[t] for t in tokens if t in lexicon.BRAND_ALIASES), None)

    qual_lower = {q.lower() for q in quals}
    consume_quals = variant is not None  # qualifiers go on the variant; else keep them in model
    model_tokens: list[str] = []
    leftover: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in lexicon.COLOR_TOKENS:
            leftover.append(t)  # colors aren't scoring variants — keep for auditing
            continue
        if (
            t in lexicon.NOISE_TOKENS
            or t in lexicon.CONDITION_REFURBISHED
            or t in lexicon.CONDITION_USED
            or t in lexicon.CONDITION_NEW
            or (t in qual_lower and consume_quals)
            or (t in lexicon.BRAND_ALIASES and t not in lexicon.SUB_BRAND_TOKENS)
        ):
            continue
        if t in seen:
            continue  # collapse repeated identity tokens ("vivo vivo y28")
        seen.add(t)
        model_tokens.append(t)

    variant_out = variant
    if variant is not None and quals:
        variant_out = variant + " " + " ".join(quals)
    return CleanedTitle(
        brand=brand,
        model=" ".join(model_tokens) or None,
        variant=variant_out,
        condition=condition,
        leftover_tokens=leftover,
    )


def _match_string(cleaned: CleanedTitle) -> str:
    """The bag-of-tokens query the fuzzy match runs against (brand + model + variant)."""
    parts = [p for p in (cleaned.brand, cleaned.model, cleaned.variant) if p]
    return _normalize_ws(" ".join(parts))


def resolve(
    title: str,
    devices: DeviceCatalogPort,
    aliases: AliasCatalogPort,
    *,
    threshold: float = 85.0,
) -> ResolutionResult:
    """Full pipeline: clean -> alias override -> fuzzy match -> accept/reject vs threshold."""
    cleaned = clean_title(title)

    # Step 5a: a learned raw-pattern override closes the long tail — trust it over fuzzy matching.
    alias_hit = aliases.lookup(alias_key(title))
    if alias_hit is not None:
        return ResolutionResult(device_id=alias_hit, cleaned=cleaned, match_score=100.0)

    # Step 4: fuzzy match against the catalog. Narrow by brand, widening if the bucket is empty
    # (brand-bucketing disagreements shouldn't silently drop a resolvable listing).
    candidates = devices.candidates_for(cleaned.brand)
    if not candidates and cleaned.brand is not None:
        candidates = devices.candidates_for(None)

    query = _dedup_tokens(_match_string(cleaned))
    # token_sort_ratio (not token_set) so family suffixes — Pro / 5G / 13R — are penalised
    # instead of collapsing a subset match to 100 (skill pitfall #4). Empty query -> 0.
    best_id: str | None = None
    best_score = 0.0
    for device_id, candidate in candidates:
        cand = _dedup_tokens(_normalize_ws(candidate))
        score = fuzz.token_sort_ratio(query, cand) if query else 0.0
        if score > best_score:
            best_id, best_score = device_id, score

    if best_id is not None and best_score >= threshold:
        return ResolutionResult(device_id=best_id, cleaned=cleaned, match_score=best_score)
    # Step 5: below threshold -> unmatched, surfaced in the needs-mapping queue.
    return ResolutionResult(
        device_id=None, cleaned=cleaned, match_score=best_score if candidates else None
    )
