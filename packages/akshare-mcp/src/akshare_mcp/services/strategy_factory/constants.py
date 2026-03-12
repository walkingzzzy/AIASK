"""策略工厂常量与配置"""

import os
from typing import Dict, List

# 回测用代表性股票（大盘/中盘/小盘各覆盖）
# 可通过环境变量 REPRESENTATIVE_STOCKS 覆盖，逗号分隔，如 "600519,000858,601318"
_DEFAULT_REPRESENTATIVE_STOCKS = [
    "600519", "000858", "601318", "600036", "000333",
    "002415", "600276", "601012", "300750", "000001",
]
_env_stocks = os.environ.get("REPRESENTATIVE_STOCKS", "").strip()
REPRESENTATIVE_STOCKS: List[str] = (
    [c.strip() for c in _env_stocks.split(",") if c.strip()]
    if _env_stocks else list(_DEFAULT_REPRESENTATIVE_STOCKS)
)

# 前端分类最低配额
CATEGORY_MINIMUMS = {
    "momentum": 3, "ma_cross": 3, "rsi": 3,
    "value_factor": 3, "quality_factor": 3, "growth_factor": 3,
    "multi_factor": 3, "macro_timing": 3,
}

# 初筛回测默认阈值与分层阈值
BACKTEST_DEFAULT_THRESHOLDS = {
    "sharpe_min": 0.30,
    "mdd_max": 0.35,
    "trades_min": 3,
    "min_samples": 3,
}

BACKTEST_AI_PROTOTYPE_THRESHOLDS = {
    "sharpe_min": 0.10,
    "mdd_max": 0.45,
    "trades_min": 1,
    "min_samples": 3,
}

# Fix #1/#2: 临时孵化准入阈值（区别于回测初筛阈值，更严格）
# 仅用于 maybe_grant_provisional_incubation，确保质量门失败的 AI 原型
# 必须通过更高标准才能进入孵化期
PROVISIONAL_PASS_THRESHOLDS = {
    "sharpe_min": 0.15,
    "mdd_max": 0.40,
    "trades_min": 2,
}

# 质量门 4 阶段验证阈值（strategy_manager._run_quality_gate 引用）
QUALITY_GATE_THRESHOLDS = {
    "walk_forward_ic_ir_min": 0.3,
    "purged_kfold_ic_min": 0.02,
    "bootstrap_ci_lower_min": 0.0,
    "param_sensitivity_max": 0.30,
}

# AI 原型策略临时孵化的风险报告阈值
RISK_REPORT_THRESHOLDS = {
    "var_percent_max": 4.5,
    "cvar_percent_max": 6.5,
    "stress_loss_percent_min": -25.0,
}

# 孵化期晋升/淘汰阈值
PROMOTION_THRESHOLDS = {
    "sharpe_min": 0.5,
    "mdd_max": 0.20,
    "hit_rate_blocker": 0.45,
    "hit_rate_risk_flag": 0.30,
}

DEPRECATION_THRESHOLDS = {
    "sharpe_negative": 0.0,
    "mdd_critical": 0.30,
}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


AUTONOMY_MAX_RESEARCH_TASKS = _env_int("STRATEGY_FACTORY_MAX_RESEARCH_TASKS", 8, minimum=1, maximum=20)
AUTONOMY_CANDIDATES_PER_TASK = _env_int("STRATEGY_FACTORY_CANDIDATES_PER_TASK", 4, minimum=1, maximum=8)
EVENT_TASK_GENERATION_LIMIT_MAX = _env_int("STRATEGY_FACTORY_EVENT_TASK_GENERATION_LIMIT_MAX", 8, minimum=2, maximum=10)
EVENT_SNAPSHOT_MIX_MAX = _env_int("STRATEGY_FACTORY_EVENT_SNAPSHOT_MIX_MAX", 2, minimum=1, maximum=6)
AUTONOMY_STARTUP_DELAY_SEC = _env_int("STRATEGY_FACTORY_STARTUP_DELAY_SEC", 0, minimum=0, maximum=3600)

# --- 有界并发配置 ---
# 研究任务并发度（同时执行的研究任务上限）
RESEARCH_TASK_CONCURRENCY = _env_int("STRATEGY_FACTORY_RESEARCH_TASK_CONCURRENCY", 5, minimum=1, maximum=12)
# 回测并发度（同时执行的候选回测上限）
BACKTEST_CONCURRENCY = _env_int("STRATEGY_FACTORY_BACKTEST_CONCURRENCY", 4, minimum=1, maximum=10)
# 提交并发度（同时执行的候选提交上限）
SUBMIT_CONCURRENCY = _env_int("STRATEGY_FACTORY_SUBMIT_CONCURRENCY", 3, minimum=1, maximum=8)
# 去重并发度
DEDUP_CONCURRENCY = _env_int("STRATEGY_FACTORY_DEDUP_CONCURRENCY", 3, minimum=1, maximum=6)

# --- 分级门禁 (Phase 2) ---
# Gate-1 快速筛选：通过后进入 Gate-2 的比例
GATE1_PASS_RATIO: float = float(os.environ.get("STRATEGY_FACTORY_GATE1_PASS_RATIO", "0.35") or 0.35)
# Gate-1 快速筛选的宽松 Sharpe 下限
GATE1_SHARPE_MIN: float = float(os.environ.get("STRATEGY_FACTORY_GATE1_SHARPE_MIN", "0.15") or 0.15)
# Gate-1 使用的代表性股票数量
GATE1_REPRESENTATIVE_COUNT: int = _env_int("STRATEGY_FACTORY_GATE1_REPRESENTATIVE_COUNT", 2, minimum=1, maximum=5)

# --- LLM fan-out (Phase 2) ---
LLM_FAN_OUT_COUNT: int = _env_int("STRATEGY_FACTORY_LLM_FAN_OUT_COUNT", 2, minimum=1, maximum=4)

# --- Spawner 扩展 (Phase 2) ---
SPAWNER_TARGET_TOTAL: int = _env_int("STRATEGY_FACTORY_SPAWNER_TARGET_TOTAL", 16, minimum=4, maximum=32)
SPAWNER_FILL_BUDGET_MAX: int = _env_int("STRATEGY_FACTORY_SPAWNER_FILL_BUDGET_MAX", 8, minimum=2, maximum=16)
SPAWNER_EVENT_FILL_BUDGET_MAX: int = _env_int("STRATEGY_FACTORY_SPAWNER_EVENT_FILL_BUDGET_MAX", 1, minimum=0, maximum=4)

# --- 调度模式配置 ---
# "continuous" = 24/7 循环（盘中15min、盘后60min）；"daily" = 每日定时一次（向后兼容）
FACTORY_SCHEDULE_MODE: str = (os.environ.get("STRATEGY_FACTORY_SCHEDULE_MODE", "continuous").strip().lower() or "continuous")
# A股盘中 (9:30-15:00 工作日) 循环间隔秒数
FACTORY_MARKET_HOURS_INTERVAL_SEC: int = _env_int("STRATEGY_FACTORY_MARKET_HOURS_INTERVAL_SEC", 900, minimum=60, maximum=7200)
# 盘后/周末/节假日循环间隔秒数
FACTORY_OFF_HOURS_INTERVAL_SEC: int = _env_int("STRATEGY_FACTORY_OFF_HOURS_INTERVAL_SEC", 3600, minimum=300, maximum=86400)
# 每日最大运行次数安全上限
FACTORY_MAX_DAILY_RUNS: int = _env_int("STRATEGY_FACTORY_MAX_DAILY_RUNS", 48, minimum=1, maximum=200)
# 出错后等待秒数
FACTORY_ERROR_BACKOFF_SEC: int = _env_int("STRATEGY_FACTORY_ERROR_BACKOFF_SEC", 120, minimum=10, maximum=3600)
# 仅 daily 模式生效：每日运行时间 (HH:MM)
FACTORY_DAILY_RUN_TIME: str = os.environ.get("STRATEGY_FACTORY_DAILY_RUN_TIME", "19:00").strip() or "19:00"

BACKTEST_TYPE_THRESHOLDS: Dict[str, dict] = {
    "momentum": {"sharpe_min": 0.35, "mdd_max": 0.32, "trades_min": 4},
    "ma_cross": {"sharpe_min": 0.25, "mdd_max": 0.35, "trades_min": 3},
    "rsi": {"sharpe_min": 0.20, "mdd_max": 0.38, "trades_min": 4},
    "value_factor": {"sharpe_min": 0.25, "mdd_max": 0.30, "trades_min": 3},
    "quality_factor": {"sharpe_min": 0.28, "mdd_max": 0.30, "trades_min": 3},
    "growth_factor": {"sharpe_min": 0.32, "mdd_max": 0.34, "trades_min": 4},
    "multi_factor": {"sharpe_min": 0.30, "mdd_max": 0.30, "trades_min": 4},
    "macro_timing": {"sharpe_min": 0.20, "mdd_max": 0.28, "trades_min": 2},
}

# --- 多阶段 Pipeline 配置 ---

PIPELINE_MODE: str = os.environ.get("STRATEGY_LLM_PIPELINE_MODE", "staged").strip().lower() or "staged"

PIPELINE_STAGE_TIMEOUT_SEC: float = float(os.environ.get("STRATEGY_PIPELINE_STAGE_TIMEOUT_SEC", "10") or 10)

# 每阶段独立超时（秒），缺失则回退到 PIPELINE_STAGE_TIMEOUT_SEC
PIPELINE_STAGE_TIMEOUTS: Dict[str, float] = {
    "event_recognition": 8.0,
    "theme_propagation": 6.0,
    "exposure_mapping": 8.0,
    "market_confirmation": 6.0,
    "strategy_generation": 12.0,
}

PIPELINE_STAGE_MAX_TOKENS: Dict[str, int] = {
    "event_recognition": 800,
    "theme_propagation": 600,
    "exposure_mapping": 800,
    "market_confirmation": 600,
    "strategy_generation": 1200,
}

PIPELINE_STAGE_TEMPERATURE: Dict[str, float] = {
    "event_recognition": 0.2,
    "theme_propagation": 0.2,
    "exposure_mapping": 0.25,
    "market_confirmation": 0.15,
    "strategy_generation": 0.3,
}
