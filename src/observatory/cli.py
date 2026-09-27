import argparse
import asyncio
import json

from observatory.models import Run, RunSpec, Scenario
from observatory.settings import Settings


def main():
    parser = argparse.ArgumentParser(description="Inference serving + Logfire integration lab")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the instrumented inference serving endpoint")
    serve.add_argument("--host", default=None)
    sub.add_parser("doctor", help="Check local configuration without printing secrets")
    run = sub.add_parser("run", help="Exercise the serving endpoint through the OpenAI SDK")
    run.add_argument("--scenario", choices=[s.value for s in Scenario], default="baseline")
    run.add_argument("--requests", type=int, default=24)
    run.add_argument("--concurrency", type=int, default=8)
    run.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    settings = Settings()
    if args.command == "serve":
        import uvicorn

        from observatory.serving import create_serving_app

        uvicorn.run(
            create_serving_app(settings),
            host=args.host or settings.observatory_host,
            port=settings.observatory_port,
        )
    elif args.command == "doctor":
        from observatory.doctor import diagnose

        checks = diagnose(settings)
        print(json.dumps(checks, indent=2))
        raise SystemExit(0 if all(c["ok"] for c in checks) else 1)
    else:
        from observatory.analysis import serialize
        from observatory.pipeline import exercise
        from observatory.store import Store
        from observatory.telemetry import configure, flush

        spec = RunSpec(
            scenario=args.scenario,
            requests=args.requests,
            concurrency=args.concurrency,
            seed=args.seed,
        )
        configure(settings, service_name="inference-application")
        workload = Run(spec=spec)
        asyncio.run(
            exercise(workload, Store(settings.observatory_db), settings.observatory_serving_url)
        )
        flushed = flush()
        print(json.dumps({"run": serialize(workload), "export_flush_completed": flushed}, indent=2))
        # Only the interrupted-stream scenario should produce request errors.
        expected = spec.requests // 4 if spec.scenario == Scenario.interrupted_stream else 0
        errors = sum(item.status != "ok" for item in workload.results)
        raise SystemExit(0 if workload.status == "completed" and errors == expected else 1)


if __name__ == "__main__":
    main()
