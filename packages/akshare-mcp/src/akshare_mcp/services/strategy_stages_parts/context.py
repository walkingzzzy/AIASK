
from __future__ import annotations

import asyncio
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
你是 A 股事件识别器。根据 market_snapshot、matched_theme_candidates、event_detection_hints、factor_research、research_task 输出 1-4 个最值得跟踪的事件。

规则:
1. 只要上述任一线索非空，就禁止输出 {"events":[]}
2. 优先使用 matched_theme_candidates 中已有的 theme_code
3. 若证据较弱，也要输出候选事件，并把 severity 设为 1-2
4. evidence 必须直接引用输入线索，不能留空
5. 只输出 JSON object，顶层 key 只能是 events

常用映射:
半导体/芯片/算力 -> chip_domestic
机器人/自动化 -> robotics_automation
白酒/食品饮料 -> liquor_consumption
银行/保险/高股息 -> high_dividend_banks
原油/油气 -> upstream_oil_gas

输出格式:
{"events":[{"theme_code":"chip_domestic","event_type":"sector_rotation","event_id":"ev_chip_001","title":"半导体板块走强","severity":3,"affected_sectors":["半导体"],"evidence":["半导体板块涨3.2%"]}]}"""

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

如果输入中包含 stock_fundamentals（真实基本面数据，来自数据库），你的策略逻辑必须与这些数据一致：
- 若 PE > 50，不得声称"估值低"或使用价值策略
- 若 ROE < 0.10，不得声称"质量优秀"
- 若 revenue_growth < 0，不得声称"高成长"
- 若 momentum_20d < 0，趋势策略需额外确认条件（如量能放大）
- 优先使用与基本面匹配的策略类型（低 PE → 均值回归；高 momentum → 趋势跟踪）

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
5. 必须严格服从 research_task.allowed_strategy_types；若该字段非空，不得生成未被允许的 strategy_type
6. 若 research_task.task_source="snapshot" 且 opportunity_type 属于 candidate_family_activation / candidate_factor_activation / factor_acceleration:
   - 默认只输出 1 个最高置信候选
   - 不得同时输出 momentum 和 ma_cross
   - 若 allowed_strategy_types 中不含 momentum，则禁止生成 momentum
   - ma_cross 必须使用更长周期(short>=10,long>=40)，并附加 close>sma20、roc20>0.01、volume_ratio20>=1.0 等确认
   - momentum 仅在 research_task 明确允许时可用，且 lookback>=20、threshold>=0.02，并附加 close>sma40、sma12>sma48、volume_ratio>=1.1 等确认

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

def _sector_item_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("group", "name", "sector", "theme_name", "label"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _snapshot_sector_names(snapshot: dict[str, Any], input_data: dict[str, Any]) -> list[str]:
    hot_sectors = list(
        (snapshot.get("hot_sectors") or input_data.get("market_snapshot", {}).get("sectors")) or []
    )
    names: list[str] = []
    for sector_item in hot_sectors[:8]:
        name = _sector_item_name(sector_item)
        if name and name not in names:
            names.append(name)
    return names

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
    """基于主题库的关键词匹配做简单传导推断。
    
    当 events 为空（并行 pipeline 模式下 event_recognition 尚未完成时）
    自动降级为从 snapshot 热门板块推断主题，保证输出非空。
    """
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

    if not themes:
        # 并行模式降级：从 snapshot 热门板块匹配主题库
        for name in _snapshot_sector_names(snapshot, input_data)[:6]:
            if not name:
                continue
            matched_code = _match_sector_to_theme(name)
            if not matched_code:
                continue
            theme_info = _THEME_LOOKUP.get(matched_code, {})
            parent = theme_info.get("parent", "")
            themes.append({
                "theme_code": matched_code,
                "theme_name": theme_info.get("name", matched_code),
                "source_event_id": f"snapshot_sector_{matched_code}",
                "propagation_chain": [parent, matched_code] if parent else [matched_code],
                "direction": "bullish",
                "confidence": 0.4,
            })

    return {"themes": themes}
