import importlib

import strategy_factory.domain.constants as constants_mod


def test_constants_support_documented_bulk_and_spawner_aliases(monkeypatch):
    with monkeypatch.context() as env:
        for name in (
            "STRATEGY_FACTORY_BULK_STOCK_MATRIX_ENABLED",
            "STRATEGY_FACTORY_BULK_ENABLED",
            "STRATEGY_FACTORY_BULK_STOCK_MATRIX_FAMILIES_PER_STOCK",
            "STRATEGY_FACTORY_BULK_FAMILIES_PER_STOCK",
            "STRATEGY_FACTORY_BULK_STOCK_MATRIX_RUN_WINDOW",
            "STRATEGY_FACTORY_BULK_RUN_WINDOW",
            "STRATEGY_FACTORY_SPAWNER_EVENT_FILL_BUDGET_MAX",
            "STRATEGY_FACTORY_EVENT_FILL_BUDGET_MAX",
        ):
            env.delenv(name, raising=False)
        env.setenv("STRATEGY_FACTORY_BULK_ENABLED", "1")
        env.setenv("STRATEGY_FACTORY_BULK_FAMILIES_PER_STOCK", "4")
        env.setenv("STRATEGY_FACTORY_BULK_RUN_WINDOW", "off_hours")
        env.setenv("STRATEGY_FACTORY_EVENT_FILL_BUDGET_MAX", "6")

        reloaded = importlib.reload(constants_mod)

        assert reloaded.STOCK_STRATEGY_MATRIX_ENABLED is True
        assert reloaded.STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK == 4
        assert reloaded.STOCK_STRATEGY_MATRIX_RUN_WINDOW == "off_hours"
        assert reloaded.SPAWNER_EVENT_FILL_BUDGET_MAX == 6

    importlib.reload(constants_mod)


def test_constants_default_disable_factor_auto_refresh(monkeypatch):
    with monkeypatch.context() as env:
        env.delenv("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", raising=False)
        env.delenv("STRATEGY_FACTORY_FACTOR_REFRESH_TIMEOUT_SEC", raising=False)

        reloaded = importlib.reload(constants_mod)

        assert reloaded.is_factory_factor_auto_refresh_enabled() is False
        assert reloaded.FACTORY_FACTOR_AUTO_REFRESH is False
        assert reloaded.FACTORY_FACTOR_REFRESH_TIMEOUT_SEC == 30

    importlib.reload(constants_mod)
