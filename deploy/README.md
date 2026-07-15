# Ampere — deploy assets (automatic daily scheduling)

The daily fetch runs **automatically once per day; the UI's "Run now" is only a fallback** (SPEC
§8a, SC8). Both the OS scheduler and the button call the same headless entrypoint —
`ampere-run-daily` (`ampere.application.run_daily:main`) — so there is exactly one code path.

Runs are **idempotent per `snapshot_date`** (SC6), so triggering twice in a day is harmless: the
second run replaces rather than duplicates. That is what makes catch-up safe.

## Configuration (environment variables)

`ampere-run-daily` reads its config from the environment (`RunConfig.from_env`):

| Var | Default | Meaning |
|-----|---------|---------|
| `AMPERE_SOURCE` | `fixture` | `affiliate` (preferred, ToS-safe) · `internal` (best-effort) · `fixture` (offline) |
| `AMPERE_KEYWORD` | `android` | search keyword |
| `AMPERE_PRICE_MIN` / `AMPERE_PRICE_MAX` | `1000000` / `2000000` | price band, whole IDR |
| `AMPERE_MALL_ONLY` | off | `1`/`true` to restrict to Shopee Mall |
| `AMPERE_DB` | adapter default (`data/ampere.db`) | SQLite path |
| `AMPERE_CACHE_DIR` | none | on-disk page cache for live sources ("cache hard", §6) |
| `AMPERE_NOTIFY` | none (off) | daily push channel: `telegram` · `stdout` (dry-run). Unset ⇒ no push. |
| `AMPERE_TELEGRAM_TOKEN` | none | Telegram Bot API token (from @BotFather) — required for `telegram` |
| `AMPERE_TELEGRAM_CHAT_ID` | none | target chat/channel id — required for `telegram` |

### Daily push (SPEC §11.2)

After each successful run, if `AMPERE_NOTIFY` names a channel, the run pushes a digest — the
best-value phone in the band plus the Pareto frontier (with outbound/affiliate links inline). It is
**off by default** (unset ⇒ nothing sent), and a push failure never fails the run (the snapshot is
already persisted). Nothing is sent when the frontier is empty (e.g. before the first
`refresh_catalog` fills the ID-band SoC benchmarks). Telegram setup: create a bot via @BotFather,
message it (or add it to a group), resolve the numeric chat id, then:

```sh
export AMPERE_NOTIFY=telegram AMPERE_TELEGRAM_TOKEN=123456:ABC... AMPERE_TELEGRAM_CHAT_ID=42
ampere-run-daily                       # or set these in the launchd plist / crontab env
AMPERE_NOTIFY=stdout ampere-run-daily  # dry-run: print exactly what the channel would receive
```

On the **first** run against a fresh DB, the real reference catalog is seeded from `data/seed/`
(`chipsets_seed.csv` + `devices_seed.csv`). Benchmarks/battery for the ID-band SoCs are filled by
the monthly `refresh_catalog`, not the daily job (never fabricated — invariant #4).

## macOS — launchd LaunchAgent (primary)

`launchd/id.co.tuntun.ampere.run-daily.plist` runs at **06:00 daily** (`StartCalendarInterval`)
and **at load/login** (`RunAtLoad`) — the latter is the launch-time catch-up.

```sh
# 1. Fill in the placeholders (venv path + a writable data home):
sed -e "s#__VENV__#$PWD/.venv#g" -e "s#__AMPERE_HOME__#$HOME/ampere#g" \
    deploy/launchd/id.co.tuntun.ampere.run-daily.plist \
    > ~/Library/LaunchAgents/id.co.tuntun.ampere.run-daily.plist

# 2. Create the data/log dirs it points at:
mkdir -p ~/ampere/data/logs ~/ampere/data/cache

# 3. Load it (starts scheduling; RunAtLoad fires one catch-up now):
launchctl load ~/Library/LaunchAgents/id.co.tuntun.ampere.run-daily.plist

# Inspect / stop:
launchctl list | grep ampere
launchctl unload ~/Library/LaunchAgents/id.co.tuntun.ampere.run-daily.plist
```

## Linux — cron

`cron/ampere.crontab` has the 06:00 daily line plus an `@reboot` catch-up line. Edit the paths,
then install:

```sh
crontab deploy/cron/ampere.crontab      # replaces the current crontab; or paste the lines in
crontab -l                              # verify
```

## Catch-up, three ways (SC8)

Any one of these guarantees "exactly one run per day even on an intermittently-on machine":

- **launchd `RunAtLoad`** / **cron `@reboot`** — a run on login/boot.
- **web app startup** — `create_app(..., on_startup=...)` calls `catch_up` on launch; the default
  app wires this, so starting `uvicorn ampere.web.api:app` also catches up.
- **the guard itself** — `catch_up` skips if today already succeeded, so none of the above ever
  double-runs (and never re-hits the fragile Shopee source in a day).
