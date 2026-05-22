"""Factor mining runtime facade.

The concrete factor mining factory is supplied by the host runtime registry.
"""

from __future__ import annotations

from ..infrastructure.mcp_services import get_factor_mining_factory

__all__ = ["get_factor_mining_factory"]
