from __future__ import annotations

import os


os.environ.setdefault("AIASK_AGENT_LOAD_PROJECT_ENV", "0")


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--run-live-hermes",
        action="store_true",
        default=False,
        help="Run optional live AIASK-native Hermes smoke tests when credentials are configured.",
    )
    parser.addoption(
        "--run-live-ai",
        action="store_true",
        default=False,
        help="Run optional live AIASK model smoke tests when credentials are configured.",
    )
