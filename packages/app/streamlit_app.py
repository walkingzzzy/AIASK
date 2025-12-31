"""
A股智能分析系统 - Streamlit MVP界面
"""
import sys
import os


import streamlit as st
import pandas as pd
from datetime import datetime

# 页面配置
st.set_page_config(
    page_title="A股智能分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 导入服务
from packages.core.services.stock_data_service import get_stock_service
from packages.core.nlp_query.intent_parser import IntentParser
from packages.core.nlp_query.query_executor import QueryExecutor
from packages.core.services.stock_screener_service import StockScreenerService
from packages.core.services.portfolio_service import PortfolioService
from app.backtest_page import render_backtest_page


def init_session_state():
    """初始化session state"""
    if "service" not in st.session_state:
        st.session_state.service = get_stock_service()
    if "query_history" not in st.session_state:
        st.session_state.query_history = []
    if "intent_parser" not in st.session_state:
        st.session_state.intent_parser = IntentParser()
    if "query_executor" not in st.session_state:
        st.session_state.query_executor = QueryExecutor()
    if "screener_service" not in st.session_state:
        st.session_state.screener_service = StockScreenerService()
    if "portfolio_service" not in st.session_state:
        st.session_state.portfolio_service = PortfolioService()


def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.title("📈 A股智能分析")
    st.sidebar.markdown("---")

    # 功能选择
    page = st.sidebar.radio(
        "功能选择",
        ["🎯 AI评分", "📊 技术分析", "💬 智能问答", "📋 批量筛选", "🔍 选股雷达", "💼 组合管理", "📈 回测分析"],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 快捷入口")

    # 热门股票
    hot_stocks = [
        ("贵州茅台", "600519"),
        ("宁德时代", "300750"),
        ("比亚迪", "002594"),
        ("招商银行", "600036"),
        ("中国平安", "601318"),
    ]

    for name, code in hot_stocks:
        if st.sidebar.button(f"{name} ({code})", key=f"hot_{code}"):
            st.session_state.selected_stock = code
            st.session_state.selected_name = name

    st.sidebar.markdown("---")
    st.sidebar.caption("版本: MVP v0.1")
    st.sidebar.caption(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    return page


def render_ai_score_page():
    """AI评分页面"""
    st.title("🎯 AI智能评分")
    st.markdown("基于技术面、基本面、资金面、情绪面、风险五个维度的综合评分")

    col1, col2 = st.columns([2, 1])

    with col1:
        stock_input = st.text_input(
            "输入股票代码或名称",
            value=st.session_state.get("selected_stock", "600519"),
            placeholder="例如: 600519 或 贵州茅台",
        )

    with col2:
        analyze_btn = st.button("🔍 开始分析", type="primary", use_container_width=True)

    if analyze_btn and stock_input:
        with st.spinner("正在分析..."):
            try:
                service = st.session_state.service

                # 获取AI评分
                score_result = service.get_ai_score(stock_input, stock_input)

                if score_result:
                    render_score_result(score_result)

                    # 获取评分解释
                    explanation = service.get_score_explanation(stock_input, stock_input)
                    if explanation:
                        render_explanation(explanation)
                else:
                    st.warning("未找到该股票的数据，请检查股票代码是否正确")
                    st.info("提示：请输入6位数字的股票代码，如 600519（贵州茅台）")
            except Exception as e:
                error_msg = str(e)
                if "无效的股票代码" in error_msg:
                    st.error(f"❌ {error_msg}")
                    st.info("💡 提示：A股代码为6位数字，如 600519、000001、300750")
                elif "数据源错误" in error_msg or "获取" in error_msg:
                    st.error(f"❌ 数据获取失败: {error_msg}")
                    st.info("💡 建议：请稍后重试，或检查网络连接")
                else:
                    st.error(f"❌ 分析失败: {error_msg}")
                    st.info("💡 如问题持续，请联系技术支持")


def render_score_result(score_result):
    """渲染评分结果"""
    st.markdown("---")

    # 主评分展示
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        score_color = (
            "green"
            if score_result.ai_score >= 7
            else "orange" if score_result.ai_score >= 5 else "red"
        )
        st.metric(
            "AI综合评分",
            f"{score_result.ai_score}/10",
            delta=score_result.signal,
            delta_color="normal" if score_result.ai_score >= 5 else "inverse",
        )

    with col2:
        st.metric("跑赢市场概率", f"{score_result.beat_market_probability*100:.0f}%")

    with col3:
        st.metric("置信度", f"{score_result.confidence*100:.0f}%")

    with col4:
        signal_emoji = {
            "Strong Buy": "🚀",
            "Buy": "📈",
            "Hold": "➡️",
            "Sell": "📉",
            "Strong Sell": "⚠️",
        }
        st.metric("买卖信号", f"{signal_emoji.get(score_result.signal, '')} {score_result.signal}")

    # 分项评分
    st.markdown("### 📊 分项评分")

    dimension_names = {
        "technical": ("技术面", "📈"),
        "fundamental": ("基本面", "📋"),
        "fund_flow": ("资金面", "💰"),
        "sentiment": ("情绪面", "😊"),
        "risk": ("风险", "⚠️"),
    }

    cols = st.columns(5)
    for i, (name, data) in enumerate(score_result.subscores.items()):
        dim_name, emoji = dimension_names.get(name, (name, "📊"))
        with cols[i]:
            score = data.get("score", 5)
            weight = data.get("weight", 0.2)
            st.metric(f"{emoji} {dim_name}", f"{score:.1f}", delta=f"权重{int(weight*100)}%")

    # 风险提示
    if score_result.risks:
        st.markdown("### ⚠️ 风险提示")
        for risk in score_result.risks:
            st.warning(risk)


def render_explanation(explanation):
    """渲染评分解释"""
    st.markdown("### 💡 评分解释")

    # 摘要
    st.info(explanation.summary)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### ✅ 利好因素")
        if explanation.top_positive_factors:
            for f in explanation.top_positive_factors:
                st.success(f"**{f.description}** (贡献 +{f.score_contribution})")
        else:
            st.caption("暂无明显利好因素")

    with col2:
        st.markdown("#### ⚠️ 风险因素")
        if explanation.top_negative_factors:
            for f in explanation.top_negative_factors:
                st.error(f"**{f.description}** (影响 {f.score_contribution})")
        else:
            st.caption("暂无明显风险因素")

    # 投资建议
    if explanation.suggestions:
        st.markdown("#### 📝 投资建议")
        for s in explanation.suggestions:
            st.markdown(f"- {s}")


def render_technical_page():
    """技术分析页面"""
    st.title("📊 技术指标分析")

    stock_input = st.text_input(
        "输入股票代码", value=st.session_state.get("selected_stock", "600519")
    )

    if st.button("计算指标", type="primary"):
        with st.spinner("计算中..."):
            try:
                service = st.session_state.service
                indicators = service.calculate_indicators(stock_input)

                if indicators:
                    render_indicators(indicators)
                else:
                    st.warning("未找到该股票的历史数据")
                    st.info("💡 提示：请确认股票代码正确，且该股票有足够的交易历史")
            except Exception as e:
                error_msg = str(e)
                if "无效的股票代码" in error_msg:
                    st.error(f"❌ {error_msg}")
                    st.info("💡 提示：A股代码为6位数字，如 600519、000001、300750")
                elif "计算失败" in error_msg or "历史数据" in error_msg:
                    st.error(f"❌ 指标计算失败: {error_msg}")
                    st.info("💡 建议：该股票可能缺少足够的历史数据")
                else:
                    st.error(f"❌ 计算失败: {error_msg}")


def render_indicators(indicators):
    """渲染技术指标"""
    st.markdown("---")

    # 价格信息
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("当前价格", f"¥{indicators.get('close', 0):.2f}")
    with col2:
        change = indicators.get("price_change", 0) * 100
        st.metric("涨跌幅", f"{change:+.2f}%", delta_color="normal" if change >= 0 else "inverse")
    with col3:
        st.metric("量比", f"{indicators.get('volume_ratio', 1):.2f}")

    # 均线系统
    st.markdown("### 📈 均线系统")
    ma_data = {
        "指标": ["MA5", "MA10", "MA20", "MA60"],
        "数值": [
            indicators.get("ma5", "-"),
            indicators.get("ma10", "-"),
            indicators.get("ma20", "-"),
            indicators.get("ma60", "-"),
        ],
    }
    st.dataframe(pd.DataFrame(ma_data), use_container_width=True)

    # MACD
    st.markdown("### 📊 MACD")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("DIF", f"{indicators.get('macd_dif', 0):.3f}")
    with col2:
        st.metric("DEA", f"{indicators.get('macd_dea', 0):.3f}")
    with col3:
        hist = indicators.get("macd_hist", 0)
        st.metric("柱状图", f"{hist:.3f}", delta="多头" if hist > 0 else "空头")

    # RSI & KDJ
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### RSI")
        rsi = indicators.get("rsi", 50)
        st.metric("RSI(14)", f"{rsi:.1f}")
        if rsi > 70:
            st.warning("超买区域")
        elif rsi < 30:
            st.success("超卖区域")

    with col2:
        st.markdown("### KDJ")
        st.metric("K", f"{indicators.get('kdj_k', 50):.1f}")
        st.metric("D", f"{indicators.get('kdj_d', 50):.1f}")
        st.metric("J", f"{indicators.get('kdj_j', 50):.1f}")


def render_nlp_page():
    """智能问答页面"""
    st.title("💬 智能问答")
    st.markdown("用自然语言提问，AI帮你分析")

    # 示例查询
    st.markdown("#### 💡 试试这些问题:")
    example_queries = [
        "分析贵州茅台",
        "找出PE低于20的股票",
        "茅台的PE是多少",
        "推荐几只消费股",
    ]

    cols = st.columns(4)
    for i, query in enumerate(example_queries):
        with cols[i]:
            if st.button(query, key=f"example_{i}"):
                st.session_state.nlp_query = query

    # 查询输入
    query = st.text_input(
        "输入你的问题",
        value=st.session_state.get("nlp_query", ""),
        placeholder="例如: 分析贵州茅台的基本面",
    )

    if st.button("🔍 查询", type="primary") and query:
        with st.spinner("分析中..."):
            # 解析意图
            intent = st.session_state.intent_parser.parse(query)

            # 显示解析结果
            st.markdown("---")
            st.markdown("#### 🎯 意图识别")
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"识别意图: **{intent.intent_type.value}**")
            with col2:
                st.info(f"置信度: **{intent.confidence*100:.0f}%**")

            if intent.entities.get("stock_codes"):
                st.success(f"识别股票: {', '.join(intent.entities['stock_codes'])}")

            # 执行查询
            result = st.session_state.query_executor.execute(intent)

            st.markdown("#### 📝 查询结果")
            if result.success:
                st.success(result.message)
                if result.data:
                    if isinstance(result.data, dict):
                        if "results" in result.data:
                            st.dataframe(pd.DataFrame(result.data["results"]))
                        elif "summary" in result.data:
                            st.markdown(result.data["summary"])
            else:
                st.error(result.message)

            if result.suggestions:
                st.markdown("#### 💡 建议")
                for s in result.suggestions:
                    st.markdown(f"- {s}")


def render_screening_page():
    """批量筛选页面"""
    st.title("📋 批量筛选")
    st.markdown("批量计算多只股票的AI评分")

    # 输入股票列表
    stock_list = st.text_area(
        "输入股票代码（每行一个或逗号分隔）",
        value="600519\n000858\n000333\n601318\n600036",
        height=150,
    )

    col1, col2 = st.columns(2)
    with col1:
        top_n = st.number_input("显示前N只", min_value=5, max_value=50, value=10)
    with col2:
        sort_by = st.selectbox("排序方式", ["AI评分", "跑赢概率"])

    if st.button("🔍 开始筛选", type="primary"):
        # 解析股票代码
        codes = []
        for line in stock_list.replace(",", "\n").split("\n"):
            code = line.strip()
            if code:
                codes.append(code)

        if not codes:
            st.error("请输入有效的股票代码")
            return

        with st.spinner(f"正在分析 {len(codes)} 只股票..."):
            service = st.session_state.service
            results = service.batch_get_ai_scores(codes)

            if results:
                # 排序
                if sort_by == "AI评分":
                    results.sort(key=lambda x: x.ai_score, reverse=True)
                else:
                    results.sort(key=lambda x: x.beat_market_probability, reverse=True)

                # 显示结果
                st.markdown("---")
                st.markdown(f"### 📊 筛选结果 (共{len(results)}只)")

                # 转换为DataFrame
                df_data = []
                for r in results[:top_n]:
                    df_data.append(
                        {
                            "股票代码": r.stock_code,
                            "股票名称": r.stock_name,
                            "AI评分": r.ai_score,
                            "信号": r.signal,
                            "跑赢概率": f"{r.beat_market_probability*100:.0f}%",
                            "置信度": f"{r.confidence*100:.0f}%",
                        }
                    )

                st.dataframe(pd.DataFrame(df_data), use_container_width=True)
            else:
                st.error("筛选失败，请检查股票代码")


def render_portfolio_page():
    """组合管理页面"""
    st.title("💼 组合管理")
    st.markdown("管理持仓、跟踪收益、分析风险")

    portfolio = st.session_state.portfolio_service

    # 标签页
    tab1, tab2, tab3 = st.tabs(["📊 持仓概览", "➕ 添加持仓", "⚠️ 风险分析"])

    with tab1:
        # 获取组合摘要
        summary = portfolio.get_portfolio_summary()

        # 总览指标
        st.markdown("### 📈 组合总览")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("总市值", f"¥{summary.total_market_value:,.2f}")
        with col2:
            st.metric("总成本", f"¥{summary.total_cost:,.2f}")
        with col3:
            profit_color = "normal" if summary.total_profit_loss >= 0 else "inverse"
            st.metric(
                "总盈亏",
                f"¥{summary.total_profit_loss:,.2f}",
                delta=f"{summary.total_profit_loss_pct:+.2f}%",
                delta_color=profit_color
            )
        with col4:
            st.metric("持仓数量", f"{summary.position_count}只")

        # 持仓列表
        if summary.position_count > 0:
            st.markdown("### 📋 持仓明细")

            positions = portfolio.get_all_positions(update_prices=True)

            # 转换为DataFrame
            df_data = []
            for pos in positions:
                df_data.append({
                    "股票代码": pos.stock_code,
                    "股票名称": pos.stock_name,
                    "持仓数量": pos.quantity,
                    "成本价": f"¥{pos.cost_price:.2f}",
                    "当前价": f"¥{pos.current_price:.2f}",
                    "市值": f"¥{pos.market_value:,.2f}",
                    "盈亏": f"¥{pos.profit_loss:,.2f}",
                    "盈亏比例": f"{pos.profit_loss_pct:+.2f}%",
                    "仓位占比": f"{pos.weight:.1f}%",
                    "添加日期": pos.add_date,
                })

            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)

            # 删除持仓
            st.markdown("### 🗑️ 删除持仓")
            col1, col2 = st.columns([3, 1])

            with col1:
                stock_to_remove = st.selectbox(
                    "选择要删除的持仓",
                    [f"{pos.stock_code} - {pos.stock_name}" for pos in positions]
                )

            with col2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("删除", type="secondary", use_container_width=True):
                    stock_code = stock_to_remove.split(" - ")[0]
                    if portfolio.remove_position(stock_code):
                        st.success(f"已删除持仓: {stock_to_remove}")
                        st.rerun()
                    else:
                        st.error("删除失败")
        else:
            st.info("暂无持仓，请在「添加持仓」标签页添加")

    with tab2:
        st.markdown("### ➕ 添加新持仓")

        col1, col2 = st.columns(2)

        with col1:
            stock_code = st.text_input("股票代码", placeholder="例如: 600519")
            quantity = st.number_input("持仓数量", min_value=100, step=100, value=100)

        with col2:
            stock_name = st.text_input("股票名称", placeholder="例如: 贵州茅台")
            cost_price = st.number_input("成本价", min_value=0.01, step=0.01, value=100.0, format="%.2f")

        if st.button("添加持仓", type="primary", use_container_width=True):
            if stock_code and stock_name:
                try:
                    position = portfolio.add_position(stock_code, stock_name, quantity, cost_price)
                    st.success(f"成功添加持仓: {stock_name} ({stock_code})")
                    st.info(f"持仓数量: {position.quantity}, 成本价: ¥{position.cost_price:.2f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"添加失败: {str(e)}")
            else:
                st.warning("请填写完整的股票信息")

    with tab3:
        st.markdown("### ⚠️ 风险分析")

        if summary.position_count > 0:
            risk_analysis = portfolio.get_risk_analysis()

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("最大单仓占比", f"{risk_analysis['max_position_weight']:.1f}%")
            with col2:
                st.metric("持仓数量", f"{risk_analysis['position_count']}只")
            with col3:
                risk_color = {
                    "低": "🟢",
                    "中": "🟡",
                    "高": "🔴"
                }
                st.metric(
                    "风险等级",
                    f"{risk_color.get(risk_analysis['risk_level'], '')} {risk_analysis['risk_level']}"
                )

            # 风险建议
            st.markdown("### 💡 风险建议")
            for suggestion in risk_analysis['suggestions']:
                if "过高" in suggestion or "较多" in suggestion:
                    st.warning(suggestion)
                elif "较少" in suggestion:
                    st.info(suggestion)
                else:
                    st.success(suggestion)
        else:
            st.info("暂无持仓数据，无法进行风险分析")


def render_stock_screener_page():
    """选股雷达页面"""
    st.title("🔍 选股雷达")
    st.markdown("基于多维度条件筛选优质股票")

    # 策略选择
    st.markdown("### 📋 选择筛选策略")

    screener = st.session_state.screener_service
    preset_strategies = screener.get_preset_strategies()

    # 预设策略选项
    strategy_options = ["自定义条件"] + [s["name"] for s in preset_strategies.values()]
    selected_strategy = st.selectbox(
        "筛选策略",
        strategy_options,
        help="选择预设策略或自定义筛选条件"
    )

    # 显示策略说明
    if selected_strategy != "自定义条件":
        strategy_key = [k for k, v in preset_strategies.items() if v["name"] == selected_strategy][0]
        strategy_info = preset_strategies[strategy_key]
        st.info(f"📝 {strategy_info['description']} (包含{strategy_info['conditions_count']}个条件)")

    col1, col2 = st.columns([3, 1])

    with col1:
        limit = st.slider("返回结果数量", min_value=5, max_value=50, value=20)

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        screen_btn = st.button("🔍 开始筛选", type="primary", use_container_width=True)

    if screen_btn:
        with st.spinner("正在筛选股票..."):
            try:
                # 执行筛选
                if selected_strategy == "自定义条件":
                    # 使用默认AI高分策略
                    results = screener.screen_stocks("ai_high_score", limit=limit)
                else:
                    # 使用选中的预设策略
                    strategy_key = [k for k, v in preset_strategies.items() if v["name"] == selected_strategy][0]
                    results = screener.screen_stocks(strategy_key, limit=limit)

                if results:
                    st.markdown("---")
                    st.markdown(f"### 📊 筛选结果 (共{len(results)}只)")

                    # 转换为DataFrame
                    df_data = []
                    for stock in results:
                        df_data.append({
                            "股票代码": stock.get("stock_code", "-"),
                            "股票名称": stock.get("stock_name", "-"),
                            "AI评分": f"{stock.get('ai_score', 0):.1f}",
                            "信号": stock.get("signal", "-"),
                            "当前价": f"¥{stock.get('price', 0):.2f}",
                            "涨跌幅": f"{stock.get('change_pct', 0):+.2f}%",
                            "PE": f"{stock.get('pe', 0):.1f}",
                            "PB": f"{stock.get('pb', 0):.2f}",
                        })

                    df = pd.DataFrame(df_data)
                    st.dataframe(df, use_container_width=True)

                    # 详细信息展开
                    st.markdown("### 📈 详细分析")
                    selected_stock = st.selectbox(
                        "选择股票查看详情",
                        [f"{s['股票代码']} - {s['股票名称']}" for s in df_data]
                    )

                    if selected_stock:
                        stock_code = selected_stock.split(" - ")[0]
                        stock_detail = next((s for s in results if s.get("stock_code") == stock_code), None)

                        if stock_detail:
                            col1, col2, col3, col4 = st.columns(4)

                            with col1:
                                st.metric("技术面评分", f"{stock_detail.get('technical_score', 0):.1f}/10")
                            with col2:
                                st.metric("基本面评分", f"{stock_detail.get('fundamental_score', 0):.1f}/10")
                            with col3:
                                st.metric("资金面评分", f"{stock_detail.get('fund_flow_score', 0):.1f}/10")
                            with col4:
                                st.metric("市值", f"{stock_detail.get('market_cap', 0):.0f}亿")
                else:
                    st.warning("未找到符合条件的股票，请尝试调整筛选条件")

            except Exception as e:
                st.error(f"筛选失败: {str(e)}")

    # 策略说明
    with st.expander("📖 预设策略说明"):
        for key, info in preset_strategies.items():
            st.markdown(f"**{info['name']}**: {info['description']}")


def main():
    """主函数"""
    init_session_state()

    page = render_sidebar()

    if page == "🎯 AI评分":
        render_ai_score_page()
    elif page == "📊 技术分析":
        render_technical_page()
    elif page == "💬 智能问答":
        render_nlp_page()
    elif page == "📋 批量筛选":
        render_screening_page()
    elif page == "🔍 选股雷达":
        render_stock_screener_page()
    elif page == "💼 组合管理":
        render_portfolio_page()
    elif page == "📈 回测分析":
        render_backtest_page()


if __name__ == "__main__":
    main()
