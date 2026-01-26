-- ============================================
-- 数据库优化脚本 (P1阶段)
-- 创建日期: 2026-01-25
-- 目标: 提升查询性能30-50%
-- ============================================

-- ============================================
-- 1. K线数据表索引优化
-- ============================================

-- 1.1 复合索引：按股票代码和时间查询（最常用）
CREATE INDEX IF NOT EXISTS idx_kline_1d_code_time 
ON kline_1d (code, time DESC);

-- 1.2 单独的代码索引（用于批量查询）
CREATE INDEX IF NOT EXISTS idx_kline_1d_code 
ON kline_1d (code);

-- 1.3 时间范围索引（用于市场整体分析）
CREATE INDEX IF NOT EXISTS idx_kline_1d_time 
ON kline_1d (time DESC);

-- 1.4 成交量索引（用于筛选活跃股票）
CREATE INDEX IF NOT EXISTS idx_kline_1d_volume 
ON kline_1d (volume DESC) WHERE volume > 0;

-- 1.5 涨跌幅索引（用于涨停板分析）
CREATE INDEX IF NOT EXISTS idx_kline_1d_change_pct 
ON kline_1d (change_pct DESC NULLS LAST) WHERE change_pct IS NOT NULL;

-- ============================================
-- 2. 财务数据表索引优化
-- ============================================

-- 2.1 复合索引：按股票代码和报告日期
CREATE INDEX IF NOT EXISTS idx_financials_code_date 
ON financials (code, report_date DESC);

-- 2.2 ROE索引（用于价值投资筛选）
CREATE INDEX IF NOT EXISTS idx_financials_roe 
ON financials (roe DESC NULLS LAST) WHERE roe IS NOT NULL;

-- 2.3 营收增长率索引
CREATE INDEX IF NOT EXISTS idx_financials_revenue_growth 
ON financials (revenue_growth DESC NULLS LAST) WHERE revenue_growth IS NOT NULL;

-- 2.4 利润增长率索引
CREATE INDEX IF NOT EXISTS idx_financials_profit_growth 
ON financials (profit_growth DESC NULLS LAST) WHERE profit_growth IS NOT NULL;

-- ============================================
-- 3. 股票信息表索引优化
-- ============================================

-- 3.1 股票名称全文搜索索引
CREATE INDEX IF NOT EXISTS idx_stocks_name_gin 
ON stocks USING gin(to_tsvector('simple', stock_name));

-- 3.2 行业索引
CREATE INDEX IF NOT EXISTS idx_stocks_industry 
ON stocks (industry) WHERE industry IS NOT NULL;

-- 3.3 市值索引
CREATE INDEX IF NOT EXISTS idx_stocks_market_cap 
ON stocks (market_cap DESC NULLS LAST) WHERE market_cap IS NOT NULL;

-- ============================================
-- 4. 持仓表索引优化
-- ============================================

-- 4.1 股票代码索引（已有UNIQUE约束，自动创建）
-- 4.2 更新时间索引（用于查询最近变动）
CREATE INDEX IF NOT EXISTS idx_positions_updated_at 
ON positions (updated_at DESC);

-- ============================================
-- 5. 自选股表索引优化
-- ============================================

-- 5.1 复合索引：分组和股票代码
CREATE INDEX IF NOT EXISTS idx_watchlist_group_code 
ON watchlist (group_id, stock_code);

-- 5.2 股票代码索引
CREATE INDEX IF NOT EXISTS idx_watchlist_code 
ON watchlist (stock_code);

-- ============================================
-- 6. 回测结果表索引优化
-- ============================================

-- 6.1 策略索引
CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy 
ON backtest_results (strategy);

-- 6.2 创建时间索引
CREATE INDEX IF NOT EXISTS idx_backtest_results_created_at 
ON backtest_results (created_at DESC);

-- 6.3 夏普比率索引（用于筛选优质策略）
CREATE INDEX IF NOT EXISTS idx_backtest_results_sharpe 
ON backtest_results (sharpe_ratio DESC NULLS LAST);

-- ============================================
-- 7. 回测交易表索引优化
-- ============================================

-- 7.1 复合索引：回测ID和日期
CREATE INDEX IF NOT EXISTS idx_backtest_trades_result_date 
ON backtest_trades (backtest_result_id, date DESC);

-- 7.2 股票代码索引
CREATE INDEX IF NOT EXISTS idx_backtest_trades_code 
ON backtest_trades (code);

-- ============================================
-- 8. 告警表索引优化
-- ============================================

-- 8.1 股票代码索引
CREATE INDEX IF NOT EXISTS idx_alerts_code 
ON alerts (code) WHERE code IS NOT NULL;

-- 8.2 告警类型索引
CREATE INDEX IF NOT EXISTS idx_alerts_type 
ON alerts (type);

-- 8.3 激活状态索引
CREATE INDEX IF NOT EXISTS idx_alerts_active 
ON alerts (active) WHERE active = true;

-- 8.4 创建时间索引
CREATE INDEX IF NOT EXISTS idx_alerts_created_at 
ON alerts (created_at DESC);

-- ============================================
-- 9. 告警历史表索引优化
-- ============================================

-- 9.1 复合索引：告警ID和触发时间
CREATE INDEX IF NOT EXISTS idx_alert_history_alert_time 
ON alert_history (alert_id, triggered_at DESC);

-- 9.2 触发时间索引
CREATE INDEX IF NOT EXISTS idx_alert_history_triggered_at 
ON alert_history (triggered_at DESC);

-- ============================================
-- 10. 向量嵌入表索引优化
-- ============================================

-- 10.1 股票代码索引（已有PRIMARY KEY）
-- 10.2 更新时间索引
CREATE INDEX IF NOT EXISTS idx_stock_embeddings_updated_at 
ON stock_embeddings (updated_at DESC);

-- ============================================
-- 11. 数据质量表索引优化
-- ============================================

-- 11.1 复合索引：股票代码和日期
CREATE INDEX IF NOT EXISTS idx_data_quality_code_date 
ON data_quality (stock_code, check_date DESC);

-- 11.2 质量分数索引
CREATE INDEX IF NOT EXISTS idx_data_quality_score 
ON data_quality (quality_score DESC);

-- ============================================
-- 12. 查询性能统计
-- ============================================

-- 启用查询统计扩展
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 创建慢查询日志表
CREATE TABLE IF NOT EXISTS slow_query_log (
    id              SERIAL PRIMARY KEY,
    query_text      TEXT NOT NULL,
    execution_time  DOUBLE PRECISION NOT NULL,
    rows_returned   INTEGER,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

-- 慢查询日志索引
CREATE INDEX IF NOT EXISTS idx_slow_query_log_time 
ON slow_query_log (execution_time DESC);

CREATE INDEX IF NOT EXISTS idx_slow_query_log_timestamp 
ON slow_query_log (timestamp DESC);

-- ============================================
-- 13. 分析和维护
-- ============================================

-- 更新表统计信息（提升查询计划质量）
ANALYZE kline_1d;
ANALYZE financials;
ANALYZE stocks;
ANALYZE positions;
ANALYZE watchlist;
ANALYZE backtest_results;
ANALYZE backtest_trades;
ANALYZE alerts;
ANALYZE alert_history;
ANALYZE stock_embeddings;
ANALYZE data_quality;

-- ============================================
-- 14. 查询优化建议
-- ============================================

-- 14.1 使用EXPLAIN ANALYZE查看查询计划
-- EXPLAIN ANALYZE SELECT * FROM kline_1d WHERE code = '600519' AND time >= '2023-01-01';

-- 14.2 查看最慢的查询
-- SELECT query, mean_exec_time, calls 
-- FROM pg_stat_statements 
-- ORDER BY mean_exec_time DESC 
-- LIMIT 10;

-- 14.3 查看索引使用情况
-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'public'
-- ORDER BY idx_scan DESC;

-- 14.4 查看表大小
-- SELECT 
--     schemaname,
--     tablename,
--     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================
-- 15. 定期维护任务
-- ============================================

-- 15.1 每周执行VACUUM ANALYZE（清理死元组，更新统计信息）
-- VACUUM ANALYZE kline_1d;
-- VACUUM ANALYZE financials;

-- 15.2 每月执行REINDEX（重建索引，提升性能）
-- REINDEX TABLE kline_1d;
-- REINDEX TABLE financials;

-- ============================================
-- 完成！
-- ============================================

-- 验证索引创建
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
