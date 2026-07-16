"""Resolve the daily-push channel from persisted settings or env (SPEC §11.2).

The push channel is configurable from the UI — persisted in the ``settings`` KV table — and still
bootstrappable from the three ``AMPERE_NOTIFY*`` env vars. This is the single resolver both the web
app and the scheduled ``run_daily`` job use, so **DB settings override env** identically in both.

Adapter-free (invariant #1): it reads only the ``SettingsRepo`` port + an env mapping and never
imports/builds a notifier — the composition roots turn a resolved ``NotifyConfig`` into a real
``Notifier`` via ``ampere.adapters.notify.build_notifier``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import BaseModel

from ampere.ports.repositories import UnitOfWork

# settings keys (also the seam the web endpoints + run_daily agree on)
KEY_KIND = "notify.kind"
KEY_TOKEN = "notify.telegram_token"
KEY_CHAT_ID = "notify.telegram_chat_id"


class NotifyConfig(BaseModel):
    """An effective, usable push-channel config. ``token``/``chat_id`` are set for telegram only."""

    kind: str
    token: str | None = None
    chat_id: str | None = None


def _normalize(kind: str | None) -> str | None:
    kind = (kind or "").strip().lower()
    return kind or None


def resolve_notify_config(
    uow: UnitOfWork, env: Mapping[str, str] | None = None
) -> NotifyConfig | None:
    """The effective channel: **DB config wins**, else env, else ``None``.

    Returns ``None`` when nothing is configured, when the kind is ``off``/empty, or when a
    ``telegram`` channel is missing either credential — so a half-configured channel reads as OFF
    and is never half-built (mirrors ``build_notifier``'s fail-fast, but as a silent "off" here).
    """
    env = os.environ if env is None else env

    db_kind = _normalize(uow.settings.get(KEY_KIND))
    if db_kind is not None:  # the presence of a stored kind is the switch to "use DB"
        kind, token, chat_id = (
            db_kind, uow.settings.get(KEY_TOKEN), uow.settings.get(KEY_CHAT_ID),
        )
    else:
        kind = _normalize(env.get("AMPERE_NOTIFY"))
        token = env.get("AMPERE_TELEGRAM_TOKEN") or None
        chat_id = env.get("AMPERE_TELEGRAM_CHAT_ID") or None

    if kind is None or kind == "off":
        return None
    if kind == "telegram" and not (token and chat_id):
        return None
    return NotifyConfig(kind=kind, token=token, chat_id=chat_id)


def save_notify_config(
    uow: UnitOfWork, *, kind: str, token: str | None = None, chat_id: str | None = None
) -> None:
    """Persist the channel. A falsy ``token``/``chat_id`` is left unchanged (so re-saving a
    telegram channel after editing only the chat id keeps the masked-and-untouched token)."""
    with uow.transaction():
        uow.settings.set(KEY_KIND, kind)
        if token:
            uow.settings.set(KEY_TOKEN, token)
        if chat_id:
            uow.settings.set(KEY_CHAT_ID, chat_id)


def clear_notify_config(uow: UnitOfWork) -> None:
    """Turn the channel off (delete all three keys) — falls back to env on the next resolve."""
    with uow.transaction():
        uow.settings.delete(KEY_KIND)
        uow.settings.delete(KEY_TOKEN)
        uow.settings.delete(KEY_CHAT_ID)


def notify_masked(cfg: NotifyConfig | None) -> dict:
    """A UI-safe view of the channel — the raw token **never** leaves the server, only whether one
    is set + its last-4 hint. ``None`` (nothing configured) reads as the ``off`` channel."""
    if cfg is None:
        return {"kind": "off", "chat_id": None, "token_set": False, "token_hint": None}
    return {
        "kind": cfg.kind,
        "chat_id": cfg.chat_id,
        "token_set": bool(cfg.token),
        "token_hint": cfg.token[-4:] if cfg.token else None,
    }
