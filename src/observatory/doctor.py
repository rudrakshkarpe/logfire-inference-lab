from pathlib import Path

import httpx

from observatory.settings import Settings


def diagnose(settings: Settings) -> list[dict]:
    parent = settings.observatory_db.parent
    parent.mkdir(parents=True, exist_ok=True)
    probe = parent / ".write-check"
    try:
        probe.write_text("ok")
        probe.unlink()
        storage = True
    except OSError:
        storage = False
    configured = bool(settings.logfire_token and settings.logfire_token.get_secret_value())
    configured = configured or (Path(".logfire") / "logfire_credentials.json").exists()
    checks = [{"check": "local storage", "ok": storage,
               "detail": "SQLite directory is writable" if storage else "Choose a writable database path"},
              {"check": "telemetry export", "ok": not settings.observatory_export or configured,
               "detail": "Disabled; local exploration works" if not settings.observatory_export
               else "Credentials found; ingestion is not yet verified" if configured
               else "Run logfire auth and logfire projects use, or set LOGFIRE_TOKEN"}]
    try:
        response = httpx.get(f"http://{settings.observatory_host}:{settings.observatory_port}/api/health",
                             timeout=2)
        ready = response.status_code == 200
    except httpx.HTTPError:
        ready = False
    checks.append({"check": "application", "ok": ready,
                   "detail": "Health endpoint responded" if ready else "Start with: uv run observatory serve"})
    return checks
