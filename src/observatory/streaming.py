import asyncio
import csv
import io
import json

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from observatory.analysis import serialize


def add_streaming_routes(app):
    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request):
        if not app.state.store.get(run_id):
            raise HTTPException(404, "Run not found")

        async def stream():
            while not await request.is_disconnected():
                run = app.state.store.get(run_id)
                yield "data: " + json.dumps(serialize(run, detail=True)) + "\n\n"
                if run.status not in {"pending", "running"}:
                    break
                await asyncio.sleep(0.4)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: str):
        run = app.state.store.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return Response(
            run.model_dump_json(indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="run-{run.id}.json"'},
        )

    @app.get("/api/runs/{run_id}/requests.csv")
    def export_csv(run_id: str):
        run = app.state.store.get(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        buffer = io.StringIO()
        from observatory.models import RequestResult

        writer = csv.DictWriter(buffer, fieldnames=["source", *RequestResult.model_fields])
        writer.writeheader()
        for result in sorted(run.results, key=lambda r: r.index):
            writer.writerow({"source": run.source, **result.model_dump()})
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="requests-{run.id}.csv"'},
        )
