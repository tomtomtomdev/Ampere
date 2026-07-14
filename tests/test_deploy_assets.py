"""M6 — the shipped OS-scheduler install assets (SPEC §8a, SC8).

These are the deliverable that makes the daily fetch *automatic*: a launchd LaunchAgent (macOS) and
a crontab (Linux), both invoking the same ``ampere-run-daily`` entrypoint. We assert the plist is
valid and encodes the 06:00 schedule + load-time catch-up, and that the crontab targets the same
entrypoint on the same schedule — so a broken schedule fails CI rather than silently never running.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

_DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
_PLIST = _DEPLOY / "launchd" / "id.co.tuntun.ampere.run-daily.plist"
_CRONTAB = _DEPLOY / "cron" / "ampere.crontab"


class TestLaunchdPlist:
    def _load(self) -> dict:
        with open(_PLIST, "rb") as f:
            return plistlib.load(f)

    def test_is_valid_plist(self):
        assert self._load()  # parses without raising

    def test_targets_the_headless_entrypoint(self):
        args = self._load()["ProgramArguments"]
        assert args[-1].endswith("/bin/ampere-run-daily")

    def test_runs_at_0600_daily(self):
        cal = self._load()["StartCalendarInterval"]
        assert cal["Hour"] == 6 and cal["Minute"] == 0

    def test_run_at_load_is_the_catch_up(self):
        # RunAtLoad => a run fires on login/load — the launch-time catch-up (SC8).
        assert self._load()["RunAtLoad"] is True

    def test_source_defaults_to_the_tos_safe_affiliate_feed(self):
        assert self._load()["EnvironmentVariables"]["AMPERE_SOURCE"] == "affiliate"


class TestCrontab:
    def _text(self) -> str:
        return _CRONTAB.read_text(encoding="utf-8")

    def test_targets_the_headless_entrypoint(self):
        assert "ampere-run-daily" in self._text()

    def test_has_the_0600_daily_schedule(self):
        lines = [ln for ln in self._text().splitlines() if ln.strip() and not ln.startswith("#")]
        assert any(ln.startswith("0 6 * * *") for ln in lines)

    def test_has_a_reboot_catch_up_line(self):
        assert "@reboot" in self._text()
