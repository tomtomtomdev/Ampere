"""``application/notify_config.py`` — resolve the push channel from persisted settings or env.

The push channel (SPEC §11.2) is configurable from the UI (persisted in the ``settings`` KV table)
and still bootstrappable from env. This module is the single resolver both the web app and the
scheduled ``run_daily`` job use, so "DB overrides env" holds identically in both. Adapter-free —
it only reads the ``SettingsRepo`` port + env, never builds a notifier (invariant #1).
"""

from __future__ import annotations

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.application.notify_config import (
    clear_notify_config,
    notify_masked,
    resolve_notify_config,
    save_notify_config,
)

_TELEGRAM_ENV = {
    "AMPERE_NOTIFY": "telegram",
    "AMPERE_TELEGRAM_TOKEN": "123456:ABC-TOKEN",
    "AMPERE_TELEGRAM_CHAT_ID": "999",
}


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    return SqliteUnitOfWork(conn)


class TestResolve:
    def test_none_when_nothing_configured(self, uow):
        assert resolve_notify_config(uow, env={}) is None

    def test_off_kind_is_none(self, uow):
        assert resolve_notify_config(uow, env={"AMPERE_NOTIFY": "off"}) is None

    def test_env_telegram_with_both_creds(self, uow):
        cfg = resolve_notify_config(uow, env=_TELEGRAM_ENV)
        assert cfg is not None
        assert cfg.kind == "telegram" and cfg.token == "123456:ABC-TOKEN" and cfg.chat_id == "999"

    def test_env_telegram_missing_chat_id_reads_as_off(self, uow):
        env = {"AMPERE_NOTIFY": "telegram", "AMPERE_TELEGRAM_TOKEN": "t"}
        assert resolve_notify_config(uow, env=env) is None

    def test_env_stdout_needs_no_creds(self, uow):
        cfg = resolve_notify_config(uow, env={"AMPERE_NOTIFY": "stdout"})
        assert cfg is not None and cfg.kind == "stdout"

    def test_db_kind_overrides_env(self, uow):
        uow.settings.set("notify.kind", "stdout")
        cfg = resolve_notify_config(uow, env=_TELEGRAM_ENV)  # env says telegram; DB wins
        assert cfg is not None and cfg.kind == "stdout"

    def test_db_telegram_resolves_from_db(self, uow):
        save_notify_config(uow, kind="telegram", token="tok", chat_id="42")
        cfg = resolve_notify_config(uow, env={})
        assert cfg is not None and cfg.token == "tok" and cfg.chat_id == "42"


class TestSaveClear:
    def test_save_then_resolve_round_trips(self, uow):
        save_notify_config(uow, kind="telegram", token="tok", chat_id="42")
        cfg = resolve_notify_config(uow, env={})
        assert cfg.kind == "telegram" and cfg.token == "tok" and cfg.chat_id == "42"

    def test_save_without_token_keeps_existing_token(self, uow):
        save_notify_config(uow, kind="telegram", token="tok", chat_id="42")
        save_notify_config(uow, kind="telegram", token=None, chat_id="43")  # user only changed chat
        cfg = resolve_notify_config(uow, env={})
        assert cfg.token == "tok" and cfg.chat_id == "43"

    def test_clear_turns_it_off(self, uow):
        save_notify_config(uow, kind="telegram", token="tok", chat_id="42")
        clear_notify_config(uow)
        assert resolve_notify_config(uow, env={}) is None


class TestMasking:
    def test_none_masks_as_off(self):
        m = notify_masked(None)
        assert m == {"kind": "off", "chat_id": None, "token_set": False, "token_hint": None}

    def test_telegram_masks_token_but_keeps_hint(self, uow):
        save_notify_config(uow, kind="telegram", token="123456:ABCDEF", chat_id="42")
        m = notify_masked(resolve_notify_config(uow, env={}))
        assert m["kind"] == "telegram" and m["chat_id"] == "42"
        assert m["token_set"] is True and m["token_hint"] == "CDEF"
        assert "123456:ABCDEF" not in str(m)  # the raw token never leaks
