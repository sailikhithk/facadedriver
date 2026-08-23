"""Plugin system for FacadeDriver.

Plugins let users ship custom backends, routers, and telemetry sinks
without forking the core. A plugin is a Python module that exposes one
or more of these entry points:

    def create_backend(config: dict) -> Backend
    def create_router(config: dict) -> Router
    def create_telemetry_sink(config: dict) -> TelemetrySink

Plugins are discovered via Python's importlib.metadata entry points
group "facadedriver.plugins", or loaded explicitly by dotted path.

Usage in config:

    backend:
      type: custom
      module: my_plugin.backends
      class_name: MyBackend
      options: { ... }
"""

from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from typing import Any

from facadedriver.backends import Backend
from facadedriver.routing import Router
from facadedriver.telemetry import TelemetrySink


def load_entry_point_plugins() -> dict[str, Any]:
    """Discover plugins registered via the facadedriver.plugins entry point group."""
    plugins: dict[str, Any] = {}
    try:
        eps = entry_points()
        # Python 3.10+ returns SelectableGroups; 3.12 returns tuple.
        group = eps.select(group="facadedriver.plugins") if hasattr(eps, "select") else eps.get("facadedriver.plugins", [])
    except Exception:  # noqa: BLE001
        return plugins
    for ep in group:
        try:
            plugins[ep.name] = ep.load()
        except Exception:  # noqa: BLE001
            continue
    return plugins


def load_class(dotted: str) -> type:
    """Import and return a class from a 'module.path.ClassName' string."""
    if "." not in dotted:
        raise ValueError(f"dotted path must include module and class: '{dotted}'")
    module_path, class_name = dotted.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def build_backend_from_config(backend_cfg: Any) -> Backend | None:
    """Build a custom backend from a BackendConfig with type='custom'."""
    if backend_cfg.type != "custom" or not backend_cfg.module:
        return None
    cls = load_class(
        f"{backend_cfg.module}.{backend_cfg.class_name}"
        if backend_cfg.class_name
        else backend_cfg.module
    )
    return cls(**backend_cfg.options)


def build_sink_from_spec(spec: str, **kwargs: Any) -> TelemetrySink:
    """Build a telemetry sink from a spec like 'module.path.ClassName'."""
    cls = load_class(spec)
    return cls(**kwargs)
