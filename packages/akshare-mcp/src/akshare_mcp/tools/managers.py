"""Compatibility shim for manager registration.

Canonical manager implementations live under ``akshare_mcp.tools.managers``.
This module is kept only for backward compatibility and delegates registration.
"""

from .managers import register as _register


def register(mcp):
    return _register(mcp)

