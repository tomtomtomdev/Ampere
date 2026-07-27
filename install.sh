#!/usr/bin/env bash
#
# Ampere — one-step install.
#
#   ./install.sh                 # venv + deps + verify + seed a local DB from the offline fixture
#   ./install.sh --schedule      # ...and install the OS scheduler (launchd on macOS, cron on Linux)
#   ./install.sh --dry-run       # print the plan, change nothing
#
# Safe to re-run: an existing venv is reused, the seeding run is idempotent per snapshot_date
# (SC6), and the scheduler install is additive — it never replaces an existing crontab.
#
# The 06:00 schedule + launch-time catch-up live in the shipped templates under deploy/ (asserted
# by tests/test_deploy_assets.py). This script renders those; it never inlines its own copy.

set -euo pipefail

_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
_VENV="$_ROOT/.venv"
_PLIST_TEMPLATE="deploy/launchd/id.co.tuntun.ampere.run-daily.plist"
_CRON_TEMPLATE="deploy/cron/ampere.crontab"
_LABEL="id.co.tuntun.ampere.run-daily"

AMPERE_HOME="${AMPERE_HOME:-$HOME/ampere}"
DO_SCHEDULE=0
DO_TEST=1
DO_SEED=1
DRY_RUN=0

usage() {
    cat <<'EOF'
Ampere — one-step install.

Usage: ./install.sh [options]

Options:
  --schedule       Also install the OS scheduler for the automatic daily fetch
                   (launchd LaunchAgent on macOS, crontab entries on Linux).
  --home DIR       Data home for the DB, cache and logs. Default: $HOME/ampere
  --no-test        Skip the pytest + ruff verification step.
  --no-seed        Skip the first offline run that creates and seeds the local DB.
  --dry-run        Print the plan and exit without changing anything.
  -h, --help       Show this help.

What a default run does:
  1. Find Python >= 3.12 (prefers uv when installed).
  2. Create .venv and install the project editable with the [dev,web] extras.
  3. Verify: pytest + ruff.
  4. Create the data home and seed a local DB with one offline run.
  5. Print how to start the UI.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --schedule) DO_SCHEDULE=1; shift ;;
        --no-test)  DO_TEST=0; shift ;;
        --no-seed)  DO_SEED=0; shift ;;
        --dry-run)  DRY_RUN=1; shift ;;
        --home)
            [[ $# -ge 2 ]] || { echo "install.sh: --home needs a directory" >&2; exit 2; }
            AMPERE_HOME="$2"; shift 2 ;;
        --home=*)   AMPERE_HOME="${1#*=}"; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          echo "install.sh: unknown option '$1' (try --help)" >&2; exit 2 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
find_python() {
    local candidate
    for candidate in python3.14 python3.13 python3.12 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
            >/dev/null 2>&1; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

HAVE_UV=0
command -v uv >/dev/null 2>&1 && HAVE_UV=1

PYTHON=""
if ! PYTHON="$(find_python)"; then
    if (( HAVE_UV )); then
        PYTHON="(uv-managed)"   # uv will provision an interpreter for us
    elif (( DRY_RUN )); then
        PYTHON="(none found)"
    else
        echo "install.sh: no Python >= 3.12 found, and uv is not installed." >&2
        echo "            Install uv (https://docs.astral.sh/uv/) or a Python 3.12+ and re-run." >&2
        exit 1
    fi
fi

case "$(uname -s)" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      PLATFORM="other" ;;
esac

# ---------------------------------------------------------------------------
# Dry run: print the plan and stop before touching anything.
# ---------------------------------------------------------------------------
if (( DRY_RUN )); then
    echo "Ampere install plan (dry run — nothing will be changed)"
    info "repo:        $_ROOT"
    info "python:      $PYTHON"
    info "installer:   $( ((HAVE_UV)) && echo 'uv' || echo 'python -m venv + pip')"
    info "venv:        $_VENV"
    info "data home:   $AMPERE_HOME"
    info "platform:    $PLATFORM"

    step "1. Create the virtualenv at $_VENV"
    step "2. Install the project editable with the [dev,web] extras"
    _n=3
    if (( DO_TEST )); then
        step "$_n. Verify: pytest and ruff check ampere tests"
        _n=$((_n + 1))
    fi
    step "$_n. Create $AMPERE_HOME/data (plus cache/ and logs/)"
    _n=$((_n + 1))
    if (( DO_SEED )); then
        step "$_n. Seed the local DB with one offline run:"
        info "AMPERE_SOURCE=fixture AMPERE_DB=$AMPERE_HOME/data/ampere.db ampere-run-daily"
        _n=$((_n + 1))
    fi
    if (( DO_SCHEDULE )); then
        case "$PLATFORM" in
            macos)
                step "$_n. Install the launchd agent from $_PLIST_TEMPLATE"
                info "-> ~/Library/LaunchAgents/$_LABEL.plist, then launchctl load" ;;
            linux)
                step "$_n. Append the entries from $_CRON_TEMPLATE to the existing crontab"
                info "(read with 'crontab -l' first — existing jobs are preserved)" ;;
            *)
                step "$_n. No scheduler for this platform — skipped" ;;
        esac
    fi
    echo
    exit 0
fi

# ---------------------------------------------------------------------------
# 1 + 2. Virtualenv and dependencies
# ---------------------------------------------------------------------------
step "Creating the virtualenv at $_VENV"
if [[ -x "$_VENV/bin/python" ]]; then
    info "already present — reusing it"
elif (( HAVE_UV )); then
    uv venv "$_VENV"
else
    "$PYTHON" -m venv "$_VENV"
fi

step "Installing ampere (editable) with the [dev,web] extras"
if (( HAVE_UV )); then
    uv pip install --python "$_VENV" -e "$_ROOT[dev,web]"
else
    "$_VENV/bin/python" -m pip install --quiet --upgrade pip
    "$_VENV/bin/python" -m pip install -e "$_ROOT[dev,web]"
fi

# ---------------------------------------------------------------------------
# 3. Verify
# ---------------------------------------------------------------------------
if (( DO_TEST )); then
    step "Verifying the install (pytest + ruff)"
    ( cd "$_ROOT" && "$_VENV/bin/pytest" )
    ( cd "$_ROOT" && "$_VENV/bin/ruff" check ampere tests )
fi

# ---------------------------------------------------------------------------
# 4. Data home + first (offline) run
# ---------------------------------------------------------------------------
step "Creating the data home at $AMPERE_HOME"
mkdir -p "$AMPERE_HOME/data/logs" "$AMPERE_HOME/data/cache"

if (( DO_SEED )); then
    # The fixture source deliberately: installing must never hit the live marketplace. The first
    # run against a fresh DB also seeds the real reference catalog from data/seed/.
    step "Seeding the local DB with one offline run"
    ( cd "$_ROOT" && AMPERE_SOURCE=fixture AMPERE_DB="$AMPERE_HOME/data/ampere.db" \
        "$_VENV/bin/ampere-run-daily" )
fi

# ---------------------------------------------------------------------------
# 5. Optional: the OS scheduler (renders the shipped deploy/ templates)
# ---------------------------------------------------------------------------
install_launchd() {
    if ! command -v launchctl >/dev/null 2>&1; then
        info "launchctl not found — skipping. Install by hand: deploy/README.md"
        return 0
    fi
    local dest="$HOME/Library/LaunchAgents/$_LABEL.plist"
    mkdir -p "$HOME/Library/LaunchAgents"
    sed -e "s#__VENV__#$_VENV#g" -e "s#__AMPERE_HOME__#$AMPERE_HOME#g" \
        "$_ROOT/$_PLIST_TEMPLATE" > "$dest"
    launchctl unload "$dest" >/dev/null 2>&1 || true   # idempotent re-install
    launchctl load "$dest"
    info "loaded $dest"
    info "the agent's RunAtLoad just fired a catch-up run"
    info "the scheduled job uses the live affiliate source — edit $dest to change it"
}

install_cron() {
    if ! command -v crontab >/dev/null 2>&1; then
        info "crontab not found — skipping. Install by hand: deploy/README.md"
        return 0
    fi
    local existing
    existing="$(mktemp)"
    # Read the current crontab and APPEND to it. Never 'crontab <file>' from the template alone:
    # that would replace every unrelated job the user has.
    crontab -l 2>/dev/null > "$existing" || true
    if grep -q 'ampere-run-daily' "$existing"; then
        info "an ampere entry is already in the crontab — leaving it untouched"
        rm -f "$existing"
        return 0
    fi
    sed -e "s#/opt/ampere/.venv#$_VENV#g" -e "s#\$HOME/ampere#$AMPERE_HOME#g" \
        "$_ROOT/$_CRON_TEMPLATE" >> "$existing"
    crontab "$existing"
    rm -f "$existing"
    info "appended the daily + @reboot entries (existing jobs preserved)"
    info "the scheduled job uses the live affiliate source — 'crontab -e' to change it"
}

if (( DO_SCHEDULE )); then
    step "Installing the OS scheduler for the automatic daily fetch"
    case "$PLATFORM" in
        macos) install_launchd ;;
        linux) install_cron ;;
        *)     info "unsupported platform '$(uname -s)' — see deploy/README.md" ;;
    esac
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
cat <<EOF

==> Ampere is installed.

    Start the web UI:
        AMPERE_DB=$AMPERE_HOME/data/ampere.db $_VENV/bin/uvicorn ampere.web.api:app --reload
        then open http://127.0.0.1:8000

    Run the daily job by hand:
        AMPERE_DB=$AMPERE_HOME/data/ampere.db $_VENV/bin/ampere-run-daily
EOF
if (( ! DO_SCHEDULE )); then
    cat <<'EOF'

    Automate the daily fetch:
        ./install.sh --schedule        (or see deploy/README.md)
EOF
fi
echo
