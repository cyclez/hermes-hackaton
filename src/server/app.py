from __future__ import annotations

from src.server.config import Settings
from src.server.game_engine import create_initial_state
from src.server.models import to_plain

try:
    from fastapi import FastAPI
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only before dependency install
    raise RuntimeError("FastAPI is not installed. Install project dependencies before running the API.") from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    app = FastAPI(title="Hermes Hackaton OptimiCity", version="0.1.0")
    state = create_initial_state(
        citizen_count=settings.citizen_count,
        season_seconds=settings.season_seconds,
    )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "llm_provider": settings.llm_provider,
            "citizen_count": settings.citizen_count,
            "database_configured": bool(settings.database_url),
        }

    @app.get("/api/state")
    def get_state() -> dict[str, object]:
        return to_plain(state)

    @app.get("/api/public-events")
    def public_events() -> list[dict[str, object]]:
        return []

    return app


app = create_app()
