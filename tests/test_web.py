"""M4 — FastAPI transport (SPEC §8), written test-first.

Endpoints are a thin skin over the read-model builders + ``run_daily`` (no business logic in the
web layer — CLAUDE.md). Uses a temp-file SQLite DB seeded via the demo bootstrap and Starlette's
TestClient. A fixed clock makes ``POST /api/run`` deterministic.
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.application.demo_seed import bootstrap
from ampere.domain.resolve import alias_key
from ampere.web.api import create_app
from fastapi.testclient import TestClient

_TODAY = date(2026, 7, 14)


@pytest.fixture(autouse=True)
def _clean_notify_env(monkeypatch):
    """Isolate the push-channel tests from the dev's shell: the DB-backed notifier factory resolves
    from persisted settings ELSE env, so a stray ``AMPERE_NOTIFY`` would make "off" tests flap."""
    for key in ("AMPERE_NOTIFY", "AMPERE_TELEGRAM_TOKEN", "AMPERE_TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "ampere.db")
    conn = db.connect(path)
    db.create_schema(conn)
    bootstrap(SqliteUnitOfWork(conn), today=_TODAY)
    conn.close()
    return path


@pytest.fixture
def client(db_path) -> TestClient:
    def uow_factory():
        return SqliteUnitOfWork(db.connect(db_path, check_same_thread=False))

    app = create_app(uow_factory=uow_factory, source_factory=FixtureSource, clock=lambda: _TODAY)
    return TestClient(app)


@pytest.fixture
def push_client(db_path):
    """A client whose app has a notifier injected directly (bypassing config), plus the captured
    messages — for exercising the send mechanics of ``POST /api/notify`` (M8)."""
    sent: list[str] = []

    class _Capture:
        kind = "capture"

        def send(self, text: str) -> None:
            sent.append(text)

    capture = _Capture()

    def uow_factory():
        return SqliteUnitOfWork(db.connect(db_path, check_same_thread=False))

    app = create_app(
        uow_factory=uow_factory, source_factory=FixtureSource, clock=lambda: _TODAY,
        notifier_factory=lambda uow: capture,
    )
    return TestClient(app), sent


class TestStaticShell:
    def test_root_serves_the_spa(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "AMPERE" in resp.text


class TestDashboard:
    def test_returns_points_and_meta(self, client):
        data = client.get("/api/dashboard").json()
        assert len(data["points"]) == 7
        assert data["meta"]["snapshot_date"] == _TODAY.isoformat()
        assert data["meta"]["stats"]["deduped"] == 7
        assert any(p["is_frontier"] for p in data["points"])

    def test_weight_query_param_re_scores_live(self, client):
        perf_heavy = client.get("/api/dashboard", params={"w_perf": 0.9}).json()
        batt_heavy = client.get("/api/dashboard", params={"w_perf": 0.1}).json()
        cap_a = {p["shopee_id"]: p["capability"] for p in perf_heavy["points"]}
        cap_b = {p["shopee_id"]: p["capability"] for p in batt_heavy["points"]}
        assert cap_a["L01"] != cap_b["L01"]
        assert perf_heavy["weights"]["w_perf"] == pytest.approx(0.9)


class TestListings:
    def test_rows(self, client):
        data = client.get("/api/listings").json()
        assert len(data["rows"]) == 7
        assert all("capability" in r and "value" in r for r in data["rows"])


class TestCatalog:
    def test_needs_mapping_and_chipsets(self, client):
        data = client.get("/api/catalog").json()
        assert {n["shopee_id"] for n in data["needs_mapping"]} == {"L22", "L23"}
        assert any(c["used_by"] == 2 for c in data["chipsets"])


class TestChanges:
    def test_diff_vs_prior(self, client):
        data = client.get("/api/changes").json()
        assert data["prior_date"] == date(2026, 7, 13).isoformat()
        assert "L01" in {d["shopee_id"] for d in data["price_drops"]}


class TestSettings:
    def test_settings_payload(self, client):
        data = client.get("/api/settings").json()
        assert data["keyword"] == "android"
        assert "fixture" in data["sources"]
        assert data["scoring_version"] == "v2.1.0"


class TestRunNow:
    def test_run_endpoint_triggers_a_snapshot(self, client):
        resp = client.post("/api/run")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["listing_count"] == 9
        assert body["snapshot_date"] == _TODAY.isoformat()


class TestNeedsMappingResolver:
    def test_map_remembers_alias_and_next_run_resolves_it(self, client, db_path):
        title = "HP Android RAM 8/256 Baru Garansi Murah Meriah Promo COD Bisa Bayar Ditempat"
        resp = client.post(
            "/api/catalog/map", json={"title": title, "device_id": "dev-rn13-8-256"}
        )
        assert resp.status_code == 200

        # the alias is persisted under the resolver's lookup key
        conn = db.connect(db_path, check_same_thread=False)
        assert SqliteUnitOfWork(conn).aliases.lookup(alias_key(title)) == "dev-rn13-8-256"
        conn.close()

        # and a subsequent run resolves L22, so it leaves the needs-mapping queue
        client.post("/api/run")
        data = client.get("/api/catalog").json()
        assert "L22" not in {n["shopee_id"] for n in data["needs_mapping"]}


class TestBonusToggles:
    """M7: longevity bonus (§11.1) + trust penalty (§5.6) are per-request query params, off by
    default, that re-score live (like the weight sliders); trust_score is a listing column."""

    def test_longevity_query_param_raises_capability(self, client):
        base = client.get("/api/listings").json()["rows"]
        boosted = client.get("/api/listings", params={"longevity": "true"}).json()["rows"]
        cap_a = {r["shopee_id"]: r["capability"] for r in base}
        cap_b = {r["shopee_id"]: r["capability"] for r in boosted}
        # every demo device promises >=2 OS-update years, so enabling the bonus can only raise cap
        assert all(cap_b[k] >= cap_a[k] for k in cap_a)
        assert any(cap_b[k] > cap_a[k] for k in cap_a)

    def test_trust_penalty_query_param_leaves_mall_value_unchanged(self, client):
        base = client.get("/api/listings").json()["rows"]
        pen = client.get("/api/listings", params={"trust_penalty": "true"}).json()["rows"]
        val_a = {r["shopee_id"]: r["value"] for r in base}
        val_b = {r["shopee_id"]: r["value"] for r in pen}
        # L01 is a Mall store -> the low-trust penalty never applies, value is identical
        assert val_b["L01"] == pytest.approx(val_a["L01"])

    def test_listing_rows_carry_trust_score(self, client):
        rows = client.get("/api/listings").json()["rows"]
        assert all("trust_score" in r for r in rows)
        row = next(r for r in rows if r["shopee_id"] == "L01")
        assert row["trust_score"] is not None and row["trust_score"] >= 90

    def test_settings_reflects_the_toggles(self, client):
        on = client.get(
            "/api/settings", params={"longevity": "true", "trust_penalty": "true"}
        ).json()
        assert on["longevity_bonus_enabled"] is True and on["trust_penalty_enabled"] is True
        off = client.get("/api/settings").json()
        assert off["longevity_bonus_enabled"] is False and off["trust_penalty_enabled"] is False


class TestDailyPush:
    """M8: POST /api/notify is the manual counterpart to the scheduled daily push (SPEC §11.2).
    It pushes the current snapshot's best-value pick + frontier through the wired notifier."""

    def test_notify_endpoint_pushes_the_digest(self, push_client):
        client, sent = push_client
        resp = client.post("/api/notify")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] == "true" and body["sent"] == "true"
        assert len(sent) == 1 and "frontier" in sent[0].lower()

    def test_notify_endpoint_reports_when_not_configured(self, client):
        # the default app resolves no channel (no DB config, clean env) -> reports rather than 500s.
        resp = client.post("/api/notify")
        assert resp.status_code == 200
        assert resp.json()["ok"] == "false"


class TestNotifyChannelConfig:
    """The push channel is set from the UI + persisted, so both 'Share now' and the daily push work
    without env vars (SPEC §11.2). The DB-backed factory resolves the channel per request."""

    def test_default_is_off_and_masked(self, client):
        data = client.get("/api/settings").json()
        assert data["notify_configured"] is False
        assert data["notify"] == {
            "kind": "off", "chat_id": None, "token_set": False, "token_hint": None
        }

    def test_configure_stdout_enables_and_pushes(self, client):
        r = client.post("/api/settings/notify", json={"kind": "stdout"})
        assert r.status_code == 200 and r.json()["kind"] == "stdout"
        # the channel now resolves -> settings reports configured...
        assert client.get("/api/settings").json()["notify_configured"] is True
        # ...and the DB-backed factory builds it, so POST /api/notify actually sends (no injection).
        assert client.post("/api/notify").json() == {"ok": "true", "sent": "true"}

    def test_configure_telegram_masks_token(self, client):
        r = client.post(
            "/api/settings/notify",
            json={"kind": "telegram", "token": "123456:ABCDEF", "chat_id": "42"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "telegram" and body["chat_id"] == "42"
        assert body["token_set"] is True and body["token_hint"] == "CDEF"
        # the raw token never appears anywhere in the settings payload
        settings = client.get("/api/settings").json()
        assert "123456:ABCDEF" not in str(settings)
        assert settings["notify"]["token_set"] is True

    def test_telegram_without_chat_id_is_rejected(self, client):
        r = client.post("/api/settings/notify", json={"kind": "telegram", "token": "t"})
        assert r.status_code == 400

    def test_editing_chat_id_keeps_the_saved_token(self, client):
        client.post(
            "/api/settings/notify", json={"kind": "telegram", "token": "tok", "chat_id": "1"}
        )
        # re-save with only the chat id changed (token left blank, as the masked UI does)
        r = client.post("/api/settings/notify", json={"kind": "telegram", "chat_id": "2"})
        assert r.status_code == 200
        assert r.json()["chat_id"] == "2" and r.json()["token_set"] is True

    def test_off_clears_the_channel(self, client):
        client.post("/api/settings/notify", json={"kind": "stdout"})
        client.post("/api/settings/notify", json={"kind": "off"})
        assert client.get("/api/settings").json()["notify_configured"] is False

    def test_send_test_hits_the_bot_api_via_injected_transport(self, db_path):
        calls: list[tuple[str, dict]] = []

        def uow_factory():
            return SqliteUnitOfWork(db.connect(db_path, check_same_thread=False))

        app = create_app(
            uow_factory=uow_factory, source_factory=FixtureSource, clock=lambda: _TODAY,
            notifier_transport=lambda url, payload: calls.append((url, payload)),
        )
        c = TestClient(app)
        c.post("/api/settings/notify", json={"kind": "telegram", "token": "TKN", "chat_id": "42"})
        assert c.post("/api/settings/notify/test").json() == {"ok": "true"}
        assert len(calls) == 1
        url, payload = calls[0]
        assert url == "https://api.telegram.org/botTKN/sendMessage"
        assert payload["chat_id"] == "42" and "Ampere connected" in payload["text"]

    def test_send_test_reports_when_off(self, client):
        assert client.post("/api/settings/notify/test").json()["ok"] == "false"


class TestReportPage:
    """M9: GET /api/report serves the self-contained shareable HTML snapshot (SPEC §11.2)."""

    def test_serves_self_contained_html(self, client):
        resp = client.get("/api/report")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert resp.text.lstrip().lower().startswith("<!doctype html")
        assert "AMPERE" in resp.text.upper()
        assert "<svg" in resp.text  # the inline Pareto scatter
