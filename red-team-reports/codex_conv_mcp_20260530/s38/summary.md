# N38 · 数据同步与新鲜度

**工具**: data_sync_manager / check_db_freshness / sync_stale_klines / sync_kline_data / batch_sync_klines / sync_trading_calendar / get_sync_status
**调用**: 30 次 · **结论**: pass_with_high_finding

## 覆盖
- data_sync_manager：help/status/list_tasks/get_task/cancel_task/list_schedules/schedule/cancel_schedule/run_due_schedules/非法 action
- check_db_freshness：核心标的 × max_stale(5/2/0) + 非法码 + 全市场扫描
- sync_kline_data(cache/api) / sync_stale_klines / batch_sync_klines / sync_trading_calendar / get_sync_status

## 关键发现
| ID | 级别 | 摘要 |
|---|---|---|
| F-N38-1 | **high** | codes 字段双重/多重 JSON 序列化污染：kline 表出现 `["600519"]` 作股票代码，任务 codes=`["[]"]`/`["[\"600519\"]"]` |
| F-N38-2 | **high** | data_sync_manager(schedule) 创建调度报 `no such function: array_to_string`(PostgreSQL 语法用在 SQLite) |
| F-N38-4 | medium | quote_snapshot freshness_ttl=30 秒导致周末/盘后全市场 5525 只误判 stale |
| F-N38-3 | low | cancel_task/cancel_schedule 取消不存在对象返回成功(虚假幂等) |
| F-N38-5 | low | 600519 05-29 change_pct=-4.25% 与收盘价环比(+3.92%)方向矛盾 |

## 正向能力
- **★★ data_sync_manager(status) 信息极丰富**：market_aux + quote_snapshot + critical_table_stale_alerts(主动暴露 north_fund 652 天/dragon_tiger no_data) + 告警分级。
- **★★ check_db_freshness 准确**：fresh/stale/missing 三分类，staleness 精确，非法码整批拒绝。
- **★★ 同步真实可用**：sync_stale_klines(300750 staleness 10→1 拉 250 根)、batch_sync、sync_kline_data(api/cache)。
- **★ sync_trading_calendar 准确**(95 交易日)；get_sync_status 含 dead-letter 追踪。
- 边界优雅：非法 action/非法码/不存在任务友好处理。

## standing caveat
周末非交易但 tqcenter/api 对部分标的可同步；quote_snapshot TTL=30 秒导致周末全市场 stale；核心 8 标的 + 指数日 K 新鲜(05-29)。
