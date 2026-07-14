"""SearchSource implementations. All satisfy ``ampere.ports.search_source.SearchSource``.

``build_source`` is the composition-root selector (SPEC §8 "source selection", SC4): swapping the
daily source is a one-line change (``source_factory=lambda: build_source("internal")``) with zero
impact on scoring/UI, since every impl emits the same ``RawListing`` contract.
"""

from __future__ import annotations

from ampere.adapters.sources.affiliate_feed import AffiliateFeedSource
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.adapters.sources.internal_endpoint import InternalEndpointSource
from ampere.ports.search_source import SearchSource

_REGISTRY = {
    "fixture": FixtureSource,
    "internal": InternalEndpointSource,
    "affiliate": AffiliateFeedSource,
}


def build_source(kind: str, **kwargs) -> SearchSource:
    """Instantiate a source by kind (``fixture`` | ``internal`` | ``affiliate``)."""
    try:
        factory = _REGISTRY[kind.lower()]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"unknown source kind: {kind!r} (known: {known})") from None
    return factory(**kwargs)


__all__ = [
    "AffiliateFeedSource",
    "FixtureSource",
    "InternalEndpointSource",
    "build_source",
]
