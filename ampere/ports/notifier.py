"""Notifier port — the swappable push channel for the daily digest (SPEC §11.2).

The daily run's natural output ("best value in the band + the Pareto frontier") is pushed to a
channel after each scheduled run. Like ``SearchSource``, the channel is swappable behind this thin
contract: the application renders a channel-neutral text digest and hands it to ``send`` — it never
learns whether the other end is Telegram, stdout, or something else. The fragile networked part
lives entirely in the adapter (invariant #1, the M5/M6 transport seam).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """A destination for the rendered daily digest."""

    kind: str  # "telegram" | "stdout" | ... — logged for provenance

    def send(self, text: str) -> None:
        """Deliver one already-rendered message. Raise on failure — the caller isolates it."""
        ...
