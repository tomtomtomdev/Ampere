"""FastAPI app — thin transport over the read-model builders + ``run_daily`` (PLAN M4).

No business logic here (CLAUDE.md): each endpoint resolves the current snapshot, builds the request
params, and hands off to ``ampere.application.views`` / ``run_daily``. Scoring, dedup, and the
Pareto frontier live in the domain layer and are recomputed server-side, so weight sliders re-score
live without any math leaking into the browser.

The app is built by ``create_app`` around an injected ``uow_factory`` (composition root wires
SQLite) — this keeps the transport testable with a temp DB and swappable per SPEC's Clean layering.

Run:  uvicorn ampere.web.api:app --reload   (needs the ``web`` extra installed)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ampere.adapters.notify import build_notifier
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.application import views
from ampere.application.demo_seed import bootstrap
from ampere.application.notify import notify_daily
from ampere.application.notify_config import (
    clear_notify_config,
    notify_masked,
    resolve_notify_config,
    save_notify_config,
)
from ampere.application.report import build_report, render_report
from ampere.application.run_daily import catch_up, run_daily
from ampere.application.views import ViewParams
from ampere.config import (
    DEFAULT_KEYWORD,
    DEFAULT_PRICE_MAX,
    DEFAULT_PRICE_MIN,
    LONGEVITY_BONUS_ENABLED,
    TRUST_PENALTY_ENABLED,
)
from ampere.domain.models import RunResult, Weights
from ampere.domain.resolve import alias_key
from ampere.ports.notifier import Notifier
from ampere.ports.repositories import UnitOfWork
from ampere.ports.search_source import SearchSource

STATIC_DIR = Path(__file__).with_name("static")


class RunRequest(BaseModel):
    """Optional overrides for the manual fallback run (SPEC §8/§8a — daily fetch is automatic)."""

    keyword: str = DEFAULT_KEYWORD
    price_min: int = DEFAULT_PRICE_MIN
    price_max: int = DEFAULT_PRICE_MAX
    w_perf: float | None = None
    mall_only: bool = False


class MapRequest(BaseModel):
    """Resolve a needs-mapping listing by learning an alias -> device_id (SPEC §7 step 5a)."""

    title: str
    device_id: str


class NotifyConfigRequest(BaseModel):
    """Set the push channel from the UI (SPEC §11.2). ``kind`` ∈ {off, stdout, telegram}. A blank
    ``token`` on an existing telegram channel is treated as "unchanged" (it is never prefilled)."""

    kind: str
    token: str | None = None
    chat_id: str | None = None


def _weights(w_perf: float | None) -> Weights:
    return Weights(w_perf=w_perf) if w_perf is not None else Weights()


def _params(
    *,
    w_perf: float | None,
    blended: bool,
    longevity: bool,
    trust_penalty: bool,
    mall_only: bool,
    keyword: str,
    price_min: int,
    price_max: int,
    source_kind: str,
) -> ViewParams:
    return ViewParams(
        weights=_weights(w_perf), blended=blended, longevity_bonus_enabled=longevity,
        trust_penalty_enabled=trust_penalty, mall_only=mall_only,
        keyword=keyword, price_min=price_min, price_max=price_max, source_kind=source_kind,
    )


def create_app(
    *,
    uow_factory: Callable[[], UnitOfWork],
    source_factory: Callable[[], SearchSource] = FixtureSource,
    clock: Callable[[], date] = date.today,
    on_startup: Callable[[], None] | None = None,
    notifier_factory: Callable[[UnitOfWork], Notifier | None] | None = None,
    notifier_transport: Callable[[str, dict], None] | None = None,
) -> FastAPI:
    """Build the app. ``uow_factory`` returns a fresh UoW per request (composition root wires it).

    ``on_startup`` (optional) runs once when the app begins serving — the default app uses it to
    seed the demo DB. Tests omit it (no import-time or startup side effects on the real DB).

    The push channel (SPEC §11.2) is **configured from persisted settings/env**, not hard-wired: by
    default the factory reads ``resolve_notify_config`` per request and builds a notifier (or
    returns ``None`` when nothing is configured). ``notifier_transport`` injects the telegram HTTP
    POST (the offline-testable seam). A test may pass an explicit ``notifier_factory`` to bypass it.
    """
    if notifier_factory is None:

        def notifier_factory(uow: UnitOfWork) -> Notifier | None:  # noqa: F811 (default impl)
            cfg = resolve_notify_config(uow, os.environ)
            if cfg is None:
                return None
            return build_notifier(
                cfg.kind, token=cfg.token, chat_id=cfg.chat_id, transport=notifier_transport,
            )

    lifespan = None
    if on_startup is not None:

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            on_startup()
            yield

    app = FastAPI(title="Ampere", version="0.1.0", lifespan=lifespan)

    def get_uow() -> Iterator[UnitOfWork]:
        uow = uow_factory()
        try:
            yield uow
        finally:
            close = getattr(uow, "close", None)
            if close is not None:
                close()

    # ``Depends`` lives in the default (not an ``Annotated`` marker): with ``from __future__ import
    # annotations`` FastAPI evaluates annotations against module globals, where the ``get_uow``
    # closure is invisible — the default value is a real object, so it resolves correctly.
    @app.get("/api/dashboard")
    def dashboard(
        uow: UnitOfWork = Depends(get_uow),
        w_perf: float | None = None,
        blended: bool = False,
        longevity: bool = LONGEVITY_BONUS_ENABLED,
        trust_penalty: bool = TRUST_PENALTY_ENABLED,
        mall_only: bool = False,
        keyword: str = DEFAULT_KEYWORD,
        price_min: int = DEFAULT_PRICE_MIN,
        price_max: int = DEFAULT_PRICE_MAX,
    ) -> views.DashboardView:
        params = _params(
            w_perf=w_perf, blended=blended, longevity=longevity, trust_penalty=trust_penalty,
            mall_only=mall_only, keyword=keyword,
            price_min=price_min, price_max=price_max, source_kind=source_factory().kind,
        )
        return views.build_dashboard(uow, views.current_snapshot(uow), params)

    @app.get("/api/listings")
    def listings(
        uow: UnitOfWork = Depends(get_uow),
        w_perf: float | None = None,
        blended: bool = False,
        longevity: bool = LONGEVITY_BONUS_ENABLED,
        trust_penalty: bool = TRUST_PENALTY_ENABLED,
        mall_only: bool = False,
        keyword: str = DEFAULT_KEYWORD,
        price_min: int = DEFAULT_PRICE_MIN,
        price_max: int = DEFAULT_PRICE_MAX,
    ) -> views.ListingsView:
        params = _params(
            w_perf=w_perf, blended=blended, longevity=longevity, trust_penalty=trust_penalty,
            mall_only=mall_only, keyword=keyword,
            price_min=price_min, price_max=price_max, source_kind=source_factory().kind,
        )
        return views.build_listings(uow, views.current_snapshot(uow), params)

    @app.get("/api/catalog")
    def catalog(uow: UnitOfWork = Depends(get_uow)) -> views.CatalogView:
        return views.build_catalog(uow, views.current_snapshot(uow))

    @app.get("/api/changes")
    def changes(
        uow: UnitOfWork = Depends(get_uow),
        w_perf: float | None = None,
        blended: bool = False,
        longevity: bool = LONGEVITY_BONUS_ENABLED,
        trust_penalty: bool = TRUST_PENALTY_ENABLED,
    ) -> views.ChangesView:
        params = _params(
            w_perf=w_perf, blended=blended, longevity=longevity, trust_penalty=trust_penalty,
            mall_only=False, keyword=DEFAULT_KEYWORD,
            price_min=DEFAULT_PRICE_MIN, price_max=DEFAULT_PRICE_MAX,
            source_kind=source_factory().kind,
        )
        return views.build_changes(uow, views.current_snapshot(uow), params)

    @app.get("/api/settings")
    def settings(
        uow: UnitOfWork = Depends(get_uow),
        w_perf: float | None = None,
        mall_only: bool = False,
        blended: bool = False,
        longevity: bool = LONGEVITY_BONUS_ENABLED,
        trust_penalty: bool = TRUST_PENALTY_ENABLED,
    ) -> views.SettingsView:
        params = _params(
            w_perf=w_perf, blended=blended, longevity=longevity, trust_penalty=trust_penalty,
            mall_only=mall_only, keyword=DEFAULT_KEYWORD,
            price_min=DEFAULT_PRICE_MIN, price_max=DEFAULT_PRICE_MAX,
            source_kind=source_factory().kind,
        )
        return views.build_settings(uow, views.current_snapshot(uow), params)

    @app.post("/api/run")
    def run(body: RunRequest | None = None, uow: UnitOfWork = Depends(get_uow)) -> RunResult:
        req = body or RunRequest()
        return run_daily(
            source=source_factory(), uow=uow, snapshot_date=clock(),
            keyword=req.keyword, price_min=req.price_min, price_max=req.price_max,
            mall_only=req.mall_only, weights=_weights(req.w_perf),
        )

    @app.post("/api/catalog/map")
    def catalog_map(body: MapRequest, uow: UnitOfWork = Depends(get_uow)) -> dict[str, str]:
        uow.aliases.remember(alias_key(body.title), body.device_id)
        return {"ok": "true", "key": alias_key(body.title), "device_id": body.device_id}

    @app.post("/api/notify")
    def notify(uow: UnitOfWork = Depends(get_uow)) -> dict[str, str]:
        """Push the current snapshot's digest through the configured channel — the manual
        counterpart to the scheduled daily push (SPEC §11.2). Off by default: with no channel
        configured it reports rather than erroring; nothing is sent when the frontier is empty."""
        notifier = notifier_factory(uow)
        if notifier is None:
            return {"ok": "false", "reason": "no notifier configured"}
        digest = notify_daily(
            uow, notifier, snapshot_date=views.current_snapshot(uow),
            source_kind=source_factory().kind,
        )
        return {"ok": "true", "sent": "true" if digest is not None else "false"}

    @app.post("/api/settings/notify")
    def set_notify(body: NotifyConfigRequest, uow: UnitOfWork = Depends(get_uow)) -> dict:
        """Persist the push channel from the UI (SPEC §11.2). ``kind=off`` clears it; ``telegram``
        is validated (needs both creds) via ``build_notifier`` before saving. A blank token reuses
        the stored one (the token is never echoed back, so the form can't resend it). Returns the
        masked channel state."""
        kind = body.kind.strip().lower()
        if kind == "off":
            clear_notify_config(uow)
            return notify_masked(None)
        existing = resolve_notify_config(uow, os.environ)
        token = body.token or (existing.token if existing else None)
        chat_id = body.chat_id or (existing.chat_id if existing else None)
        try:
            build_notifier(kind, token=token, chat_id=chat_id)  # validate only (no network)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_notify_config(uow, kind=kind, token=token, chat_id=chat_id)
        return notify_masked(resolve_notify_config(uow, os.environ))

    @app.post("/api/settings/notify/test")
    def test_notify(uow: UnitOfWork = Depends(get_uow)) -> dict[str, str]:
        """Send a fixed test message through the configured channel to confirm the creds work
        live (SPEC §11.2). Reports 'not configured' when off; a send failure is caught + reported
        (never a 500) so a bad token/chat id shows the user the error string."""
        notifier = notifier_factory(uow)
        if notifier is None:
            return {"ok": "false", "reason": "no notifier configured"}
        try:
            notifier.send("Ampere connected ✓ — test push from your Ampere settings.")
        except Exception as exc:  # noqa: BLE001 (surface any transport error to the user)
            return {"ok": "false", "error": str(exc)}
        return {"ok": "true"}

    @app.get("/api/report", response_class=HTMLResponse)
    def report(uow: UnitOfWork = Depends(get_uow)) -> HTMLResponse:
        """Serve the self-contained shareable HTML snapshot of the current frontier (SPEC §11.2)."""
        html = render_report(
            build_report(uow, views.current_snapshot(uow), source_kind=source_factory().kind)
        )
        return HTMLResponse(html)

    # Static SPA shell last, mounted at root so /api/* wins.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


def _default_uow_factory() -> UnitOfWork:
    conn = db.connect(check_same_thread=False)
    db.create_schema(conn)
    return SqliteUnitOfWork(conn)


def _bootstrap_default_db() -> None:
    """Seed the demo DB on first launch, then catch up today's run on every launch (SC8).

    Dev convenience so ``uvicorn ampere.web.api:app`` shows data immediately (M4): a fresh DB gets
    the demo catalog + its first fixture snapshots. On a DB that has already run, the launch-time
    catch-up (SPEC §8a) runs today's snapshot iff no successful run exists for today — so a laptop
    that was asleep at the scheduled time still gets exactly one run for the date via startup
    (idempotent per ``snapshot_date`` — never zero, never a duplicate).
    """
    uow = _default_uow_factory()
    try:
        if uow.runs.last_successful() is None:
            bootstrap(uow, today=date.today())  # first launch: seed demo catalog + snapshots
        else:
            catch_up(uow, FixtureSource(), today=date.today())  # subsequent launches: SC8 catch-up
    finally:
        uow.close()  # type: ignore[attr-defined]  # type: ignore[attr-defined]


app = create_app(uow_factory=_default_uow_factory, on_startup=_bootstrap_default_db)
