"""多阶段 AI 策略生成 — Stage 定义与注册表。

每个 Stage 拥有:
- 专属 system prompt（短而聚焦）
- 输入/输出 JSON schema（用于验证）
- 独立 fallback 函数（LLM 不可用时降级到本地规则引擎）
- 独立的 max_tokens / temperature 配置
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class StageDefinition:
    """一个 Pipeline 阶段的完整定义。"""

    stage_id: str
    system_prompt: str
    max_tokens: int = 500
    temperature: float = 0.2
    # 某些阶段本地规则更稳定时，可直接优先走 fallback，避免白白消耗 LLM 超时预算。
    prefer_fallback: bool = False
    # 输出中的必填顶层 key（用于快速验证）
    required_output_keys: list[str] = field(default_factory=list)
    # fallback 函数签名: (db, input_data, snapshot) -> dict
    fallback_fn: Optional[Callable[..., Coroutine[Any, Any, dict]]] = None


@dataclass
class StageResult:
    """单阶段执行结果。"""

    stage_id: str
    output: dict[str, Any]
    used_fallback: bool = False
    llm_attempted: bool = False
    prompt_chars: int = 0
    response_chars: int = 0
    elapsed_sec: float = 0.0
    error: Optional[str] = None
    llm_error: Optional[str] = None
    llm_error_type: Optional[str] = None
    llm_error_metrics: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extended theme library (扩展到 ~20 个预定义主题)
# ---------------------------------------------------------------------------

EXTENDED_THEME_LIBRARY: list[dict[str, Any]] = [
    {"theme_code": "upstream_oil_gas", "name": "上游油气", "aliases": ["石油", "油气", "原油", "炼化", "油服"], "parent": "commodities"},
    {"theme_code": "shipping_trade", "name": "航运贸易", "aliases": ["航运", "港口", "物流", "集运"], "parent": "global_trade"},
    {"theme_code": "chip_domestic", "name": "芯片半导体", "aliases": ["芯片", "半导体", "设备", "算力", "ai", "服务器"], "parent": "technology"},
    {"theme_code": "military_industry", "name": "军工国防", "aliases": ["军工", "国防", "航空", "航天"], "parent": "defense"},
    {"theme_code": "high_dividend_banks", "name": "高股息金融", "aliases": ["银行", "保险", "高股息", "运营商", "公用事业"], "parent": "defensive"},
    {"theme_code": "liquor_consumption", "name": "消费龙头", "aliases": ["白酒", "消费", "家电", "食品", "饮料"], "parent": "consumer"},
    {"theme_code": "new_energy_vehicle", "name": "新能源汽车", "aliases": ["新能源", "电动车", "锂电", "充电桩", "汽车"], "parent": "new_energy"},
    # 以下为扩展主题
    {"theme_code": "pharma_biotech", "name": "医药生物", "aliases": ["医药", "生物", "创新药", "CXO", "医疗器械"], "parent": "healthcare"},
    {"theme_code": "real_estate_chain", "name": "地产链", "aliases": ["房地产", "地产", "建材", "家居", "装修"], "parent": "real_estate"},
    {"theme_code": "photovoltaic_wind", "name": "光伏风电", "aliases": ["光伏", "风电", "储能", "新能源发电", "逆变器"], "parent": "new_energy"},
    {"theme_code": "rare_earth_metals", "name": "稀土有色", "aliases": ["稀土", "有色", "铜", "铝", "锂矿", "黄金"], "parent": "commodities"},
    {"theme_code": "telecom_5g", "name": "通信5G", "aliases": ["5G", "通信", "光模块", "光纤", "基站"], "parent": "technology"},
    {"theme_code": "software_saas", "name": "软件信创", "aliases": ["软件", "信创", "国产替代", "操作系统", "ERP"], "parent": "technology"},
    {"theme_code": "agriculture_food", "name": "农业食品", "aliases": ["农业", "种业", "化肥", "猪肉", "养殖"], "parent": "consumer"},
    {"theme_code": "infrastructure", "name": "基建工程", "aliases": ["基建", "建筑", "水利", "铁路", "城轨"], "parent": "infrastructure"},
    {"theme_code": "tourism_leisure", "name": "旅游休闲", "aliases": ["旅游", "酒店", "免税", "影视", "游戏"], "parent": "consumer"},
    {"theme_code": "carbon_neutral", "name": "碳中和", "aliases": ["碳中和", "碳交易", "环保", "节能", "绿电"], "parent": "policy"},
    {"theme_code": "robotics_automation", "name": "机器人自动化", "aliases": ["机器人", "自动化", "人形机器人", "减速器", "伺服"], "parent": "technology"},
    {"theme_code": "data_center_cloud", "name": "数据中心与云", "aliases": ["数据中心", "云计算", "IDC", "算力租赁", "液冷"], "parent": "technology"},
    {"theme_code": "insurance_pension", "name": "保险养老", "aliases": ["保险", "养老", "年金", "寿险"], "parent": "defensive"},
]

# 方便按 theme_code 快速查找
_THEME_LOOKUP: dict[str, dict[str, Any]] = {t["theme_code"]: t for t in EXTENDED_THEME_LIBRARY}


# ---------------------------------------------------------------------------
# System Prompts — 每个 ~150-250 token，聚焦单一任务
# ---------------------------------------------------------------------------

_PROMPT_EVENT_RECOGNITION = """\
你是一个 A 股市场事件识别引擎。根据提供的市场快照数据，在扩展主题库范围内识别 3-5 个当前活跃的市场事件。

规则:
1. 仅从 theme_library 中的 theme_code 选择，除非有强烈理由新增主题
2. 每个事件需给出事件类型(sector_rotation/policy/macro/earnings/flow)、严重程度(1-5)和受影响板块
3. 需引用具体数据证据(如板块涨跌幅、资金流向、龙虎榜等)

严格按以下 JSON 格式输出:
{"events": [{"theme_code": "chip_domestic", "event_type": "sector_rotation", "event_id": "ev_001", "title": "芯片板块资金流入", "severity": 3, "affected_sectors": ["半导体", "算力"], "evidence": ["芯片板块涨2.5%"]}]}"""

_PROMPT_THEME_PROPAGATION = """\
你是一个产业链传导分析引擎。根据识别出的事件，将每个事件映射到产业链传导路径。

规则:
1. 为每个事件识别上游→中游→下游传导链条
2. 给出传导方向(bullish/bearish)和置信度(0-1)
3. 只关注产业链逻辑，不涉及具体个股
4. 传导链条需符合 A 股市场实际产业关系

严格按以下 JSON 格式输出:
{"themes": [{"theme_code": "chip_domestic", "theme_name": "芯片半导体", "source_event_id": "ev_001", "propagation_chain": ["technology", "chip_domestic"], "direction": "bullish", "confidence": 0.7}]}"""

_PROMPT_EXPOSURE_MAPPING = """\
你是一个股票暴露映射引擎。将主题映射到具体的股票或行业板块暴露。

规则:
1. 从给定的股票池基本面摘要中选择与主题匹配的标的
2. 给出暴露类型(direct_beneficiary/indirect_beneficiary/hedge)和权重(0-1)
3. 每个主题映射 2-6 只标的
4. 优先选择基本面健康、流动性好的标的

严格按以下 JSON 格式输出:
{"exposures": [{"theme_code": "chip_domestic", "target_symbols": ["600519", "000858"], "sector": "芯片半导体", "exposure_type": "direct_beneficiary", "weight": 0.7}]}"""

_PROMPT_MARKET_CONFIRMATION = """\
你是一个技术面确认引擎。用技术信号验证基本面暴露是否当前可操作。

规则:
1. 对每只标的判断 confirmed(true/false)
2. 评估信号强度(strong/moderate/weak)和进场时机(immediate/wait_pullback/avoid)
3. 给出风险等级(low/medium/high)
4. 判断依据包括趋势方向、量价配合、RSI/MACD/均线位置

严格按以下 JSON 格式输出:
{"confirmations": [{"symbol": "600519", "confirmed": true, "theme_code": "liquor_consumption", "signal_strength": "moderate", "entry_timing": "immediate", "risk_level": "medium"}]}"""

_PROMPT_STRATEGY_GENERATION = """\
你是一个策略 DSL 生成引擎。必须为输入中的标的生成至少 1-2 个可回测的交易策略。

重要: 你必须生成候选策略，不得返回空列表。即使市场环境不理想，也要生成适合当前环境的防御性或均值回归策略。

DSL 格式要求:
- version: "1.0"
- timeframe: "daily"
- entry: 使用 {"any":[...]} 或 {"all":[...]} 组合条件
- exit: 同 entry 格式
- 条件支持的 op: gt, gte, lt, lte, cross_above, cross_below
- 支持的 indicator: sma, ema, rsi, roc, stddev, zscore, atr, volume_ratio
- 每个 indicator 需要 field(默认 "close") 和 window 参数

策略与标的匹配规则:
- 科技/成长/周期类(芯片、新能源、军工): 适合趋势跟踪(MA cross)和动量突破策略
- 银行/保险/高股息/公用事业类: 适合均值回归(RSI超卖买入、超买卖出)和区间震荡策略
- 消费类(白酒、家电): 适合趋势跟踪或RSI策略

规则:
1. 每个候选策略必须有 name, strategy_type, target_symbols, dsl, tags
2. entry 和 exit 条件必须完整可执行
3. 策略参数应合理(均线窗口 5-60，RSI 阈值 20-80)
4. 至少生成 1 个候选策略

严格按以下 JSON 格式输出(趋势跟踪示例):
{"candidates": [{"name": "芯片趋势跟踪", "strategy_type": "ma_cross", "target_symbols": ["600519"], "dsl": {"version": "1.0", "timeframe": "daily", "entry": {"any": [{"op": "cross_above", "left": {"indicator": "sma", "field": "close", "window": 5}, "right": {"indicator": "sma", "field": "close", "window": 20}}]}, "exit": {"any": [{"op": "cross_below", "left": {"indicator": "sma", "field": "close", "window": 5}, "right": {"indicator": "sma", "field": "close", "window": 20}}]}}, "tags": ["ai_staged", "ma_cross"]}]}

均值回归示例:
{"candidates": [{"name": "银行超卖回归", "strategy_type": "rsi", "target_symbols": ["601398"], "dsl": {"version": "1.0", "timeframe": "daily", "entry": {"all": [{"op": "lt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 35}}]}, "exit": {"any": [{"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 65}}]}}, "tags": ["ai_staged", "rsi", "mean_reversion"]}]}"""


# ---------------------------------------------------------------------------
# Output validators
# ---------------------------------------------------------------------------

def _try_find_list(output: dict[str, Any], primary_key: str, alt_keys: tuple[str, ...] = ()) -> list[Any] | None:
    """尝试从 LLM 输出中提取目标列表，容忍常见的键名变体。

    处理策略:
    1. 精确匹配 primary_key
    2. 尝试 alt_keys 别名
    3. 如果 output 只有 1 个 key 且其值是非空 list，直接采用
    """
    val = output.get(primary_key)
    if isinstance(val, list) and val:
        return val
    for k in alt_keys:
        val = output.get(k)
        if isinstance(val, list) and val:
            logger.debug("Validator: accepted alt key '%s' instead of '%s'", k, primary_key)
            return val
    # 单 key fallback
    if len(output) == 1:
        only_val = next(iter(output.values()))
        if isinstance(only_val, list) and only_val:
            logger.debug("Validator: accepted single-key fallback for '%s'", primary_key)
            return only_val
    return None


def _validate_event_recognition(output: dict[str, Any]) -> bool:
    events = _try_find_list(output, "events", ("event_list", "market_events", "results"))
    if not events:
        logger.debug("event_recognition validation failed: no 'events' list, keys=%s", list(output.keys()))
        return False
    # 回写到标准 key 以便下游消费
    output["events"] = events
    for ev in events:
        if not isinstance(ev, dict):
            return False
        if not ev.get("theme_code") or not ev.get("event_type"):
            logger.debug("event_recognition item missing theme_code/event_type: %s", list(ev.keys()))
            return False
    return True


def _validate_theme_propagation(output: dict[str, Any]) -> bool:
    themes = _try_find_list(output, "themes", ("theme_list", "propagation", "propagation_result", "results"))
    if not themes:
        logger.debug("theme_propagation validation failed: no 'themes' list, keys=%s", list(output.keys()))
        return False
    output["themes"] = themes
    for th in themes:
        if not isinstance(th, dict):
            return False
        if not th.get("theme_code"):
            logger.debug("theme_propagation item missing theme_code: %s", list(th.keys()))
            return False
    return True


def _validate_exposure_mapping(output: dict[str, Any]) -> bool:
    exposures = _try_find_list(output, "exposures", ("exposure_list", "mappings", "exposure_mapping", "results"))
    if not exposures:
        logger.debug("exposure_mapping validation failed: no 'exposures' list, keys=%s", list(output.keys()))
        return False
    output["exposures"] = exposures
    for exp in exposures:
        if not isinstance(exp, dict):
            return False
        # 容忍 target_symbols 的别名
        if not exp.get("target_symbols"):
            for alt in ("symbols", "stocks", "stock_codes", "targets"):
                if exp.get(alt):
                    exp["target_symbols"] = exp[alt]
                    break
        if not exp.get("theme_code") or not exp.get("target_symbols"):
            logger.debug("exposure_mapping item missing theme_code/target_symbols: %s", list(exp.keys()))
            return False
    return True


def _validate_market_confirmation(output: dict[str, Any]) -> bool:
    confirmations = _try_find_list(output, "confirmations", ("confirmation_list", "confirmed_stocks", "results"))
    if not confirmations:
        logger.debug("market_confirmation validation failed: no 'confirmations' list, keys=%s", list(output.keys()))
        return False
    output["confirmations"] = confirmations
    for conf in confirmations:
        if not isinstance(conf, dict):
            return False
        # 容忍 symbol 的别名
        if not conf.get("symbol"):
            for alt in ("code", "stock_code", "stock", "ticker"):
                if conf.get(alt):
                    conf["symbol"] = conf[alt]
                    break
        if "confirmed" not in conf or not conf.get("symbol"):
            logger.debug("market_confirmation item missing symbol/confirmed: %s", list(conf.keys()))
            return False
    return True


def _validate_strategy_generation(output: dict[str, Any]) -> bool:
    candidates = _try_find_list(output, "candidates", ("strategies", "strategy_list", "results"))
    if not candidates:
        logger.debug("strategy_generation validation failed: no 'candidates' list, keys=%s", list(output.keys()))
        return False
    output["candidates"] = candidates
    for cand in candidates:
        if not isinstance(cand, dict):
            return False
        dsl = cand.get("dsl")
        if not isinstance(dsl, dict) or not dsl.get("entry") or not dsl.get("exit"):
            logger.debug("strategy_generation item missing dsl.entry/exit: %s", list((dsl or {}).keys()) if isinstance(dsl, dict) else "no dsl")
            return False
        # 补全 strategy_type（LLM 可能遗漏）
        if not cand.get("strategy_type"):
            cand["strategy_type"] = "dsl_rule"
        # 补全 dsl.version
        if not dsl.get("version"):
            dsl["version"] = "1.0"
        if not dsl.get("timeframe"):
            dsl["timeframe"] = "daily"
    return True


_VALIDATORS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "event_recognition": _validate_event_recognition,
    "theme_propagation": _validate_theme_propagation,
    "exposure_mapping": _validate_exposure_mapping,
    "market_confirmation": _validate_market_confirmation,
    "strategy_generation": _validate_strategy_generation,
}


# ---------------------------------------------------------------------------
# Fallback functions — 调用现有规则引擎
# ---------------------------------------------------------------------------

async def _fallback_event_recognition(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用 LocalEventDrivenResearchEngine 的规则检测作为 fallback。"""
    from strategy_factory import get_local_event_engine

    engine = get_local_event_engine()
    result = await engine.refresh(db, snapshot=snapshot)
    events: list[dict[str, Any]] = []
    # 从 event_engine 结果中提取活跃事件
    for cluster in list(result.get("event_clusters") or []):
        theme_code = str(cluster.get("theme_code") or "").strip()
        if not theme_code:
            continue
        events.append({
            "event_id": cluster.get("event_id", f"local_{theme_code}"),
            "theme_code": theme_code,
            "event_type": "theme_rotation",
            "title": cluster.get("theme_name") or theme_code,
            "severity": 3,
            "affected_sectors": list(cluster.get("affected_sectors") or []),
            "evidence": [cluster.get("direction_reason") or "rule-based detection"],
        })
    # 如果 event_engine 没有返回 event_clusters，从 market_internals 推断
    if not events:
        internals = dict(result.get("market_internals") or {})
        hot_sectors = list(internals.get("hot_sectors") or [])
        for sector_info in hot_sectors[:5]:
            name = str(sector_info if isinstance(sector_info, str) else (sector_info or {}).get("group", "")).strip()
            if not name:
                continue
            # 尝试匹配主题库
            matched_code = _match_sector_to_theme(name)
            events.append({
                "event_id": f"local_hot_{name}",
                "theme_code": matched_code or "unknown",
                "event_type": "sector_rotation",
                "title": f"{name}板块活跃",
                "severity": 2,
                "affected_sectors": [name],
                "evidence": ["rule-based hot sector detection"],
            })
    return {"events": events[:5]}


async def _fallback_theme_propagation(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """基于主题库的关键词匹配做简单传导推断。"""
    events = list(input_data.get("events") or [])
    themes: list[dict[str, Any]] = []
    for ev in events:
        theme_code = str(ev.get("theme_code") or "").strip()
        theme_info = _THEME_LOOKUP.get(theme_code, {})
        parent = theme_info.get("parent", "")
        themes.append({
            "theme_code": theme_code,
            "theme_name": theme_info.get("name", theme_code),
            "source_event_id": ev.get("event_id", ""),
            "propagation_chain": [parent, theme_code] if parent else [theme_code],
            "direction": "bullish" if ev.get("severity", 3) <= 3 else "bearish",
            "confidence": 0.5,
        })
    return {"themes": themes}


async def _fallback_exposure_mapping(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用 opportunity.py 的规则扫描做板块→成分股映射。"""
    themes = list(input_data.get("themes") or [])
    exposures: list[dict[str, Any]] = []

    # 尝试从 DB 加载股票池并按主题关键词匹配
    from strategy_factory import _call_optional_async
    universe = await _call_optional_async(db, "list_stock_universe", limit=200, offset=0, default=[])

    for th in themes:
        theme_code = str(th.get("theme_code") or "").strip()
        theme_info = _THEME_LOOKUP.get(theme_code, {})
        aliases = [a.lower() for a in list(theme_info.get("aliases") or [])]
        if not aliases:
            continue
        matched_symbols: list[str] = []
        for row in list(universe or []):
            name = str(row.get("name") or "").lower()
            industry = str(row.get("industry") or "").lower()
            sector = str(row.get("sector") or "").lower()
            text = f"{name} {industry} {sector}"
            if any(alias in text for alias in aliases):
                code = str(row.get("code") or "").strip()
                if code:
                    matched_symbols.append(code)
            if len(matched_symbols) >= 6:
                break
        if matched_symbols:
            exposures.append({
                "theme_code": theme_code,
                "target_symbols": matched_symbols,
                "sector": theme_info.get("name", theme_code),
                "exposure_type": "direct_beneficiary",
                "weight": 0.5,
            })
    return {"exposures": exposures}


async def _fallback_market_confirmation(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用技术面扫描逻辑做确认。"""
    from strategy_factory import _call_optional_async

    exposures = list(input_data.get("exposures") or [])
    confirmations: list[dict[str, Any]] = []
    for exp in exposures:
        for symbol in list(exp.get("target_symbols") or [])[:4]:
            try:
                klines = await _call_optional_async(db, "get_klines", symbol, limit=30, default=[])
            except TypeError:
                klines = await _call_optional_async(db, "get_klines", symbol, default=[])
            klines = list(klines or [])
            confirmed = False
            signal_strength = "weak"
            if len(klines) >= 5:
                closes = [float(k.get("close") or 0) for k in klines if k.get("close") is not None]
                if len(closes) >= 5:
                    ma5 = sum(closes[-5:]) / 5
                    ma20 = sum(closes[-20:]) / max(len(closes[-20:]), 1) if len(closes) >= 20 else sum(closes) / len(closes)
                    last_close = closes[-1]
                    # 简单确认: 价格在均线上方且短均线>长均线
                    if last_close > ma20 and ma5 > ma20:
                        confirmed = True
                        signal_strength = "moderate"
                    if last_close > ma5 > ma20:
                        signal_strength = "strong"
            confirmations.append({
                "theme_code": exp.get("theme_code", ""),
                "symbol": symbol,
                "confirmed": confirmed,
                "signal_strength": signal_strength,
                "entry_timing": "immediate" if confirmed else "avoid",
                "risk_level": "medium",
            })
    return {"confirmations": confirmations}


def _is_defensive_theme(theme_code: str) -> bool:
    """判断主题是否属于防御/价值类（适合均值回归而非趋势跟踪）。"""
    theme_info = _THEME_LOOKUP.get(theme_code, {})
    parent = theme_info.get("parent", "")
    if parent in ("defensive",):
        return True
    if theme_code in ("high_dividend_banks", "insurance_pension"):
        return True
    return False


def _build_trend_templates(theme_name: str, theme_code: str, symbols: list[str], stock_pool: dict) -> list[dict[str, Any]]:
    """趋势跟踪 + 动量突破模板（适合科技/周期/成长类标的）。"""
    templates = []
    templates.append({
        "name": f"{theme_name}_趋势跟踪",
        "strategy_type": "ma_cross",
        "target_symbols": list(symbols),
        "dsl": {
            "version": "1.0",
            "timeframe": "daily",
            "entry": {
                "any": [{
                    "op": "cross_above",
                    "left": {"indicator": "sma", "field": "close", "window": 5},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                }],
            },
            "exit": {
                "any": [{
                    "op": "cross_below",
                    "left": {"indicator": "sma", "field": "close", "window": 5},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                }],
            },
            "metadata": {"target_symbols": list(symbols), "stock_pool": stock_pool},
        },
        "tags": ["ai_staged", theme_code, "ma_cross"],
    })
    if len(symbols) >= 2:
        templates.append({
            "name": f"{theme_name}_动量突破",
            "strategy_type": "momentum",
            "target_symbols": list(symbols),
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "all": [
                        {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 10}, "right": {"value": 0.02}},
                        {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 20}, "right": {"value": 1.2}},
                    ],
                },
                "exit": {
                    "any": [
                        {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 10}, "right": {"value": -0.03}},
                        {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 75}},
                    ],
                },
                "metadata": {"target_symbols": list(symbols), "stock_pool": stock_pool},
            },
            "tags": ["ai_staged", theme_code, "momentum"],
        })
    return templates


def _build_mean_reversion_templates(theme_name: str, theme_code: str, symbols: list[str], stock_pool: dict) -> list[dict[str, Any]]:
    """均值回归 + 高股息低吸模板（适合银行/保险/高股息/公用事业类标的）。"""
    templates = []
    # RSI 超卖回归策略
    templates.append({
        "name": f"{theme_name}_超卖回归",
        "strategy_type": "rsi",
        "target_symbols": list(symbols),
        "dsl": {
            "version": "1.0",
            "timeframe": "daily",
            "entry": {
                "all": [
                    {"op": "lt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 35}},
                    {"op": "gt", "left": {"indicator": "volume_ratio", "field": "volume", "window": 20}, "right": {"value": 0.8}},
                ],
            },
            "exit": {
                "any": [
                    {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 14}, "right": {"value": 65}},
                ],
            },
            "metadata": {"target_symbols": list(symbols), "stock_pool": stock_pool},
        },
        "tags": ["ai_staged", theme_code, "rsi", "mean_reversion"],
    })
    # 布林带回归策略
    if len(symbols) >= 2:
        templates.append({
            "name": f"{theme_name}_区间震荡",
            "strategy_type": "rsi",
            "target_symbols": list(symbols),
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "all": [
                        {"op": "lt", "left": {"indicator": "rsi", "field": "close", "window": 6}, "right": {"value": 25}},
                        {"op": "lt", "left": {"indicator": "roc", "field": "close", "window": 5}, "right": {"value": -0.01}},
                    ],
                },
                "exit": {
                    "any": [
                        {"op": "gt", "left": {"indicator": "rsi", "field": "close", "window": 6}, "right": {"value": 55}},
                        {"op": "gt", "left": {"indicator": "roc", "field": "close", "window": 5}, "right": {"value": 0.03}},
                    ],
                },
                "metadata": {"target_symbols": list(symbols), "stock_pool": stock_pool},
            },
            "tags": ["ai_staged", theme_code, "rsi", "mean_reversion"],
        })
    return templates


async def _fallback_strategy_generation(db: Any, input_data: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """使用 DSL 模板库生成策略，根据主题类型选择合适的策略模板。"""
    confirmations = list(input_data.get("confirmations") or [])
    confirmed = [c for c in confirmations if c.get("confirmed")]
    if not confirmed:
        confirmed = confirmations[:2]  # 至少生成一些候选

    # 按 theme_code 分组
    theme_symbols: dict[str, list[str]] = {}
    for conf in confirmed:
        tc = str(conf.get("theme_code") or "default").strip()
        sym = str(conf.get("symbol") or "").strip()
        if sym:
            theme_symbols.setdefault(tc, []).append(sym)

    candidates: list[dict[str, Any]] = []
    for theme_code, symbols in theme_symbols.items():
        theme_info = _THEME_LOOKUP.get(theme_code, {})
        theme_name = theme_info.get("name", theme_code)
        stock_pool = {"selection_mode": "explicit", "symbols": list(symbols)}

        if _is_defensive_theme(theme_code):
            templates = _build_mean_reversion_templates(theme_name, theme_code, symbols, stock_pool)
            logger.debug("Fallback: using mean-reversion templates for defensive theme '%s'", theme_code)
        else:
            templates = _build_trend_templates(theme_name, theme_code, symbols, stock_pool)
        candidates.extend(templates)

    return {"candidates": candidates[:6]}


def _match_sector_to_theme(sector_name: str) -> str:
    """将板块名称匹配到主题库中的 theme_code。"""
    sector_lower = sector_name.lower()
    for theme in EXTENDED_THEME_LIBRARY:
        for alias in list(theme.get("aliases") or []):
            if alias.lower() in sector_lower or sector_lower in alias.lower():
                return theme["theme_code"]
    return ""


# ---------------------------------------------------------------------------
# Stage Definitions — 注册表
# ---------------------------------------------------------------------------

def _build_stage_definitions() -> dict[str, StageDefinition]:
    """构建 5 个 Stage 的定义。"""
    from strategy_factory import (
        PIPELINE_STAGE_MAX_TOKENS,
        PIPELINE_STAGE_TEMPERATURE,
    )

    return {
        "event_recognition": StageDefinition(
            stage_id="event_recognition",
            system_prompt=_PROMPT_EVENT_RECOGNITION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("event_recognition", 600),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("event_recognition", 0.2),
            required_output_keys=["events"],
            fallback_fn=_fallback_event_recognition,
        ),
        "theme_propagation": StageDefinition(
            stage_id="theme_propagation",
            system_prompt=_PROMPT_THEME_PROPAGATION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("theme_propagation", 400),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("theme_propagation", 0.2),
            required_output_keys=["themes"],
            fallback_fn=_fallback_theme_propagation,
        ),
        "exposure_mapping": StageDefinition(
            stage_id="exposure_mapping",
            system_prompt=_PROMPT_EXPOSURE_MAPPING,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("exposure_mapping", 500),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("exposure_mapping", 0.25),
            required_output_keys=["exposures"],
            fallback_fn=_fallback_exposure_mapping,
        ),
        "market_confirmation": StageDefinition(
            stage_id="market_confirmation",
            system_prompt=_PROMPT_MARKET_CONFIRMATION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("market_confirmation", 500),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("market_confirmation", 0.15),
            required_output_keys=["confirmations"],
            fallback_fn=_fallback_market_confirmation,
        ),
        "strategy_generation": StageDefinition(
            stage_id="strategy_generation",
            system_prompt=_PROMPT_STRATEGY_GENERATION,
            max_tokens=PIPELINE_STAGE_MAX_TOKENS.get("strategy_generation", 800),
            temperature=PIPELINE_STAGE_TEMPERATURE.get("strategy_generation", 0.3),
            required_output_keys=["candidates"],
            fallback_fn=_fallback_strategy_generation,
        ),
    }


# 惰性初始化的全局注册表
_stage_registry: Optional[dict[str, StageDefinition]] = None


def get_stage_registry() -> dict[str, StageDefinition]:
    global _stage_registry
    if _stage_registry is None:
        _stage_registry = _build_stage_definitions()
    return _stage_registry


def validate_stage_output(stage_id: str, output: dict[str, Any]) -> bool:
    """验证阶段输出是否合法。"""
    validator = _VALIDATORS.get(stage_id)
    if validator is None:
        return True
    try:
        return validator(output)
    except Exception:
        return False


# Pipeline 阶段执行顺序
STAGE_ORDER: list[str] = [
    "event_recognition",
    "theme_propagation",
    "exposure_mapping",
    "market_confirmation",
    "strategy_generation",
]
