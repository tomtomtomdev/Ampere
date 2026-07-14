"""Pure catalog-identity helpers — stable ids + vendor inference for chipsets and devices.

Lives in ``domain`` (imports nothing outward — invariant #1) so BOTH the scraper adapters and the
application-layer seed loader derive ids the same way, without the application ever importing an
adapter. Deterministic string functions only; no I/O.
"""

from __future__ import annotations

import re

_VENDOR_HINTS: tuple[tuple[str, str], ...] = (
    ("snapdragon", "Qualcomm"),
    ("dimensity", "MediaTek"),
    ("helio", "MediaTek"),
    ("exynos", "Samsung"),
    ("tensor", "Google"),
    ("unisoc", "Unisoc"),
    ("kirin", "HiSilicon"),
)


def slugify(text: str) -> str:
    """Lowercase, collapse non-alphanumeric runs to single hyphens, trim leading/trailing ones."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def chipset_id(name: str) -> str:
    """Stable chipset id from its display name (``Snapdragon 7 Gen 4`` → ``snapdragon-7-gen-4``).

    Chipset-variant suffixes ("Extreme", "Ultra") produce distinct ids on purpose — they are
    different parts and must not collapse (SPEC Appendix C caveat)."""
    return slugify(name)


def chipset_vendor(name: str) -> str | None:
    """Infer the SoC vendor from its name, or ``None`` if unrecognized (never guessed wrongly)."""
    low = name.lower()
    for needle, vendor in _VENDOR_HINTS:
        if needle in low:
            return vendor
    return None


def device_id(brand: str, model: str, variant: str) -> str:
    """Stable device id from brand + model + variant (``Xiaomi``/``Redmi Note 13``/``8/256`` →
    ``xiaomi-redmi-note-13-8-256``)."""
    return slugify(f"{brand} {model} {variant}")
