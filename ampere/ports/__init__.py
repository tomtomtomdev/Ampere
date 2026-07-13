"""Ports — interfaces (Protocols). The ONLY way I/O crosses into the domain (invariant #1).

Concrete implementations live in ``ampere.adapters``. Scoring/UI depend on these Protocols, never
on a concrete source or repo (SC4: swapping a ``SearchSource`` requires zero domain/UI changes).
"""
