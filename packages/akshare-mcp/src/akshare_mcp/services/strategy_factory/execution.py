"""策略工厂执行模块兼容导出。"""

from .elimination import EliminationChecker
from .submitter import StrategySubmitter

__all__ = ["StrategySubmitter", "EliminationChecker"]
