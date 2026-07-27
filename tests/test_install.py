"""The one-step installer (``install.sh``).

``install.sh`` is a shipped deliverable like the deploy assets (see ``test_deploy_assets.py``): it
is what turns a fresh clone into a working install. We cannot run a real install in CI, so the
script carries a ``--dry-run`` mode that prints its plan and mutates nothing — that is the seam
these tests drive. We assert the script parses, that dry-run really is inert, that the install
never reaches the network, and that scheduler installation reuses the *shipped* templates (so the
schedule asserted in ``test_deploy_assets.py`` stays the single source of truth) and appends to the
user's crontab rather than replacing it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_INSTALL = _ROOT / "install.sh"


def _run(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_INSTALL), *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        **kw,
    )


class TestScriptItself:
    def test_exists(self):
        assert _INSTALL.is_file()

    def test_is_executable(self):
        assert os.access(_INSTALL, os.X_OK), "install.sh must be chmod +x to be a one-step install"

    def test_is_valid_bash(self):
        # `bash -n` = parse without executing. A syntax error here would fail every user's install.
        assert subprocess.run(["bash", "-n", str(_INSTALL)], capture_output=True).returncode == 0

    def test_fails_fast_on_errors(self):
        # Without `set -e`, a failed step would be reported as a successful install.
        assert "set -euo pipefail" in _INSTALL.read_text(encoding="utf-8")


class TestHelp:
    def test_help_exits_zero(self):
        assert _run("--help").returncode == 0

    def test_help_documents_the_flags(self):
        out = _run("--help").stdout
        for flag in ("--schedule", "--dry-run", "--no-test", "--no-seed", "--home"):
            assert flag in out, f"{flag} undocumented"

    def test_rejects_an_unknown_flag(self):
        assert _run("--wat").returncode != 0


class TestDryRun:
    def test_exits_zero(self):
        assert _run("--dry-run").returncode == 0

    def test_mutates_nothing(self, tmp_path):
        # The strongest inertness check we can make: point --home at a path that does not exist
        # and assert the dry run did not bring it into being.
        home = tmp_path / "ampere-home"
        assert _run("--dry-run", "--home", str(home)).returncode == 0
        assert not home.exists()

    def test_plan_covers_the_editable_dev_web_install(self):
        out = _run("--dry-run").stdout
        assert "[dev,web]" in out

    def test_plan_names_the_venv_and_the_data_home(self, tmp_path):
        home = tmp_path / "ampere-home"
        out = _run("--dry-run", "--home", str(home)).stdout
        assert ".venv" in out
        assert str(home) in out

    def test_no_test_drops_the_verify_step(self):
        assert "pytest" in _run("--dry-run").stdout
        assert "pytest" not in _run("--dry-run", "--no-test").stdout

    def test_no_seed_drops_the_first_run(self):
        assert "ampere-run-daily" in _run("--dry-run").stdout
        assert "ampere-run-daily" not in _run("--dry-run", "--no-seed").stdout


class TestOfflineByDefault:
    def test_the_seeding_run_uses_the_fixture_source(self):
        # Invariant: installing must never hit the fragile/ToS-bound live source. The first run is
        # the offline fixture source; the live source is only ever the *scheduled* job's default.
        out = _run("--dry-run").stdout
        assert "AMPERE_SOURCE=fixture" in out


class TestSchedulerInstall:
    def test_dry_run_schedule_exits_zero(self):
        assert _run("--dry-run", "--schedule").returncode == 0

    def test_reuses_a_shipped_template(self):
        # The schedule (06:00 + catch-up) is asserted in test_deploy_assets.py against the shipped
        # templates. The installer must render *those*, never inline a second copy that can drift.
        out = _run("--dry-run", "--schedule").stdout
        assert "deploy/launchd/id.co.tuntun.ampere.run-daily.plist" in out or (
            "deploy/cron/ampere.crontab" in out
        )

    def test_does_not_inline_its_own_schedule(self):
        text = _INSTALL.read_text(encoding="utf-8")
        assert "StartCalendarInterval" not in text, "schedule belongs in the shipped plist"

    def test_crontab_install_is_additive(self):
        # `crontab <file>` REPLACES the user's whole crontab. The installer must read the existing
        # one and append, so installing Ampere cannot silently destroy unrelated cron jobs.
        text = _INSTALL.read_text(encoding="utf-8")
        assert "crontab -l" in text, "must read the existing crontab before writing"

    def test_no_destructive_crontab_replace(self):
        text = _INSTALL.read_text(encoding="utf-8")
        assert "crontab deploy/cron" not in text
        assert 'crontab "$_CRONTAB"' not in text

    def test_missing_scheduler_binary_is_reported_not_crashed(self):
        # --schedule runs last, after a *successful* install. If crontab/launchctl is absent,
        # `set -e` would abort with an opaque 127 and imply the whole install failed. Guard both.
        text = _INSTALL.read_text(encoding="utf-8")
        assert "command -v crontab" in text
        assert "command -v launchctl" in text


class TestDocsStayInSync:
    def test_readme_points_at_the_installer(self):
        assert "install.sh" in (_ROOT / "README.md").read_text(encoding="utf-8")

    def test_deploy_readme_points_at_the_installer(self):
        text = (_ROOT / "deploy" / "README.md").read_text(encoding="utf-8")
        assert "install.sh" in text
