from __future__ import annotations

import asyncio
import inspect

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Keep async tests on asyncio even when pytest-anyio is installed."""
    return "asyncio"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Bridge legacy ``@pytest.mark.asyncio`` tests onto pytest-anyio."""
    for item in items:
        obj = getattr(item, "obj", None)
        if not inspect.iscoroutinefunction(obj):
            continue
        if item.get_closest_marker("anyio") is None:
            item.add_marker(pytest.mark.anyio)


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run legacy coroutine tests even when pytest-asyncio is absent."""
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None
    funcargs = pyfuncitem.funcargs
    testargs = {arg: funcargs[arg] for arg in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(test_func(**testargs))
    return True
