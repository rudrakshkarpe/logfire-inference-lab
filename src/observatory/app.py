import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from observatory.analysis import serialize
from observatory.metrics import Metrics
from observatory.models import Run, RunSpec
from observatory.runner import Runner
from observatory.scenarios import catalogue
from observatory.settings import Settings
from observatory.store import Store
from observatory.telemetry import configure, flush

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        configure(settings)
        app.state.store = Store(settings.observatory_db)
        metrics = Metrics()
        app.state.runner = Runner(app.state.store, settings.observatory_max_runs, metrics.record)
        yield
        await app.state.runner.close()
        await asyncio.to_thread(flush)

    app = FastAPI(title="Inference Observatory", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "source": "synthetic",
            "export_enabled": settings.observatory_export,
            "project_url": settings.observatory_project_url,
            "active_runs": len(app.state.runner.tasks),
        }

    @app.get("/api/scenarios")
    def scenarios():
        return catalogue()

    @app.post("/api/runs", status_code=202)
    async def start(spec: RunSpec):
        run = Run(spec=spec)
        try:
            app.state.runner.start(run)
        except RuntimeError as exc:
            raise HTTPException(429, str(exc)) from exc
        return serialize(run, detail=True)

    @app.get("/api/runs")
    def runs():
        return [serialize(run) for run in app.state.store.list()]

    @app.get("/api/runs/{run_id}")
    def detail(run_id: str):
        run = app.state.store.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return serialize(run, detail=True)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        if not app.state.store.get(run_id):
            raise HTTPException(404, "Run not found")
        return {"cancelled": await app.state.runner.cancel(run_id)}

    from observatory.streaming import add_streaming_routes

    add_streaming_routes(app)

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(STATIC / "index.html")

    return app
