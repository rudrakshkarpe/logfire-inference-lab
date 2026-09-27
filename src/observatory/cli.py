import argparse
import asyncio
import json

from observatory.models import Run, RunSpec, Scenario
from observatory.settings import Settings


def main():
    parser = argparse.ArgumentParser(description="Inference Observatory")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the local investigation console")
    serve.add_argument("--host", default=None)
    sub.add_parser("doctor", help="Check local configuration without printing secrets")
    run = sub.add_parser("run", help="Execute a repeatable workload")
    run.add_argument("--scenario", choices=[s.value for s in Scenario], default="baseline")
    run.add_argument("--requests", type=int, default=24)
    run.add_argument("--concurrency", type=int, default=8)
    run.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "serve":
        import uvicorn
        from observatory.app import create_app
        uvicorn.run(create_app(settings), host=args.host or settings.observatory_host,
                    port=settings.observatory_port)
    elif args.command == "doctor":
        from observatory.doctor import diagnose
        checks = diagnose(settings)
        print(json.dumps(checks, indent=2))
        raise SystemExit(0 if all(c["ok"] for c in checks) else 1)
    else:
        from observatory.analysis import serialize
        from observatory.metrics import Metrics
        from observatory.runner import Runner
        from observatory.store import Store
        from observatory.telemetry import configure, flush
        spec = RunSpec(scenario=args.scenario, requests=args.requests,
                       concurrency=args.concurrency, seed=args.seed)
        configure(settings)
        metrics = Metrics()
        runner = Runner(Store(settings.observatory_db))
        workload = Run(spec=spec)
        asyncio.run(runner.execute(workload, metrics.record))
        flushed = flush()
        print(json.dumps({"run": serialize(workload), "export_flush_completed": flushed}, indent=2))
        raise SystemExit(0 if workload.status == "completed" else 1)


if __name__ == "__main__":
    main()
