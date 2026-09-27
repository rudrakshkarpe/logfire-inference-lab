import asyncio
from collections.abc import Callable

from observatory.engine import execute_request
from observatory.models import Run
from observatory.scenarios import PROFILES
from observatory.store import Store
from observatory.telemetry import span, trace_id


class Runner:
    def __init__(self, store: Store, max_runs: int = 2):
        self.store = store
        self.max_runs = max_runs
        self.tasks: dict[str, asyncio.Task] = {}

    def start(self, run: Run):
        if len(self.tasks) >= self.max_runs:
            raise RuntimeError("Another workload is active. Wait for a slot or cancel a run.")
        self.store.save(run)
        task = asyncio.create_task(self.execute(run))
        self.tasks[run.id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run.id, None))

    async def execute(self, run: Run, on_result: Callable | None = None):
        run.status = "running"
        self.store.save(run)
        slots = asyncio.Semaphore(PROFILES[run.spec.scenario].slots)
        clients = asyncio.Semaphore(run.spec.concurrency)
        tasks = []

        async def one(index):
            async with clients:
                result = await execute_request(run, index, slots)
                run.results.append(result)
                self.store.save(run)
                if on_result:
                    on_result(run, result)

        try:
            with span("workload.run", **{"observatory.run_id": run.id,
                      "observatory.scenario": run.spec.scenario.value,
                      "observatory.requests": run.spec.requests,
                      "observatory.concurrency": run.spec.concurrency}) as run_span:
                run.trace_id = trace_id()
                self.store.save(run)
                tasks = [asyncio.create_task(one(index)) for index in range(run.spec.requests)]
                await asyncio.gather(*tasks)
                run_span.set_attribute("observatory.errors", sum(r.status != "ok" for r in run.results))
                run.status = "completed"
        except asyncio.CancelledError:
            run.status = "cancelled"
        except Exception as exc:
            run.status = "failed"
            run.failure = type(exc).__name__
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.store.save(run)

    async def cancel(self, run_id: str) -> bool:
        task = self.tasks.get(run_id)
        if task is None:
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return True

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
