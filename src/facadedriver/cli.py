"""FacadeDriver CLI.

Commands:
    facadedriver generate ROUTE MESSAGE    - run a generate call
    facadedriver routes                    - list configured routes
    facadedriver swap ROUTE MODEL          - runtime swap a route's primary
    facadedriver health MODEL              - show circuit breaker health
    facadedriver replay LOGFILE            - replay requests from a telemetry log
    facadedriver serve [--host H] [--port P] - start FastAPI server

Configuration is loaded from facadedriver.yaml in the current directory,
or from --config FILE. Backend defaults to mock for safe local use;
set --backend raw_sdk or --backend litellm to hit real providers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from facadedriver import (
    Config,
    FacadeDriver,
    LiteLLMBackend,
    MockBackend,
    RawSDKBackend,
)
from facadedriver.telemetry import NullSink, StructlogSink


def _build_driver(args: argparse.Namespace) -> FacadeDriver:
    cfg = Config.from_yaml(args.config) if args.config else Config.from_dict({})
    if args.backend == "mock":
        backend: Any = MockBackend()
    elif args.backend == "litellm":
        backend = LiteLLMBackend()
    else:
        backend = RawSDKBackend()
    sink = StructlogSink() if not args.quiet else NullSink()
    return FacadeDriver(cfg, backend=backend, telemetry_sink=sink)


def _cmd_generate(args: argparse.Namespace) -> int:
    driver = _build_driver(args)
    resp = driver.generate(
        args.route, [{"role": "user", "content": args.message}]
    )
    print(resp.content)
    return 0


def _cmd_routes(args: argparse.Namespace) -> int:
    driver = _build_driver(args)
    for r in driver.routes():
        chain = driver.router.chain(r)
        print(f"{r}: {' -> '.join(chain)}")
    return 0


def _cmd_swap(args: argparse.Namespace) -> int:
    driver = _build_driver(args)
    driver.swap(args.route, args.model)
    print(f"swapped {args.route} -> {args.model}")
    print(f"new chain: {' -> '.join(driver.router.chain(args.route))}")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    driver = _build_driver(args)
    h = driver.health(args.model)
    print(json.dumps({
        "model": h.model,
        "circuit_state": h.circuit_state.value,
        "error_rate": round(h.error_rate, 4),
        "requests": h.request_count,
        "errors": h.error_count,
        "last_error": h.last_error,
        "healthy": h.healthy,
    }, indent=2))
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    driver = _build_driver(args)
    path = Path(args.logfile)
    if not path.exists():
        print(f"log file not found: {path}", file=sys.stderr)
        return 1
    n = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        route = event.get("route")
        if not route or not driver.router.has(route):
            continue
        # We don't have the original messages in the log; replay just
        # exercises the route with a placeholder to verify the chain.
        driver.generate(route, [{"role": "user", "content": "replay"}])
        n += 1
    print(f"replayed {n} requests")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from facadedriver.server import build_app, run_app

    driver = _build_driver(args)
    app = build_app(driver)
    run_app(app, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="facadedriver", description=__doc__)
    p.add_argument("--config", help="path to facadedriver.yaml")
    p.add_argument("--backend", choices=["mock", "raw_sdk", "litellm"], default="mock")
    p.add_argument("--quiet", action="store_true", help="suppress telemetry output")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="run a generate call")
    g.add_argument("route")
    g.add_argument("message")
    g.set_defaults(func=_cmd_generate)

    r = sub.add_parser("routes", help="list configured routes")
    r.set_defaults(func=_cmd_routes)

    s = sub.add_parser("swap", help="runtime swap a route's primary model")
    s.add_argument("route")
    s.add_argument("model")
    s.set_defaults(func=_cmd_swap)

    h = sub.add_parser("health", help="show circuit breaker health for a model")
    h.add_argument("model")
    h.set_defaults(func=_cmd_health)

    rp = sub.add_parser("replay", help="replay requests from a telemetry log")
    rp.add_argument("logfile")
    rp.set_defaults(func=_cmd_replay)

    sv = sub.add_parser("serve", help="start FastAPI server")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=_cmd_serve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
