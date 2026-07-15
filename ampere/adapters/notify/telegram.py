"""``TelegramNotifier`` — push the daily digest to a Telegram chat via the Bot API (SPEC §11.2).

The transport (the actual HTTP POST) is the fragile networked part, so — like the M5/M6 sources —
it is injected as a ``transport`` callable and defaults to a best-effort ``httpx`` POST that is NOT
exercised in tests (no network in CI). The pure part — building the correct Bot API URL + payload —
is exercised through an injected transport, so a wrong endpoint/field fails offline.

Setup (once): create a bot via @BotFather → get the token; message the bot (or add it to a group)
and resolve the numeric ``chat_id``. Provide both via ``AMPERE_TELEGRAM_TOKEN`` /
``AMPERE_TELEGRAM_CHAT_ID`` and set ``AMPERE_NOTIFY=telegram``.
"""

from __future__ import annotations

from collections.abc import Callable

_API = "https://api.telegram.org"


def _httpx_post(url: str, payload: dict) -> None:
    """Best-effort live transport (plain ``httpx`` POST). Not exercised in tests."""
    import httpx  # lazy: only the live path needs it

    resp = httpx.post(url, json=payload, timeout=20.0)
    resp.raise_for_status()


class TelegramNotifier:
    """A ``Notifier`` over the Telegram Bot API ``sendMessage`` method."""

    kind = "telegram"

    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        transport: Callable[[str, dict], None] | None = None,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("TelegramNotifier requires both token and chat_id")
        self._token = token
        self._chat_id = chat_id
        self._transport = transport or _httpx_post

    def send(self, text: str) -> None:
        url = f"{_API}/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_web_page_preview": True,  # affiliate links inline, no giant unfurl per link
        }
        self._transport(url, payload)
