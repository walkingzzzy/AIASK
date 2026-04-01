"""策略工厂 + 策略超市 全面测试。"""

from ._test_strategy_factory_and_marketplace_autonomy import (
    _TestAutonomyEnhancementsCoreMixin,
    _TestAutonomyEnhancementsFactoryMixin,
    _TestAutonomyEnhancementsLlmMixin,
)
from ._test_strategy_factory_and_marketplace_misc import *
from ._test_strategy_factory_and_marketplace_runtime import *
from ._test_strategy_factory_and_marketplace_scheduler import (
    _TestStrategyFactorySchedulerGenerationMixin,
    _TestStrategyFactorySchedulerReportingMixin,
    _TestStrategyFactorySchedulerScannerMixin,
)
from ._test_strategy_factory_and_marketplace_vector_actions import *


class TestAutonomyEnhancements(
    _TestAutonomyEnhancementsCoreMixin,
    _TestAutonomyEnhancementsLlmMixin,
    _TestAutonomyEnhancementsFactoryMixin,
):
    pass


class TestStrategyFactoryScheduler(
    _TestStrategyFactorySchedulerGenerationMixin,
    _TestStrategyFactorySchedulerScannerMixin,
    _TestStrategyFactorySchedulerReportingMixin,
):
    pass
