"""Quickstart: the simplest FacadeDriver program.

Runs entirely on the MockBackend - no API keys, no network. Shows
config-from-dict, generate(), and reading the Response fields.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from facadedriver import Config, FacadeDriver, MockBackend
from facadedriver.telemetry import NullSink


def main() -> None:
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet", "gemini-1.5-flash"],
            }
        }
    })
    driver = FacadeDriver(cfg, backend=MockBackend(), telemetry_sink=NullSink())

    resp = driver.generate(
        "summarize",
        [{"role": "user", "content": "FacadeDriver is a model-agnostic orchestration layer."}],
    )

    print("content      :", resp.content)
    print("model        :", resp.model)
    print("provider     :", resp.provider)
    print("route        :", resp.route)
    print("latency_ms   :", round(resp.latency_ms, 2))
    print("tokens       :", resp.input_tokens, "in ->", resp.output_tokens, "out")
    print("fallback_used:", resp.fallback_used)
    print("request_id   :", resp.request_id)


if __name__ == "__main__":
    main()
