"""估值工具"""

from typing import Optional, List
from ..storage import get_db
from ..utils import ok, fail
import statistics



def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _cost_of_equity_capm(risk_free_rate: float, beta: float, market_risk_premium: float) -> float:
    """CAPM 权益成本"""
    return risk_free_rate + beta * market_risk_premium


def _after_tax_cost_of_debt(cost_of_debt: float, tax_rate: float) -> float:
    """税后债务成本"""
    return cost_of_debt * (1 - tax_rate)


def _compute_wacc(
    *,
    equity_weight: float,
    debt_weight: float,
    cost_of_equity: float,
    cost_of_debt: float,
    tax_rate: float,
) -> dict:
    """计算 WACC，并返回拆解详情。"""
    total_weight = equity_weight + debt_weight
    if total_weight <= 0:
        raise ValueError("equity_weight + debt_weight 必须大于 0")

    ew = equity_weight / total_weight
    dw = debt_weight / total_weight
    after_tax_debt = _after_tax_cost_of_debt(cost_of_debt, tax_rate)
    wacc = ew * cost_of_equity + dw * after_tax_debt
    return {
        "cost_of_equity": float(cost_of_equity),
        "cost_of_debt_pre_tax": float(cost_of_debt),
        "cost_of_debt_after_tax": float(after_tax_debt),
        "equity_weight": float(ew),
        "debt_weight": float(dw),
        "tax_rate": float(tax_rate),
        "wacc": float(wacc),
    }


def _build_driver_fcf_projection(
    *,
    base_revenue: float,
    growth_rate: float,
    years: int,
    profit_margin: float,
    tax_rate: float,
    capex_ratio: float,
    depreciation_ratio: float,
    nwc_ratio: float,
) -> List[dict]:
    """按驱动项构造未来 FCF 预测。"""
    projection = []
    for year in range(1, years + 1):
        revenue = base_revenue * ((1 + growth_rate) ** year)
        ebit = revenue * profit_margin
        nopat = ebit * (1 - tax_rate)
        depreciation = revenue * depreciation_ratio
        capex = revenue * capex_ratio
        delta_nwc = revenue * nwc_ratio
        fcf = nopat + depreciation - capex - delta_nwc
        projection.append(
            {
                "year": year,
                "revenue": float(revenue),
                "ebit": float(ebit),
                "nopat": float(nopat),
                "depreciation": float(depreciation),
                "capex": float(capex),
                "delta_nwc": float(delta_nwc),
                "fcf": float(fcf),
            }
        )
    return projection


def _present_value_from_projection(
    projection: List[dict],
    *,
    discount_rate: float,
    terminal_growth_rate: float,
) -> dict:
    """将 FCF 预测折现并计算终值。"""
    pv_sum = 0.0
    discounted_projection = []
    for row in projection:
        year = row["year"]
        pv = row["fcf"] / ((1 + discount_rate) ** year)
        pv_sum += pv
        item = dict(row)
        item["pv_fcf"] = float(pv)
        discounted_projection.append(item)

    last_fcf = projection[-1]["fcf"]
    terminal_fcf = last_fcf * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth_rate)
    pv_terminal = terminal_value / ((1 + discount_rate) ** projection[-1]["year"])

    return {
        "projection": discounted_projection,
        "pv_sum": float(pv_sum),
        "terminal_fcf": float(terminal_fcf),
        "terminal_value": float(terminal_value),
        "pv_terminal": float(pv_terminal),
        "intrinsic_value": float(pv_sum + pv_terminal),
    }


def _run_sensitivity(
    *,
    base_revenue: float,
    years: int,
    profit_margin: float,
    tax_rate: float,
    capex_ratio: float,
    depreciation_ratio: float,
    nwc_ratio: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
    growth_shocks: List[float],
    discount_shocks: List[float],
    terminal_shocks: List[float],
) -> List[dict]:
    """增长率/折现率/永续增长率三维敏感性。"""
    scenarios = []
    for g_shock in growth_shocks:
        for r_shock in discount_shocks:
            for tg_shock in terminal_shocks:
                g = growth_rate + g_shock
                r = discount_rate + r_shock
                tg = terminal_growth_rate + tg_shock
                if r <= tg:
                    continue
                projection = _build_driver_fcf_projection(
                    base_revenue=base_revenue,
                    growth_rate=g,
                    years=years,
                    profit_margin=profit_margin,
                    tax_rate=tax_rate,
                    capex_ratio=capex_ratio,
                    depreciation_ratio=depreciation_ratio,
                    nwc_ratio=nwc_ratio,
                )
                val = _present_value_from_projection(
                    projection,
                    discount_rate=r,
                    terminal_growth_rate=tg,
                )
                scenarios.append(
                    {
                        "growth_rate": float(g),
                        "discount_rate": float(r),
                        "terminal_growth_rate": float(tg),
                        "intrinsic_value": float(val["intrinsic_value"]),
                    }
                )
    return scenarios


# 供测试与审计复用的默认情景偏移
DEFAULT_SENSITIVITY_SHOCKS = [-0.01, 0.0, 0.01]


# ---------------------------------------------------------------------------
# P0-D: 行业参数模板 (Industry Parameter Templates)
# ---------------------------------------------------------------------------
# 每个行业模板包含 DCF 驱动项的合理默认值，用户可按需覆盖。
# 字段说明:
#   growth_rate       - 营收增长率
#   profit_margin     - 营业利润率
#   capex_ratio       - 资本开支 / 营收
#   depreciation_ratio- 折旧 / 营收
#   nwc_ratio         - 净营运资本变动 / 营收
#   beta              - CAPM Beta
#   equity_weight     - 权益占比
#   debt_weight       - 债务占比
#   cost_of_debt      - 债务成本
#   terminal_growth   - 永续增长率
# ---------------------------------------------------------------------------

INDUSTRY_TEMPLATES: dict = {
    "银行": {
        "label": "银行/金融",
        "growth_rate": 0.05,
        "profit_margin": 0.35,
        "capex_ratio": 0.02,
        "depreciation_ratio": 0.015,
        "nwc_ratio": 0.01,
        "beta": 0.8,
        "equity_weight": 0.12,
        "debt_weight": 0.88,
        "cost_of_debt": 0.025,
        "terminal_growth": 0.02,
    },
    "制造": {
        "label": "制造/工业",
        "growth_rate": 0.08,
        "profit_margin": 0.10,
        "capex_ratio": 0.08,
        "depreciation_ratio": 0.05,
        "nwc_ratio": 0.03,
        "beta": 1.1,
        "equity_weight": 0.60,
        "debt_weight": 0.40,
        "cost_of_debt": 0.045,
        "terminal_growth": 0.025,
    },
    "科技": {
        "label": "科技/TMT",
        "growth_rate": 0.15,
        "profit_margin": 0.18,
        "capex_ratio": 0.06,
        "depreciation_ratio": 0.04,
        "nwc_ratio": 0.02,
        "beta": 1.3,
        "equity_weight": 0.80,
        "debt_weight": 0.20,
        "cost_of_debt": 0.04,
        "terminal_growth": 0.03,
    },
    "消费": {
        "label": "消费/零售",
        "growth_rate": 0.10,
        "profit_margin": 0.14,
        "capex_ratio": 0.05,
        "depreciation_ratio": 0.035,
        "nwc_ratio": 0.025,
        "beta": 0.9,
        "equity_weight": 0.70,
        "debt_weight": 0.30,
        "cost_of_debt": 0.04,
        "terminal_growth": 0.025,
    },
    "医药": {
        "label": "医药/生物",
        "growth_rate": 0.12,
        "profit_margin": 0.20,
        "capex_ratio": 0.07,
        "depreciation_ratio": 0.04,
        "nwc_ratio": 0.02,
        "beta": 1.0,
        "equity_weight": 0.75,
        "debt_weight": 0.25,
        "cost_of_debt": 0.04,
        "terminal_growth": 0.025,
    },
}


def _scenario_dcf(
    *,
    base_revenue: float,
    years: int,
    tax_rate: float,
    risk_free_rate: float,
    market_risk_premium: float,
    scenarios: List[dict],
) -> dict:
    """
    多情景概率加权 DCF。

    每个 scenario 字典需包含:
        name, probability, growth_rate, profit_margin, capex_ratio,
        depreciation_ratio, nwc_ratio, beta, equity_weight, debt_weight,
        cost_of_debt, terminal_growth

    返回各情景估值明细 + 概率加权内在价值。
    """
    results = []
    weighted_value = 0.0
    total_prob = 0.0

    for sc in scenarios:
        prob = sc["probability"]
        total_prob += prob

        cost_of_equity = _cost_of_equity_capm(
            risk_free_rate, sc["beta"], market_risk_premium
        )
        wacc_info = _compute_wacc(
            equity_weight=sc["equity_weight"],
            debt_weight=sc["debt_weight"],
            cost_of_equity=cost_of_equity,
            cost_of_debt=sc["cost_of_debt"],
            tax_rate=tax_rate,
        )
        discount_rate = wacc_info["wacc"]
        terminal_growth = sc["terminal_growth"]

        if discount_rate <= terminal_growth:
            # 跳过不合理情景
            continue

        projection = _build_driver_fcf_projection(
            base_revenue=base_revenue,
            growth_rate=sc["growth_rate"],
            years=years,
            profit_margin=sc["profit_margin"],
            tax_rate=tax_rate,
            capex_ratio=sc["capex_ratio"],
            depreciation_ratio=sc["depreciation_ratio"],
            nwc_ratio=sc["nwc_ratio"],
        )
        pv_result = _present_value_from_projection(
            projection,
            discount_rate=discount_rate,
            terminal_growth_rate=terminal_growth,
        )

        intrinsic = pv_result["intrinsic_value"]
        weighted_value += prob * intrinsic

        results.append({
            "scenario": sc["name"],
            "probability": prob,
            "growth_rate": sc["growth_rate"],
            "profit_margin": sc["profit_margin"],
            "wacc": discount_rate,
            "terminal_growth": terminal_growth,
            "intrinsic_value": float(intrinsic),
            "weighted_contribution": float(prob * intrinsic),
        })

    # 归一化（防止概率之和不为 1）
    if total_prob > 0 and abs(total_prob - 1.0) > 1e-6:
        weighted_value /= total_prob
        for r in results:
            r["weighted_contribution"] = float(
                r["probability"] / total_prob * r["intrinsic_value"]
            )

    return {
        "scenarios": results,
        "weighted_intrinsic_value": float(weighted_value),
    }


def register(mcp):
    """注册估值工具"""

    @mcp.tool()
    async def get_valuation_metrics(code: str):
        """
        获取估值指标

        Args:
            code: 股票代码
        """
        try:
            db = get_db()

            # 从stocks表获取估值指标
            async with db.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT stock_code, stock_name, pe_ratio, pb_ratio, market_cap
                       FROM stocks
                       WHERE stock_code = $1""",
                    code
                )

                if not row:
                    return fail('Stock not found')

                return ok({
                    'code': row['stock_code'],
                    'name': row['stock_name'],
                    'pe_ratio': float(row['pe_ratio']) if row['pe_ratio'] else None,
                    'pb_ratio': float(row['pb_ratio']) if row['pb_ratio'] else None,
                    'market_cap': float(row['market_cap']) if row['market_cap'] else None,
                })

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def dcf_valuation(
        code: str,
        discount_rate: float = 0.10,
        growth_rate: float = 0.05,
        years: int = 5,
        risk_free_rate: float = 0.03,
        beta: float = 1.0,
        market_risk_premium: float = 0.06,
        cost_of_debt: float = 0.05,
        tax_rate: float = 0.25,
        equity_weight: float = 0.7,
        debt_weight: float = 0.3,
        terminal_growth_rate: Optional[float] = None,
        capex_ratio: float = 0.04,
        depreciation_ratio: float = 0.03,
        nwc_ratio: float = 0.01,
        enable_sensitivity: bool = True,
    ):
        """
        DCF估值（现金流折现，驱动项版本）

        Args:
            code: 股票代码
            discount_rate: 折现率（兼容参数；不传时由WACC估算）
            growth_rate: 显性预测期增长率
            years: 预测年数
            risk_free_rate: 无风险利率（CAPM）
            beta: Beta（CAPM）
            market_risk_premium: 市场风险溢价（CAPM）
            cost_of_debt: 税前债务成本
            tax_rate: 所得税率
            equity_weight: 权益资本权重
            debt_weight: 债务资本权重
            terminal_growth_rate: 永续增长率（缺省沿用growth_rate）
            capex_ratio: CapEx/Revenue
            depreciation_ratio: Depreciation/Revenue
            nwc_ratio: ΔNWC/Revenue
            enable_sensitivity: 是否执行敏感性分析
        """
        try:
            if years < 1:
                return fail('years 必须 >= 1')

            term_g = growth_rate if terminal_growth_rate is None else terminal_growth_rate

            # 参数边界保护
            tax_rate = _clamp(float(tax_rate), 0.0, 0.45)
            capex_ratio = _clamp(float(capex_ratio), 0.0, 0.3)
            depreciation_ratio = _clamp(float(depreciation_ratio), 0.0, 0.2)
            nwc_ratio = _clamp(float(nwc_ratio), -0.05, 0.1)

            db = get_db()
            financials = await db.get_financials(code, limit=max(8, years * 2))
            if not financials:
                return fail('No financial data for DCF')

            latest_valid = next(
                (
                    f for f in financials
                    if f.get('net_profit') is not None and float(f.get('net_profit')) > 0
                ),
                None,
            )
            if not latest_valid:
                return fail('No valid net profit for DCF')

            revenue_candidates = [
                float(f.get('revenue'))
                for f in financials
                if f.get('revenue') is not None and float(f.get('revenue')) > 0
            ]
            if not revenue_candidates:
                return fail('No valid revenue for DCF driver model')

            base_revenue = revenue_candidates[0]
            net_profit = float(latest_valid.get('net_profit'))
            profit_margin = _clamp(net_profit / base_revenue, 0.02, 0.5)

            cost_of_equity = _cost_of_equity_capm(risk_free_rate, beta, market_risk_premium)
            wacc_info = _compute_wacc(
                equity_weight=equity_weight,
                debt_weight=debt_weight,
                cost_of_equity=cost_of_equity,
                cost_of_debt=cost_of_debt,
                tax_rate=tax_rate,
            )
            implied_wacc = wacc_info['wacc']

            # 兼容旧接口：discount_rate 仍可显式覆盖
            effective_discount_rate = float(discount_rate) if discount_rate and discount_rate > 0 else implied_wacc
            if effective_discount_rate <= term_g:
                return fail('discount_rate/WACC 必须大于 terminal_growth_rate，避免终值分母<=0')

            projection = _build_driver_fcf_projection(
                base_revenue=base_revenue,
                growth_rate=growth_rate,
                years=years,
                profit_margin=profit_margin,
                tax_rate=tax_rate,
                capex_ratio=capex_ratio,
                depreciation_ratio=depreciation_ratio,
                nwc_ratio=nwc_ratio,
            )
            valuation_core = _present_value_from_projection(
                projection,
                discount_rate=effective_discount_rate,
                terminal_growth_rate=term_g,
            )

            sensitivity = []
            if enable_sensitivity:
                sensitivity = _run_sensitivity(
                    base_revenue=base_revenue,
                    years=years,
                    profit_margin=profit_margin,
                    tax_rate=tax_rate,
                    capex_ratio=capex_ratio,
                    depreciation_ratio=depreciation_ratio,
                    nwc_ratio=nwc_ratio,
                    growth_rate=growth_rate,
                    discount_rate=effective_discount_rate,
                    terminal_growth_rate=term_g,
                    growth_shocks=DEFAULT_SENSITIVITY_SHOCKS,
                    discount_shocks=DEFAULT_SENSITIVITY_SHOCKS,
                    terminal_shocks=DEFAULT_SENSITIVITY_SHOCKS,
                )

            return ok({
                'code': code,
                'intrinsic_value': float(valuation_core['intrinsic_value']),
                'discount_rate': float(effective_discount_rate),
                'growth_rate': float(growth_rate),
                'terminal_growth_rate': float(term_g),
                'years': int(years),
                'financial_report_date': latest_valid.get('report_date'),
                'model': 'Driver DCF with WACC',
                'wacc_breakdown': wacc_info,
                'driver_assumptions': {
                    'base_revenue': float(base_revenue),
                    'profit_margin': float(profit_margin),
                    'capex_ratio': float(capex_ratio),
                    'depreciation_ratio': float(depreciation_ratio),
                    'nwc_ratio': float(nwc_ratio),
                },
                'projection': valuation_core['projection'],
                'pv_sum': float(valuation_core['pv_sum']),
                'pv_terminal': float(valuation_core['pv_terminal']),
                'terminal_value': float(valuation_core['terminal_value']),
                'sensitivity': sensitivity,
                'meta': {
                    'trace': 'dcf_driver_v2',
                    'compatibility_mode': 'legacy_signature_plus_extensions',
                    'used_discount_source': 'input_discount_rate' if discount_rate and discount_rate > 0 else 'wacc',
                }
            })

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def ddm_valuation(
        code: str,
        dividend: Optional[float] = None,
        growth_rate: float = 0.05,
        required_return: float = 0.10
    ):
        """
        DDM估值（股息折现模型）

        Args:
            code: 股票代码
            dividend: 每股股息（不填则从数据估算）
            growth_rate: 股息增长率
            required_return: 要求回报率
        """
        try:
            if growth_rate >= required_return:
                return fail('增长率必须小于要求回报率')

            db = get_db()

            # 获取股息数据（如果没有提供）
            if not dividend:
                # 尝试从财务数据估算股息
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        """SELECT eps FROM financials
                           WHERE stock_code = $1
                           ORDER BY report_date DESC
                           LIMIT 1""",
                        code
                    )

                    if row and row['eps']:
                        # 假设分红率为30%
                        dividend = float(row['eps']) * 0.3

            if not dividend or dividend <= 0:
                return fail(f'股票 {code} 无股息数据，DDM模型不适用')

            # Gordon Growth Model: P = D1 / (r - g)
            next_dividend = dividend * (1 + growth_rate)
            intrinsic_value = next_dividend / (required_return - growth_rate)

            return ok({
                'code': code,
                'model': 'Gordon Growth Model (DDM)',
                'intrinsic_value': float(intrinsic_value),
                'current_dividend': dividend,
                'next_dividend': float(next_dividend),
                'growth_rate': growth_rate,
                'required_return': required_return,
            })

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def relative_valuation(
        code: str,
        metrics: Optional[List[str]] = None,
        peers: Optional[List[str]] = None
    ):
        """
        相对估值分析

        Args:
            code: 目标股票代码
            metrics: 估值指标列表，如['pe_ratio', 'pb_ratio', 'ps_ratio']
            peers: 可比公司列表（不填则自动查找同行业公司）
        """
        try:
            db = get_db()

            # 默认估值指标
            if not metrics:
                metrics = ['pe_ratio', 'pb_ratio']

            # 获取目标股票信息
            target_info = await db.get_stock_info(code)
            if not target_info:
                return fail(f'Stock {code} not found')

            target_industry = target_info.get('industry', '')
            target_market_cap = float(target_info.get('market_cap') or 0.0)
            target_financial = None
            try:
                target_financial = await db.get_financials(code, limit=1)
            except Exception:
                target_financial = None

            def _latest_row(rows):
                if isinstance(rows, list) and rows:
                    for item in rows:
                        if isinstance(item, dict):
                            return item
                if isinstance(rows, dict):
                    return rows
                return None

            target_fin_row = _latest_row(target_financial) or {}
            target_roe = target_fin_row.get('roe')
            target_debt_ratio = target_fin_row.get('debt_ratio')
            try:
                target_roe = float(target_roe) if target_roe is not None else None
            except Exception:
                target_roe = None
            try:
                target_debt_ratio = float(target_debt_ratio) if target_debt_ratio is not None else None
            except Exception:
                target_debt_ratio = None

            # 获取目标股票估值指标
            target_metrics = {}
            for metric in metrics:
                value = target_info.get(metric)
                if value and value > 0:
                    target_metrics[metric] = float(value)

            if not target_metrics:
                return fail(f'No valid valuation metrics for {code}')

            # 查找可比公司（优先同行业，扩大样本后再做层层过滤）
            if not peers:
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """SELECT stock_code FROM stocks
                           WHERE industry = $1 AND stock_code != $2
                           LIMIT 200""",
                        target_industry, code
                    )
                    peers = [row['stock_code'] for row in rows]

            if not peers:
                return fail(f'No peer companies found for industry: {target_industry}')

            # 获取候选可比公司估值与质量数据
            peer_candidates = []
            for peer_code in peers:
                peer_info = await db.get_stock_info(peer_code)
                if not peer_info:
                    continue

                peer_metrics = {'code': peer_code, 'name': peer_info.get('name', '')}
                valid = False
                for metric in metrics:
                    value = peer_info.get(metric)
                    if value and value > 0:
                        peer_metrics[metric] = float(value)
                        valid = True

                if valid:
                    peer_metrics['_market_cap'] = float(peer_info.get('market_cap') or 0.0)
                    peer_financial = None
                    try:
                        peer_financial = await db.get_financials(peer_code, limit=1)
                    except Exception:
                        peer_financial = None
                    peer_fin_row = _latest_row(peer_financial) or {}
                    try:
                        peer_metrics['_roe'] = (
                            float(peer_fin_row.get('roe'))
                            if peer_fin_row.get('roe') is not None
                            else None
                        )
                    except Exception:
                        peer_metrics['_roe'] = None
                    try:
                        peer_metrics['_debt_ratio'] = (
                            float(peer_fin_row.get('debt_ratio'))
                            if peer_fin_row.get('debt_ratio') is not None
                            else None
                        )
                    except Exception:
                        peer_metrics['_debt_ratio'] = None
                    peer_candidates.append(peer_metrics)

            if not peer_candidates:
                return fail('No valid peer data found')

            peer_pool_build = {
                'candidate_count': len(peer_candidates),
                'size_filter_relaxed': False,
                'quality_filter_relaxed': False,
                'size_ratio_min': 0.3,
                'size_ratio_max': 3.0,
                'quality_thresholds': {},
            }

            # 过滤1：规模可比（默认 0.3x~3x）
            peer_stage = peer_candidates
            size_filtered = peer_stage
            if target_market_cap > 0:
                size_filtered = [
                    p for p in peer_stage
                    if p.get('_market_cap', 0.0) > 0
                    and 0.3 <= (p.get('_market_cap', 0.0) / target_market_cap) <= 3.0
                ]
                peer_pool_build['after_size_filter'] = len(size_filtered)
                if len(size_filtered) >= 5:
                    peer_stage = size_filtered
                else:
                    peer_pool_build['size_filter_relaxed'] = True
            else:
                peer_pool_build['after_size_filter'] = len(peer_stage)

            # 过滤2：质量可比（ROE/负债率）
            quality_filtered = peer_stage
            roe_threshold = None
            debt_threshold = None
            if target_roe is not None:
                roe_threshold = max(0.05, target_roe * 0.5)
                peer_pool_build['quality_thresholds']['roe_min'] = roe_threshold
            if target_debt_ratio is not None:
                debt_threshold = min(0.95, target_debt_ratio + 0.25)
                peer_pool_build['quality_thresholds']['debt_ratio_max'] = debt_threshold

            if roe_threshold is not None or debt_threshold is not None:
                quality_filtered = []
                for p in peer_stage:
                    ok_roe = True
                    if roe_threshold is not None:
                        peer_roe = p.get('_roe')
                        ok_roe = (peer_roe is not None) and (peer_roe >= roe_threshold)

                    ok_debt = True
                    if debt_threshold is not None:
                        peer_debt = p.get('_debt_ratio')
                        ok_debt = (peer_debt is None) or (peer_debt <= debt_threshold)

                    if ok_roe and ok_debt:
                        quality_filtered.append(p)

                peer_pool_build['after_quality_filter'] = len(quality_filtered)
                if len(quality_filtered) >= 5:
                    peer_stage = quality_filtered
                else:
                    peer_pool_build['quality_filter_relaxed'] = True
            else:
                peer_pool_build['after_quality_filter'] = len(peer_stage)

            # 排序：优先规模更接近目标
            if target_market_cap > 0:
                peer_stage = sorted(
                    peer_stage,
                    key=lambda p: abs((p.get('_market_cap', target_market_cap) / target_market_cap) - 1.0),
                )

            peer_data = []
            for p in peer_stage:
                public_row = {k: v for k, v in p.items() if not str(k).startswith('_')}
                peer_data.append(public_row)

            if not peer_data:
                return fail('No valid peer data found')

            # 计算行业统计
            industry_stats = {}
            for metric in metrics:
                values = [p[metric] for p in peer_data if metric in p]
                if values:
                    industry_stats[metric] = {
                        'mean': float(statistics.mean(values)),
                        'median': float(statistics.median(values)),
                        'min': float(min(values)),
                        'max': float(max(values)),
                        'count': len(values)
                    }

            # 计算相对估值
            comparison = {}
            for metric in target_metrics:
                if metric in industry_stats:
                    target_value = target_metrics[metric]
                    industry_mean = industry_stats[metric]['mean']
                    industry_median = industry_stats[metric]['median']

                    comparison[metric] = {
                        'target': target_value,
                        'industry_mean': industry_mean,
                        'industry_median': industry_median,
                        'premium_to_mean': float((target_value - industry_mean) / industry_mean * 100) if industry_mean else None,
                        'premium_to_median': float((target_value - industry_median) / industry_median * 100) if industry_median else None,
                        'percentile': float(sum(1 for p in peer_data if p.get(metric, float('inf')) < target_value) / len(peer_data) * 100)
                    }

            return ok({
                'code': code,
                'name': target_info.get('name', ''),
                'industry': target_industry,
                'target_metrics': target_metrics,
                'industry_stats': industry_stats,
                'comparison': comparison,
                'peer_count': len(peer_data),
                'peer_pool_build': peer_pool_build,
                'peers': peer_data[:10]  # 只返回前10个可比公司
            })

        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def get_historical_valuation(
        code: str,
        days: int = 30
    ):
        """
        获取历史估值数据

        Args:
            code: 股票代码
            days: 查询天数
        """
        try:
            db = get_db()
            rows = []

            async with db.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT time, pe, pb, mkt_cap, price
                       FROM stock_quotes
                       WHERE code = $1
                       AND time >= NOW() - INTERVAL '1 day' * $2
                       ORDER BY time DESC""",
                    code, days
                )

            history = []
            if rows:
                for row in rows:
                    history.append({
                        'date': row['time'].strftime('%Y-%m-%d') if row['time'] else None,
                        'pe_ratio': float(row['pe']) if row['pe'] else None,
                        'pb_ratio': float(row['pb']) if row['pb'] else None,
                        'market_cap': float(row['mkt_cap']) if row['mkt_cap'] else None,
                        'price': float(row['price']) if row['price'] else None,
                    })
            else:
                # Fallback 1: 尝试实时行情补一条快照（不硬失败）
                try:
                    from .market.quote import get_realtime_quote
                    rt = get_realtime_quote(code)
                    data = rt.get('data') if isinstance(rt, dict) else None
                    if isinstance(data, dict) and data.get('price') is not None:
                        history.append({
                            'date': data.get('time', data.get('data_timestamp', ''))[:10] or None,
                            'pe_ratio': float(data['pe']) if data.get('pe') is not None else None,
                            'pb_ratio': float(data['pb']) if data.get('pb') is not None else None,
                            'market_cap': float(data['mkt_cap']) if data.get('mkt_cap') is not None else (
                                float(data['market_cap']) if data.get('market_cap') is not None else None
                            ),
                            'price': float(data['price']) if data.get('price') is not None else None,
                        })
                except Exception:
                    pass

                # Fallback 2: stock 基础估值兜底
                if not history:
                    stock_info = await db.get_stock_info(code)
                    if stock_info:
                        history.append({
                            'date': None,
                            'pe_ratio': float(stock_info['pe_ratio']) if stock_info.get('pe_ratio') is not None else None,
                            'pb_ratio': float(stock_info['pb_ratio']) if stock_info.get('pb_ratio') is not None else None,
                            'market_cap': float(stock_info['market_cap']) if stock_info.get('market_cap') is not None else None,
                            'price': None,
                        })

            # 计算统计信息
            pe_values = [h['pe_ratio'] for h in history if h['pe_ratio'] is not None]
            pb_values = [h['pb_ratio'] for h in history if h['pb_ratio'] is not None]

            stats = {}
            if pe_values:
                stats['pe'] = {
                    'current': pe_values[0],
                    'mean': float(statistics.mean(pe_values)),
                    'median': float(statistics.median(pe_values)),
                    'min': float(min(pe_values)),
                    'max': float(max(pe_values))
                }

            if pb_values:
                stats['pb'] = {
                    'current': pb_values[0],
                    'mean': float(statistics.mean(pb_values)),
                    'median': float(statistics.median(pb_values)),
                    'min': float(min(pb_values)),
                    'max': float(max(pb_values))
                }

            payload = {
                'code': code,
                'days': days,
                'history': history,
                'stats': stats,
                'count': len(history)
            }
            if not rows:
                payload['message'] = 'stock_quotes 无历史数据，已返回降级结果'
                payload['source'] = 'fallback'

            return ok(payload)

        except Exception as e:
            return fail(str(e))

    # ------------------------------------------------------------------
    # P0-D: 行业模板查询 & 多情景 DCF
    # ------------------------------------------------------------------

    @mcp.tool()
    async def list_industry_templates():
        """
        列出所有可用的行业参数模板

        返回各行业 DCF 默认参数（增长率、利润率、资本开支等），
        可直接用于 scenario_dcf_valuation 的 industry 参数。
        """
        return ok({
            "templates": {
                k: {**v} for k, v in INDUSTRY_TEMPLATES.items()
            },
            "available_industries": list(INDUSTRY_TEMPLATES.keys()),
        })

    @mcp.tool()
    async def scenario_dcf_valuation(
        code: str,
        base_revenue: float,
        industry: Optional[str] = None,
        years: int = 5,
        tax_rate: float = 0.25,
        risk_free_rate: float = 0.028,
        market_risk_premium: float = 0.06,
        shares_outstanding: Optional[float] = None,
        bull_probability: float = 0.25,
        base_probability: float = 0.50,
        bear_probability: float = 0.25,
        bull_growth_premium: float = 0.05,
        bear_growth_discount: float = 0.05,
        bull_margin_premium: float = 0.03,
        bear_margin_discount: float = 0.03,
        custom_scenarios: Optional[List[dict]] = None,
        growth_rate: Optional[float] = None,
        profit_margin: Optional[float] = None,
        capex_ratio: Optional[float] = None,
        depreciation_ratio: Optional[float] = None,
        nwc_ratio: Optional[float] = None,
        beta: Optional[float] = None,
        equity_weight: Optional[float] = None,
        debt_weight: Optional[float] = None,
        cost_of_debt: Optional[float] = None,
        terminal_growth: Optional[float] = None,
    ):
        """
        多情景概率加权 DCF 估值（支持行业模板）

        自动生成 Base / Bull / Bear 三情景并概率加权，
        也可通过 custom_scenarios 完全自定义情景。

        Args:
            code: 股票代码
            base_revenue: 基准年营收（元）
            industry: 行业模板名称（银行/制造/科技/消费/医药），不填则需手动指定参数
            years: 预测年数（默认5）
            tax_rate: 企业所得税率
            risk_free_rate: 无风险利率
            market_risk_premium: 市场风险溢价
            shares_outstanding: 总股本（填入后返回每股价值）
            bull_probability: 乐观情景概率（默认0.25）
            base_probability: 基准情景概率（默认0.50）
            bear_probability: 悲观情景概率（默认0.25）
            bull_growth_premium: 乐观情景增长率上浮
            bear_growth_discount: 悲观情景增长率下浮
            bull_margin_premium: 乐观情景利润率上浮
            bear_margin_discount: 悲观情景利润率下浮
            custom_scenarios: 完全自定义情景列表（提供后忽略自动生成）
            growth_rate: 覆盖行业模板的增长率
            profit_margin: 覆盖行业模板的利润率
            capex_ratio: 覆盖行业模板的资本开支率
            depreciation_ratio: 覆盖行业模板的折旧率
            nwc_ratio: 覆盖行业模板的净营运资本变动率
            beta: 覆盖行业模板的 Beta
            equity_weight: 覆盖行业模板的权益占比
            debt_weight: 覆盖行业模板的债务占比
            cost_of_debt: 覆盖行业模板的债务成本
            terminal_growth: 覆盖行业模板的永续增长率
        """
        try:
            # 1. 确定基准参数：行业模板 → 用户覆盖 → 默认值
            if industry and industry in INDUSTRY_TEMPLATES:
                tpl = INDUSTRY_TEMPLATES[industry]
            else:
                tpl = {}

            def _p(name, default):
                """优先级: 用户显式传参 > 行业模板 > 默认值"""
                user_val = locals_map.get(name)
                if user_val is not None:
                    return user_val
                return tpl.get(name, default)

            locals_map = {
                "growth_rate": growth_rate,
                "profit_margin": profit_margin,
                "capex_ratio": capex_ratio,
                "depreciation_ratio": depreciation_ratio,
                "nwc_ratio": nwc_ratio,
                "beta": beta,
                "equity_weight": equity_weight,
                "debt_weight": debt_weight,
                "cost_of_debt": cost_of_debt,
                "terminal_growth": terminal_growth,
            }

            base_gr = _p("growth_rate", 0.08)
            base_pm = _p("profit_margin", 0.12)
            base_capex = _p("capex_ratio", 0.06)
            base_depr = _p("depreciation_ratio", 0.04)
            base_nwc = _p("nwc_ratio", 0.02)
            base_beta = _p("beta", 1.0)
            base_ew = _p("equity_weight", 0.70)
            base_dw = _p("debt_weight", 0.30)
            base_cod = _p("cost_of_debt", 0.04)
            base_tg = _p("terminal_growth", 0.025)

            # 2. 构建情景
            if custom_scenarios:
                scenarios = custom_scenarios
            else:
                common = dict(
                    capex_ratio=base_capex,
                    depreciation_ratio=base_depr,
                    nwc_ratio=base_nwc,
                    beta=base_beta,
                    equity_weight=base_ew,
                    debt_weight=base_dw,
                    cost_of_debt=base_cod,
                    terminal_growth=base_tg,
                )
                scenarios = [
                    {
                        "name": "Bull（乐观）",
                        "probability": bull_probability,
                        "growth_rate": base_gr + bull_growth_premium,
                        "profit_margin": base_pm + bull_margin_premium,
                        **common,
                    },
                    {
                        "name": "Base（基准）",
                        "probability": base_probability,
                        "growth_rate": base_gr,
                        "profit_margin": base_pm,
                        **common,
                    },
                    {
                        "name": "Bear（悲观）",
                        "probability": bear_probability,
                        "growth_rate": max(base_gr - bear_growth_discount, 0.0),
                        "profit_margin": max(base_pm - bear_margin_discount, 0.01),
                        **common,
                    },
                ]

            # 3. 执行多情景 DCF
            result = _scenario_dcf(
                base_revenue=base_revenue,
                years=years,
                tax_rate=tax_rate,
                risk_free_rate=risk_free_rate,
                market_risk_premium=market_risk_premium,
                scenarios=scenarios,
            )

            payload = {
                "code": code,
                "model": "Multi-Scenario Probability-Weighted DCF",
                "industry": industry or "custom",
                "years": years,
                **result,
            }

            if shares_outstanding and shares_outstanding > 0:
                per_share = result["weighted_intrinsic_value"] / shares_outstanding
                payload["per_share_value"] = float(per_share)
                payload["shares_outstanding"] = shares_outstanding

            return ok(payload)

        except Exception as e:
            return fail(str(e))
