"""Canonical runtime bootstrap for Strategy Factory-owned runtimes.

This module keeps ``strategy-factory`` free of static ``akshare_mcp`` imports
while still allowing the current AKShare host to register concrete runtime
providers through a dynamic configurator hook.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
import os
from typing import Any

from ..api.runtime import build_scheduler_runtime_kwargs
from ..infrastructure.runtime_services import (
    get_registered_runtime_provider_names,
    has_runtime_provider,
)


DEFAULT_RUNTIME_PROVIDER_CONFIGURATOR: str | None = None
RUNTIME_PROVIDER_ENTRY_POINT_GROUP = "aiask.strategy_factory.runtime"

DEFAULT_REQUIRED_RUNTIME_PROVIDERS: tuple[str, ...] = (
    "db_provider",
    "factor_scheduler",
    "factor_mining_factory",
    "factor_mining_support_factory",
    "factor_pool_gateway",
    "quant_manager_callable",
    "runtime_warmup_runner",
    "signal_tracker_runtime_factory",
    "signal_tracker_runtime_support_factory",
    "incubation_runtime_factory",
    "incubation_runtime_support_factory",
    "market_event_ingest_support_factory",
    "strategy_promotion_pipeline_service",
    "strategy_runtime_control_service",
    "event_context_builder",
    "strategy_vector_platform_factory",
    "execution_audit_snapshot_builder",
    "closure_review_builder",
    "strategy_llm_provider_loader",
)

RUNTIME_PROVIDER_CONFIGURATOR_ENV_KEY = "AIASK_STRATEGY_FACTORY_RUNTIME_CONFIGURATOR"


def _resolve_configurator_path(configurator_path: str | None = None) -> str | None:
    raw_path = (
        configurator_path
        or os.getenv(RUNTIME_PROVIDER_CONFIGURATOR_ENV_KEY)
        or DEFAULT_RUNTIME_PROVIDER_CONFIGURATOR
    )
    path = str(raw_path).strip() if raw_path else ""
    if path and ":" not in path:
        raise ValueError(
            "runtime configurator must use 'module.submodule:callable_name' format"
        )
    return path


def _load_configurator(configurator_path: str | None = None):
    path = _resolve_configurator_path(configurator_path)
    if path:
        module_name, _, attr_name = path.partition(":")
        module = import_module(module_name)
        configurator = getattr(module, attr_name)
    else:
        discovered = list(entry_points().select(group=RUNTIME_PROVIDER_ENTRY_POINT_GROUP))
        if len(discovered) != 1:
            names = sorted(item.name for item in discovered)
            raise RuntimeError(
                "strategy-factory runtime host is not uniquely configured; "
                f"entry_point_group={RUNTIME_PROVIDER_ENTRY_POINT_GROUP} discovered={names}; "
                f"set {RUNTIME_PROVIDER_CONFIGURATOR_ENV_KEY}=module:callable"
            )
        configurator = discovered[0].load()
        path = f"entrypoint:{discovered[0].name}"
    if not callable(configurator):
        raise TypeError(f"runtime configurator is not callable: {path}")
    return configurator


def get_missing_required_runtime_providers(
    required_providers: tuple[str, ...] | list[str] = DEFAULT_REQUIRED_RUNTIME_PROVIDERS,
) -> list[str]:
    return [
        str(name)
        for name in tuple(required_providers or ())
        if str(name or "").strip() and not has_runtime_provider(str(name))
    ]


def runtime_services_ready(
    required_providers: tuple[str, ...] | list[str] = DEFAULT_REQUIRED_RUNTIME_PROVIDERS,
) -> bool:
    return not get_missing_required_runtime_providers(required_providers)


def ensure_default_runtime_services(
    *,
    configurator_path: str | None = None,
    required_providers: tuple[str, ...] | list[str] = DEFAULT_REQUIRED_RUNTIME_PROVIDERS,
) -> tuple[str, ...]:
    missing_before = get_missing_required_runtime_providers(required_providers)
    if not missing_before:
        return get_registered_runtime_provider_names()
    configurator = _load_configurator(configurator_path)
    configurator()
    missing_after = get_missing_required_runtime_providers(required_providers)
    if missing_after:
        raise RuntimeError(
            "strategy-factory canonical bootstrap did not register required providers; "
            f"missing={missing_after}"
        )
    return get_registered_runtime_provider_names()


def build_default_runtime_adapters(db: Any | None = None) -> Any:
    ensure_default_runtime_services()
    return build_scheduler_runtime_kwargs(db=db)["runtime_adapters"]


def build_default_scheduler_kwargs(db: Any | None = None) -> dict[str, Any]:
    ensure_default_runtime_services()
    return build_scheduler_runtime_kwargs(db=db)


__all__ = [
    "DEFAULT_REQUIRED_RUNTIME_PROVIDERS",
    "DEFAULT_RUNTIME_PROVIDER_CONFIGURATOR",
    "RUNTIME_PROVIDER_ENTRY_POINT_GROUP",
    "RUNTIME_PROVIDER_CONFIGURATOR_ENV_KEY",
    "build_default_runtime_adapters",
    "build_default_scheduler_kwargs",
    "ensure_default_runtime_services",
    "get_missing_required_runtime_providers",
    "runtime_services_ready",
]
