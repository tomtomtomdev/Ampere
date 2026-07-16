"""M8 — daily push notification (SPEC §11.2), written test-first.

The natural output of a daily run — "the best-value phone in the band + the Pareto frontier" —
is pushed to a channel (Telegram) after the scheduled run. The seam mirrors M5/M6: the fragile
networked part (the Telegram Bot API call) is an injected transport, so the *content* selection
(``build_push_digest``) and *rendering* (``render_digest``) are pure and fully offline-tested;
``notify_daily`` orchestrates build → render → send and is tested with a fake ``Notifier``.

Off by default: no channel configured ⇒ nothing is pushed (the composition root wires a notifier
only when env supplies one). The digest reflects what was PERSISTED (default weights, toggles off,
SC3), so the push agrees with the dashboard.
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.notify import build_notifier
from ampere.adapters.notify.stdout import StdoutNotifier
from ampere.adapters.notify.telegram import TelegramNotifier
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.application.notify import (
    PushDigest,
    PushItem,
    build_push_digest,
    notify_daily,
    render_digest,
)
from ampere.application.run_daily import RunConfig, run_daily
from ampere.domain.models import (
    BatteryMetricKind,
    Chipset,
    Device,
)

_D1 = date(2026, 7, 12)
_D2 = date(2026, 7, 13)

# Illustrative catalog — same shape as tests/test_run_daily.py (NOT real benchmarks).
_CHIPSETS = [
    ("dimensity-6080", 760, 1990, 410_000, 790),
    ("snapdragon-4-gen-2", 900, 2050, 450_000, 850),
    ("helio-g99", 730, 1950, 400_000, 760),
    ("helio-g85", 520, 1620, 360_000, 720),
    ("dimensity-6300", 780, 2100, 430_000, 820),
    ("exynos-1330", 900, 2100, 410_000, 800),
]
_DEVICES = [
    ("dev-rn13-8-256", "Xiaomi", "Redmi Note 13", "8/256", "dimensity-6080", 15.0),
    ("dev-pocom6-6-128", "Xiaomi", "Poco M6 5G", "6/128", "snapdragon-4-gen-2", 13.5),
    ("dev-hot40pro-8-256", "Infinix", "Hot 40 Pro", "8/256", "helio-g99", 16.0),
    ("dev-a15-8-256", "Samsung", "Galaxy A15", "8/256", "exynos-1330", 14.0),
    ("dev-r13c-8-256", "Xiaomi", "Redmi 13C", "8/256", "helio-g85", 13.0),
    ("dev-rn13r-8-256", "Xiaomi", "Redmi Note 13R", "8/256", "dimensity-6300", 14.5),
]


def _seed_catalog(uow: SqliteUnitOfWork) -> None:
    for cid, s, m, a, w in _CHIPSETS:
        uow.chipsets.upsert(
            Chipset(id=cid, name=cid, gb6_single=s, gb6_multi=m, antutu=a, wildlife=w)
        )
    for did, brand, model, variant, cid, hours in _DEVICES:
        uow.devices.upsert(
            Device(id=did, brand=brand, model=model, variant=variant, chipset_id=cid,
                   active_use_hours=hours, battery_metric_kind=BatteryMetricKind.ACTIVE_USE_V2)
        )


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    u = SqliteUnitOfWork(conn)
    _seed_catalog(u)
    return u


class FakeNotifier:
    """Captures whatever is pushed, so the send is asserted without any network."""

    kind = "fake"

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def _run(uow, source=None):
    return run_daily(
        source=source or FixtureSource(), uow=uow, snapshot_date=_D2,
        keyword="android", price_min=1_000_000, price_max=2_000_000,
    )


# ---------------------------------------------------------------------------
# build_push_digest — content selection matches the persisted frontier (SC3)
# ---------------------------------------------------------------------------
class TestBuildDigest:
    def test_none_when_no_snapshot(self, uow):
        assert build_push_digest(uow, None) is None

    def test_frontier_matches_persisted_and_is_ranked_by_value(self, uow):
        result = _run(uow)
        digest = build_push_digest(uow, _D2, source_kind="fixture")

        assert digest is not None
        assert digest.snapshot_date == _D2
        assert digest.source_kind == "fixture"
        assert digest.scoring_version  # pinned
        # the pushed frontier is exactly the persisted non-dominated set (SC3)
        persisted_frontier = {s.listing_id for s in uow.scores.for_snapshot(_D2) if s.is_frontier}
        assert {item.shopee_id for item in digest.frontier} == persisted_frontier
        assert len(digest.frontier) == result.frontier_size
        # ranked by value, highest first, ranks 1..N contiguous
        values = [item.value for item in digest.frontier]
        assert values == sorted(values, reverse=True)
        assert [item.rank for item in digest.frontier] == list(range(1, len(digest.frontier) + 1))

    def test_best_value_is_the_top_frontier_point(self, uow):
        _run(uow)
        digest = build_push_digest(uow, _D2)
        assert digest is not None and digest.best_value is not None
        assert digest.best_value == digest.frontier[0]
        assert digest.best_value.value == max(item.value for item in digest.frontier)
        # enriched with catalog data, not just ids
        assert digest.best_value.model and digest.best_value.chip != "—"

    def test_frontier_limit_truncates_but_keeps_the_top(self, uow):
        _run(uow)
        full = build_push_digest(uow, _D2)
        capped = build_push_digest(uow, _D2, frontier_limit=1)
        assert full is not None and capped is not None
        assert len(capped.frontier) == 1
        assert capped.frontier[0] == full.frontier[0]  # kept the best-value pick
        assert capped.best_value == full.best_value

    def test_counts_reflect_the_diff_vs_prior(self, uow):
        # a first-ever run has no prior snapshot, so every listing is a new arrival.
        _run(uow)
        digest = build_push_digest(uow, _D2)
        assert digest is not None
        assert digest.new_arrivals >= 1

    def test_none_when_snapshot_has_no_scoreable_listings(self):
        # devices resolve but their chipset is a "pending refresh" stub (null benchmarks, as M6
        # seeds before the first refresh) -> nothing scoreable -> empty frontier.
        conn = db.connect(":memory:")
        db.create_schema(conn)
        u = SqliteUnitOfWork(conn)
        for cid, *_ in _CHIPSETS:
            u.chipsets.upsert(Chipset(id=cid, name=cid))  # name only, no benchmark numbers
        for did, brand, model, variant, cid, hours in _DEVICES:
            u.devices.upsert(
                Device(id=did, brand=brand, model=model, variant=variant, chipset_id=cid,
                       active_use_hours=hours, battery_metric_kind=BatteryMetricKind.ACTIVE_USE_V2)
            )
        _run(u)
        digest = build_push_digest(u, _D2)
        assert digest is not None
        assert digest.frontier == [] and digest.best_value is None


# ---------------------------------------------------------------------------
# render_digest — pure formatting, tested on a fabricated digest
# ---------------------------------------------------------------------------
def _sample_digest() -> PushDigest:
    return PushDigest(
        snapshot_date=date(2026, 7, 15), keyword="android",
        price_min=1_000_000, price_max=2_000_000, source_kind="affiliate",
        scoring_version="v2.1.0", new_arrivals=2, price_drops=3,
        best_value=PushItem(
            rank=1, shopee_id="L05", model="Poco M6 5G", variant="6/128",
            chip="Snapdragon 4 Gen 2", condition="new", effective_price=1_669_000,
            capability=61.4, value=36.8, url="https://s.shopee.co.id/aff-L05",
        ),
        frontier=[
            PushItem(rank=1, shopee_id="L05", model="Poco M6 5G", variant="6/128",
                     chip="Snapdragon 4 Gen 2", condition="new", effective_price=1_669_000,
                     capability=61.4, value=36.8, url="https://s.shopee.co.id/aff-L05"),
            PushItem(rank=2, shopee_id="L13", model="Redmi 13C", variant="8/256",
                     chip="Helio G85", condition="new", effective_price=1_399_000,
                     capability=48.0, value=34.3, url="https://s.shopee.co.id/aff-L13"),
        ],
    )


class TestRenderDigest:
    def test_includes_band_date_version_and_keyword(self):
        text = render_digest(_sample_digest())
        assert "android" in text
        assert "2026-07-15" in text
        assert "v2.1.0" in text
        assert "1.00jt" in text and "2.00jt" in text  # the band

    def test_headlines_the_best_value_pick_with_its_affiliate_url(self):
        text = render_digest(_sample_digest())
        assert "Poco M6 5G" in text and "6/128" in text
        assert "Snapdragon 4 Gen 2" in text
        assert "https://s.shopee.co.id/aff-L05" in text  # outbound affiliate link (§11.2)

    def test_lists_the_frontier_and_the_change_counts(self):
        text = render_digest(_sample_digest())
        assert "Redmi 13C" in text  # the #2 frontier point
        assert "https://s.shopee.co.id/aff-L13" in text
        assert "2 new" in text and "3 price drop" in text  # diff counts, phrased

    def test_empty_frontier_renders_a_no_frontier_line(self):
        empty = _sample_digest().model_copy(update={"best_value": None, "frontier": []})
        text = render_digest(empty)
        assert "frontier" in text.lower()  # informative, not a crash


# ---------------------------------------------------------------------------
# notify_daily — orchestration + guards
# ---------------------------------------------------------------------------
class TestNotifyDaily:
    def test_sends_rendered_digest_once(self, uow):
        _run(uow)
        notifier = FakeNotifier()
        digest = notify_daily(uow, notifier, snapshot_date=_D2, source_kind="fixture")
        assert digest is not None
        assert len(notifier.sent) == 1
        assert notifier.sent[0] == render_digest(digest)
        assert digest.best_value.model in notifier.sent[0]

    def test_does_not_send_when_no_snapshot(self, uow):
        notifier = FakeNotifier()
        assert notify_daily(uow, notifier, snapshot_date=None) is None
        assert notifier.sent == []

    def test_does_not_send_when_frontier_empty(self):
        conn = db.connect(":memory:")
        db.create_schema(conn)
        u = SqliteUnitOfWork(conn)  # empty catalog -> nothing scoreable
        _run(u)
        notifier = FakeNotifier()
        assert notify_daily(u, notifier, snapshot_date=_D2) is None
        assert notifier.sent == []

    def test_send_failure_propagates(self, uow):
        _run(uow)

        class Boom:
            kind = "boom"

            def send(self, text: str) -> None:
                raise RuntimeError("telegram down")

        with pytest.raises(RuntimeError):
            notify_daily(uow, Boom(), snapshot_date=_D2)


# ---------------------------------------------------------------------------
# adapters — the injected-transport seam (network never touched in tests)
# ---------------------------------------------------------------------------
class TestNotifierAdapters:
    def test_build_telegram(self):
        n = build_notifier("telegram", token="T", chat_id="C")
        assert isinstance(n, TelegramNotifier) and n.kind == "telegram"

    def test_build_stdout(self):
        assert build_notifier("stdout").kind == "stdout"

    def test_build_unknown_raises(self):
        with pytest.raises(ValueError):
            build_notifier("carrier-pigeon")

    def test_telegram_missing_credentials_raises(self):
        with pytest.raises(ValueError):
            build_notifier("telegram", token=None, chat_id=None)

    def test_stdout_notifier_writes_the_text(self):
        import io

        buf = io.StringIO()
        StdoutNotifier(stream=buf).send("hello frontier")
        assert "hello frontier" in buf.getvalue()

    def test_telegram_builds_correct_bot_api_call(self):
        calls: list[tuple[str, dict]] = []
        n = TelegramNotifier(
            token="123:ABC", chat_id="42", transport=lambda url, p: calls.append((url, p))
        )
        n.send("digest body")
        assert len(calls) == 1
        url, payload = calls[0]
        assert url == "https://api.telegram.org/bot123:ABC/sendMessage"
        assert payload["chat_id"] == "42"
        assert payload["text"] == "digest body"
        assert payload["disable_web_page_preview"] is True


# ---------------------------------------------------------------------------
# RunConfig — the composition root reads the channel from env (off by default)
# ---------------------------------------------------------------------------
class TestRunConfigNotifyEnv:
    def test_defaults_off(self):
        cfg = RunConfig.from_env({})
        assert cfg.notify_kind is None
        assert cfg.telegram_token is None and cfg.telegram_chat_id is None

    def test_reads_telegram_env(self):
        cfg = RunConfig.from_env(
            {"AMPERE_NOTIFY": "telegram", "AMPERE_TELEGRAM_TOKEN": "tok",
             "AMPERE_TELEGRAM_CHAT_ID": "chat"}
        )
        assert cfg.notify_kind == "telegram"
        assert cfg.telegram_token == "tok" and cfg.telegram_chat_id == "chat"


# ---------------------------------------------------------------------------
# The scheduled push resolves the channel DB-first (a UI-set channel drives it too) — §11.2
# ---------------------------------------------------------------------------
class TestDailyPushHonorsDbConfig:
    @pytest.fixture(autouse=True)
    def _clean_notify_env(self, monkeypatch):
        for key in ("AMPERE_NOTIFY", "AMPERE_TELEGRAM_TOKEN", "AMPERE_TELEGRAM_CHAT_ID"):
            monkeypatch.delenv(key, raising=False)

    def test_db_configured_channel_is_pushed(self, uow, capsys):
        from ampere.application.notify_config import save_notify_config
        from ampere.application.run_daily import _push_daily_digest

        result = _run(uow)  # persists a snapshot with a non-empty frontier
        assert result.frontier_size > 0
        save_notify_config(uow, kind="stdout")  # configured via the UI/DB, no env
        _push_daily_digest(RunConfig(), uow, result)
        assert "frontier" in capsys.readouterr().out.lower()

    def test_nothing_configured_pushes_nothing(self, uow, capsys):
        from ampere.application.run_daily import _push_daily_digest

        _push_daily_digest(RunConfig(), uow, _run(uow))  # no DB config, clean env
        assert capsys.readouterr().out == ""
