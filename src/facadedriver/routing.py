"""Router - resolves a route name to an ordered model chain.

A route is a logical name (e.g. "summarize", "code-review") that maps
to a primary model and an ordered fallback list. The router also
supports runtime swaps: change the primary model for a route without
reloading config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from facadedriver.config import RouteConfig


@dataclass
class RouteState:
    name: str
    config: RouteConfig
    overrides: dict[str, str] = field(default_factory=dict)

    def chain(self) -> list[str]:
        """Return the effective [primary, *fallback] model chain."""
        primary = self.overrides.get("primary", self.config.primary)
        fallback = [
            self.overrides.get(f, f) for f in self.config.fallback
        ]
        return [primary, *fallback]


class Router:
    """Resolves routes to model chains with runtime swap support."""

    def __init__(self, routes: dict[str, RouteConfig]) -> None:
        self._states: dict[str, RouteState] = {
            name: RouteState(name=name, config=cfg) for name, cfg in routes.items()
        }
        self._lock = RLock()

    def has(self, route: str) -> bool:
        return route in self._states

    def chain(self, route: str) -> list[str]:
        with self._lock:
            if route not in self._states:
                from facadedriver.types import RouteNotFoundError

                raise RouteNotFoundError(route)
            return self._states[route].chain()

    def config(self, route: str) -> RouteConfig:
        with self._lock:
            return self._states[route].config

    def swap(self, route: str, model: str) -> None:
        """Runtime swap: set a new primary model for a route."""
        with self._lock:
            if route not in self._states:
                from facadedriver.types import RouteNotFoundError

                raise RouteNotFoundError(route)
            self._states[route].overrides["primary"] = model

    def swap_fallback(self, route: str, index: int, model: str) -> None:
        with self._lock:
            if route not in self._states:
                from facadedriver.types import RouteNotFoundError

                raise RouteNotFoundError(route)
            self._states[route].overrides[f"__fb_{index}"] = model

    def reset(self, route: str) -> None:
        with self._lock:
            if route in self._states:
                self._states[route].overrides.clear()

    def routes(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())
