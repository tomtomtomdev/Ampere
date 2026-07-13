"""FastAPI app — thin transport over use-cases/repos (PLAN M4).

M0: serves the static shell + design system so the UI foundation runs; the data endpoints are
declared but return 501 until M4 wires them to the repos. Business math never lives here.

Run:  uvicorn ampere.web.api:app --reload   (needs the ``web`` extra installed)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).with_name("static")

app = FastAPI(title="Ampere", version="0.1.0")


def _not_yet(screen: str) -> dict:
    # Declared surface for the five screens; implemented in M4 against the repos.
    raise HTTPException(status_code=501, detail=f"{screen}: implemented in M4")


@app.get("/api/dashboard")
def dashboard() -> dict:
    return _not_yet("dashboard")


@app.get("/api/listings")
def listings() -> dict:
    return _not_yet("listings")


@app.get("/api/catalog")
def catalog() -> dict:
    return _not_yet("catalog")


@app.get("/api/changes")
def changes() -> dict:
    return _not_yet("changes")


@app.get("/api/settings")
def settings() -> dict:
    return _not_yet("settings")


# Static SPA shell last, mounted at root so /api/* wins.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
