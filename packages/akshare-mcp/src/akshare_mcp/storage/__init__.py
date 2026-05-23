"""Compatibility exports for the shared AIASK storage layer."""

import logging

from aiask_quant_core.storage import (
    SQLiteAdapter,
    await_with_db_cleanup,
    close_db,
    drain_cleanup_callbacks,
    get_db,
    run_with_db_cleanup,
)

logger = logging.getLogger(__name__)

try:
    from akshare_mcp.adapters.strategy_factory_runtime import (
        configure_akshare_storage_runtime_hooks,
    )

    configure_akshare_storage_runtime_hooks()
except Exception as exc:
    logger.debug("AKShare storage runtime hook registration skipped: %s", exc)

__all__ = [
    "SQLiteAdapter",
    "get_db",
    "close_db",
    "drain_cleanup_callbacks",
    "await_with_db_cleanup",
    "run_with_db_cleanup",
]
