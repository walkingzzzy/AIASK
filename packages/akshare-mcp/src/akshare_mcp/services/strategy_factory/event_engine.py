"""本地 DB 驱动的事件主题研究引擎兼容导出。"""

from strategy_factory.application.event_engine import (
    LOCAL_EVENT_ENGINE_NAME,
    LocalEventDrivenResearchEngine,
    get_local_event_engine,
)

__all__ = [
    "LOCAL_EVENT_ENGINE_NAME",
    "LocalEventDrivenResearchEngine",
    "get_local_event_engine",
]
