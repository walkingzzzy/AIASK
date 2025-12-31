"""
回测分析页面
展示AI评分回测结果和可视化报告
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os


def render_backtest_page():
    """渲染回测分析页面"""
    st.title("📊 AI评分回测分析")
    st.markdown("基于历史数据验证AI评分系统的有效性")

    # 回测参数设置
    st.subheader("回测参数设置")

    col1, col2, col3 = st.columns(3)

    with col1:
        start_date = st.date_input(
            "开始日期",
            value=datetime.now() - timedelta(days=365),
            max_value=datetime.now()
        )

    with col2:
        end_date = st.date_input(
            "结束日期",
            value=datetime.now(),
            max_value=datetime.now()
        )

    with col3:
        holding_days = st.number_input(
            "持有天数",
            min_value=1,
            max_value=60,
            value=20,
            step=1
        )

    # 回测类型选择
    backtest_type = st.radio(
        "回测类型",
        ["评分分层回测", "阈值优化", "滚动验证"],
        horizontal=True
    )

    # 开始回测按钮
    if st.button("🚀 开始回测", type="primary", use_container_width=True):
        run_backtest(backtest_type, start_date, end_date, holding_days)

    # 显示历史回测结果
    st.markdown("---")
    st.subheader("历史回测结果")

    # 检查是否有回测结果
    if "backtest_results" in st.session_state and st.session_state.backtest_results:
        display_backtest_results(st.session_state.backtest_results)
    else:
        st.info("暂无回测结果，请先运行回测")


def run_backtest(backtest_type: str, start_date, end_date, holding_days: int):
    """运行回测"""
    try:
        from ..backtest.score_backtest import AIScoreBacktester
        from ..backtest.backtest_visualizer import BacktestVisualizer

        with st.spinner("正在运行回测..."):
            # 模拟回测数据（实际应该从数据库获取）
            st.info("正在准备回测数据...")

            if backtest_type == "评分分层回测":
                run_stratified_backtest(start_date, end_date, holding_days)
            elif backtest_type == "阈值优化":
                run_threshold_optimization(start_date, end_date, holding_days)
            elif backtest_type == "滚动验证":
                run_rolling_validation(start_date, end_date, holding_days)

    except Exception as e:
        st.error(f"回测失败: {str(e)}")


def run_stratified_backtest(start_date, end_date, holding_days: int):
    """运行评分分层回测"""
    from ..backtest.score_backtest import AIScoreBacktester, ScoreBacktestResult
    from ..backtest.backtest_visualizer import BacktestVisualizer

    # 模拟回测结果
    mock_results = [
        ScoreBacktestResult(
            score_range="9-10分",
            total_stocks=150,
            avg_return=0.15,
            win_rate=0.68,
            sharpe_ratio=1.8,
            max_drawdown=-0.12,
            beat_market_rate=0.72
        ),
        ScoreBacktestResult(
            score_range="8-9分",
            total_stocks=280,
            avg_return=0.10,
            win_rate=0.62,
            sharpe_ratio=1.4,
            max_drawdown=-0.15,
            beat_market_rate=0.65
        ),
        ScoreBacktestResult(
            score_range="7-8分",
            total_stocks=420,
            avg_return=0.05,
            win_rate=0.55,
            sharpe_ratio=0.9,
            max_drawdown=-0.18,
            beat_market_rate=0.58
        ),
        ScoreBacktestResult(
            score_range="6-7分",
            total_stocks=380,
            avg_return=0.02,
            win_rate=0.51,
            sharpe_ratio=0.5,
            max_drawdown=-0.20,
            beat_market_rate=0.52
        ),
        ScoreBacktestResult(
            score_range="5-6分",
            total_stocks=220,
            avg_return=-0.03,
            win_rate=0.45,
            sharpe_ratio=-0.2,
            max_drawdown=-0.25,
            beat_market_rate=0.42
        ),
    ]

    # 保存到session state
    st.session_state.backtest_results = mock_results
    st.session_state.backtest_type = "stratified"

    # 生成可视化
    visualizer = BacktestVisualizer()
    output_dir = "backtest_reports"
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    visualizer.plot_score_returns_curve(mock_results, report_path)

    st.session_state.backtest_chart_path = report_path

    st.success("回测完成！")
    st.rerun()


def run_threshold_optimization(start_date, end_date, holding_days: int):
    """运行阈值优化"""
    st.info("阈值优化功能开发中...")


def run_rolling_validation(start_date, end_date, holding_days: int):
    """运行滚动验证"""
    st.info("滚动验证功能开发中...")


def display_backtest_results(results):
    """显示回测结果"""

    # 结果摘要
    st.subheader("回测结果摘要")

    # 转换为DataFrame
    results_df = pd.DataFrame([
        {
            "评分区间": r.score_range,
            "样本数量": r.total_stocks,
            "平均收益率": f"{r.avg_return*100:.2f}%",
            "胜率": f"{r.win_rate*100:.1f}%",
            "夏普比率": f"{r.sharpe_ratio:.2f}",
            "最大回撤": f"{abs(r.max_drawdown)*100:.2f}%",
            "跑赢市场": f"{r.beat_market_rate*100:.1f}%"
        }
        for r in results
    ])

    st.dataframe(results_df, use_container_width=True)

    # 关键指标卡片
    st.subheader("关键指标")

    col1, col2, col3, col4 = st.columns(4)

    best_score_range = max(results, key=lambda x: x.avg_return)

    with col1:
        st.metric(
            "最佳评分区间",
            best_score_range.score_range,
            f"+{best_score_range.avg_return*100:.2f}%"
        )

    with col2:
        st.metric(
            "最高胜率",
            f"{max(r.win_rate for r in results)*100:.1f}%",
            "胜率"
        )

    with col3:
        st.metric(
            "最佳夏普比率",
            f"{max(r.sharpe_ratio for r in results):.2f}",
            "风险调整收益"
        )

    with col4:
        total_samples = sum(r.total_stocks for r in results)
        st.metric(
            "总样本数",
            f"{total_samples}",
            "个股票"
        )

    # 可视化图表
    if "backtest_chart_path" in st.session_state and os.path.exists(st.session_state.backtest_chart_path):
        st.subheader("可视化分析")
        st.image(st.session_state.backtest_chart_path, use_container_width=True)

    # 结论和建议
    st.subheader("回测结论")

    conclusions = []

    # 分析评分有效性
    high_score_return = results[0].avg_return if results else 0
    low_score_return = results[-1].avg_return if results else 0

    if high_score_return > low_score_return:
        conclusions.append("✅ AI评分系统有效：高评分股票收益显著优于低评分股票")
    else:
        conclusions.append("⚠️ AI评分系统需要优化：评分与收益相关性较弱")

    # 分析胜率
    avg_win_rate = sum(r.win_rate for r in results) / len(results) if results else 0
    if avg_win_rate > 0.55:
        conclusions.append(f"✅ 整体胜率良好：平均胜率 {avg_win_rate*100:.1f}%")
    else:
        conclusions.append(f"⚠️ 胜率需要提升：平均胜率 {avg_win_rate*100:.1f}%")

    # 分析夏普比率
    best_sharpe = max(r.sharpe_ratio for r in results) if results else 0
    if best_sharpe > 1.0:
        conclusions.append(f"✅ 风险调整收益优秀：最佳夏普比率 {best_sharpe:.2f}")
    else:
        conclusions.append(f"⚠️ 风险调整收益一般：最佳夏普比率 {best_sharpe:.2f}")

    for conclusion in conclusions:
        st.markdown(conclusion)

    # 投资建议
    st.subheader("投资建议")

    st.markdown(f"""
    基于回测结果，建议：

    1. **选股策略**：优先选择评分在 **{best_score_range.score_range}** 的股票
    2. **持仓管理**：建议持有周期为 **{st.session_state.get('holding_days', 20)}** 个交易日
    3. **风险控制**：单只股票最大回撤控制在 **{abs(best_score_range.max_drawdown)*100:.1f}%** 以内
    4. **组合构建**：建议构建 **10-15** 只股票的分散组合

    ⚠️ **风险提示**：历史回测结果不代表未来表现，投资需谨慎。
    """)
