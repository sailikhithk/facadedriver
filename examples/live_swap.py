"""Live-swap demo: change a route's primary model at runtime.

This is the headline demo for the AI Tinkerers Houston talk. It shows
that you can swap the model backing a route without restarting the
process or touching config files - all while serving live traffic.

Uses MockBackend so it runs with no API keys.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from facadedriver import Config, FacadeDriver, MockBackend
from facadedriver.telemetry import NullSink


def main() -> None:
    cfg = Config.from_dict({
        "routes": {
            "summarize": {
                "primary": "gpt-4o-mini",
                "fallback": ["claude-3-5-sonnet"],
            }
        }
    })
    driver = FacadeDriver(cfg, backend=MockBackend(), telemetry_sink=NullSink())

    print("=== Before swap ===")
    print("chain:", driver.router.chain("summarize"))
    r1 = driver.generate("summarize", [{"role": "user", "content": "hi"}])
    print("served by:", r1.model)

    print("\n=== Swapping to claude-3-5-sonnet at runtime ===")
    driver.swap("summarize", "claude-3-5-sonnet")
    print("chain:", driver.router.chain("summarize"))

    print("\n=== After swap ===")
    r2 = driver.generate("summarize", [{"role": "user", "content": "hi again"}])
    print("served by:", r2.model)

    print("\n=== Swapping back to gpt-4o-mini ===")
    driver.swap("summarize", "gpt-4o-mini")
    r3 = driver.generate("summarize", [{"role": "user", "content": "one more"}])
    print("served by:", r3.model)

    print("\nKey takeaway: the application code never changed. Only the")
    print("route -> model mapping did, at runtime, with zero downtime.")


if __name__ == "__main__":
    main()
