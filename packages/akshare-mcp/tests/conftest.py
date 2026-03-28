"""pytest conftest for akshare-mcp tests.

Key isolation concerns
----------------------
``akshare_mcp.services.artifact_registry._ARTIFACTS`` is a module-level dict
that acts as an in-memory fallback cache.  When the real TimescaleDB is
reachable during a test session it gets populated by live DB reads; those
cached entries then "leak" into subsequent tests and cause non-deterministic
behavior (e.g. the ``factor_research`` stage flipping from PARTIAL to
COMPLETED because governance artifacts from a prior test are still cached).

The autouse fixture below resets the cache before every test function so that
each test starts from a clean slate.
"""

import pytest


@pytest.fixture(autouse=True)
def reset_artifact_registry_cache():
    """Clear the artifact in-memory cache before and after every test."""
    import akshare_mcp.services.artifact_registry as _ar_mod

    _ar_mod._ARTIFACTS.clear()
    yield
    _ar_mod._ARTIFACTS.clear()
