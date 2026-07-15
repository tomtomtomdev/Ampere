"""Notifier implementations. All satisfy ``ampere.ports.notifier.Notifier``.

``build_notifier`` is the composition-root selector (mirrors ``build_source``): the daily job / web
app pick a channel by kind from env, with zero impact on the ``notify_daily`` use-case. Telegram
needs ``token`` + ``chat_id``; ``stdout`` is the credential-free dry-run channel.
"""

from __future__ import annotations

from ampere.adapters.notify.stdout import StdoutNotifier
from ampere.adapters.notify.telegram import TelegramNotifier
from ampere.ports.notifier import Notifier


def build_notifier(
    kind: str,
    *,
    token: str | None = None,
    chat_id: str | None = None,
    stream=None,
) -> Notifier:
    """Instantiate a notifier by kind (``telegram`` | ``stdout``).

    Raises ``ValueError`` for an unknown kind, or for ``telegram`` without both credentials — so a
    half-configured push channel fails fast at startup rather than silently dropping the digest.
    """
    key = kind.lower()
    if key == "stdout":
        return StdoutNotifier(stream=stream)
    if key == "telegram":
        if not token or not chat_id:
            raise ValueError(
                "telegram notifier needs AMPERE_TELEGRAM_TOKEN and AMPERE_TELEGRAM_CHAT_ID"
            )
        return TelegramNotifier(token=token, chat_id=chat_id)
    raise ValueError(f"unknown notifier kind: {kind!r} (known: stdout, telegram)")


__all__ = ["StdoutNotifier", "TelegramNotifier", "build_notifier"]
