# AIASK 运维 Runbook（统一入口）

> 解决就绪评审 P1-4（运行观测/runbook 不统一）、P2-1（文档状态分散）、P2-5（root runners 易被误当产品 API）。
> 本文是 AIASK 的单一运维入口：启动、健康、安全默认值、工厂操作、soak/门禁、故障恢复。

最后更新：2026-05-29

---

## 0. 上线口径（必须先读）

AIASK 当前定位为**本地/内网受限运行**：只读研究、dry-run、paper/sandbox、人工确认的 ActionIntent。

- ❌ 默认不开启真实交易（live order）。
- ❌ 不在无约束生产环境跑常驻工厂写流程。
- ✅ 允许：只读分析、数据门禁、paper observation、dry-run 工厂周期、人工确认意图。

风险全集见 `docs/architecture/AIASK_OVERALL_READINESS_REVIEW_2026-05-29.md`。

---

## 1. 服务启动与健康

### 1.1 Agent HTTP（控制面，模型可见面）

```bash
make bootstrap                  # uv sync + npm install（首次）
cd packages/agent && uv run aiask-agent --host 127.0.0.1 --port 8767
```

健康检查：

```bash
make smoke                      # curl /health
curl -fsS http://127.0.0.1:8767/health/detailed   # parity / hermes / readiness 摘要
curl -fsS http://127.0.0.1:8767/v1/financial-system/readiness
```

| 端点 | 用途 |
| --- | --- |
| `GET /health` | 存活探针 |
| `GET /health/detailed` | parity / hermes / readiness 综合 |
| `GET /v1/financial-system/readiness` | 数据库 / 索引 / 子项就绪度 |
| `GET /v1/capabilities/parity` | Hermes 对等矩阵 |

### 1.2 Desktop 工作台

```bash
cd desktop && npm run dev       # 开发（请在本地终端手动运行，不要在自动化里跑常驻）
cd desktop && npm run build     # 产物构建
```

Desktop 只消费 Agent HTTP API，不直连 MCP/manager。

---

## 2. Root runners 安全默认值（P2-5）

> ⚠️ 根目录 `run_*.py` 是**运维入口，不是产品 API**。生产/共享环境务必默认短模式，避免误启动长跑或写流程。

| Runner | 安全默认（推荐） | 危险（需确认） |
| --- | --- | --- |
| `run_strategy_factory.py` | `--once`（单周期）或 `--status` | 无参常驻（默认 10s 间隔长跑） |
| `run_factor_mining_factory.py` | `--once` / `--status` / `--maintenance` | 无参 schedule 常驻 |
| `run_incubation_factory.py` | `--dry-run` / `--status` / `--once` | `--daemon` 常驻写 paper |
| `run_signal_tracker.py` | `--status` | 常驻 |
| `run_all_factories.py` | 不在生产用 | 一次拉起三工厂常驻 |

约定：

- 默认 `--once` / `--status` / `--dry-run`，确认无误后再考虑常驻。
- 常驻进程必须在受控主机、带监控、带告警的前提下运行。
- 任何写流程（真实下单、批量写库）走 ActionIntent 人工确认。

---

## 3. 工厂操作

### 3.1 策略工厂

```bash
python run_strategy_factory.py --once
python run_strategy_factory.py --once --codes 600519 000001
# 通过 Agent/MCP：strategy_manager(action="factory_run_once" | "factory_status" | "factory_runs")
```

策略工厂终点是**生成/记录候选 + 质检**，不下实盘单（P0-4 边界，由
`packages/strategy-factory/tests/test_no_live_trading_boundary.py` 守门）。

### 3.2 因子挖掘工厂

```bash
python run_factor_mining_factory.py --once          # 单次挖掘
python run_factor_mining_factory.py --maintenance   # 衰减检测 + 自动退役
python run_factor_mining_factory.py --status
```

质量档位（数据稀疏期）：`AKSHARE_QUALITY_PROFILE=strict|lite|minimum`（默认 strict，
生产禁用 minimum）。

### 3.3 孵化工厂

```bash
cd packages/akshare-mcp
make incubation-factory-dry-run      # 推荐先 dry-run
make incubation-factory-status
make incubation-factory              # 单次
```

孵化只驱动 **paper** 交易（paper_orders / paper_trading_manager），
`evaluate_promotion()` 仅产出晋级资格判定，不自动上实盘。

### 3.4 定期维护（建议随常驻调度）

```bash
# 运营表保留期裁剪（dry-run 默认；--apply 前自动 gzip 备份）
python scripts/ops/db_retention.py            # 看可裁剪量
python scripts/ops/db_retention.py --apply    # 执行裁剪 + incremental_vacuum
```

建议把 `--apply` 接入工厂常驻的低峰维护窗口（如每日 06:00 维护周期），
防止 `strategy_task_runs` / `strategy_generation_experiments` / `strategy_domain_events`
的 JSON 日志长期累积。详见 §6。

---

## 4. 真实交易边界（P0-2）

- finance-mcp 下单/撤单：`live_trading_manager` 默认 `dry_run=true`；`execute=true`
  必须带 `confirm_token`，工具内校验并写 `audit_event`。
- finance-mcp-servers 共享守卫 `_shared/trade_guard.py`：缺 token / 错 token →
  `TRADE_RISK_TOKEN_REQUIRED` 拒绝 envelope（`explicit_token_required=True`）。
- 单元负向测试已覆盖：`packages/finance-mcp-servers/tests/test_trade_guard.py`。
- **仍缺**：真实 broker sandbox 端到端（需券商沙箱账号），见 `docs/runbook/SLO.md` 门禁表。

上线 live 交易前必须：在 sandbox 跑缺 token / 错 token / 正确 token 全链路，且每次下单有完整审计。

---

## 5. 数据门禁与质量

```bash
# 数据新鲜度（akshare-mcp 工具）：check_freshness / ensure_fresh_klines
python scripts/probe_event_driven_data_readiness.py
cd packages/akshare-mcp && python scripts/check_db_status.py
```

关键表的 freshness / placeholder / fallback / 不可得字段必须在 API/UI 可见（P0-3）。

---

## 6. DB Soak / 膨胀门禁（P1-5）

### 6.1 根因（2026-05-29 实测剖析）

对现库做了表级体积剖析，结论与最初"100MB 目标"不同，必须分开看：

| 来源 | 体量 | 性质 |
| --- | --- | --- |
| `kline_1d`（约 870 万行） | 占 3.2GB 主体 | **合法行情数据仓库**，不是垃圾，不应删 |
| `strategy_task_runs`（~1.8 万行） | ~308 MB | 运行日志 JSON（`result` 单行可达 63KB） |
| `strategy_generation_experiments`（~8.8千行） | ~281 MB | 实验记录 JSON |
| `strategy_domain_events`（~7.7千行） | ~87 MB | 事件 payload |
| freelist | ~3 MB | 碎片极少，**VACUUM 几乎收不回空间** |

修正结论：
- 旧的"单库 < 100MB"门禁对一个**全市场行情仓库**不成立，应改为"运营表有界 + 行情表单独核算"。
- 真正可治理的是运营/实验/事件三张表的**无界 JSON 日志增长**，不是碎片，所以正确手段是**保留期裁剪（retention）**而非 VACUUM。
- 字段级大 payload 已有 `bounded_json_text` 上限保护（`strategy_factory_json_budget.py`）。

### 6.2 保留期裁剪工具（dry-run 默认）

```bash
# 1) 先 dry-run 看可裁剪量（不删任何数据）
python scripts/ops/db_retention.py

# 2) 确认后执行（删除前自动写 gzip 备份到 data/backups/，再 incremental_vacuum）
python scripts/ops/db_retention.py --apply

# 单表 + 自定义窗口
python scripts/ops/db_retention.py --table strategy_task_runs --days 30 --apply
```

默认保留策略：`strategy_task_runs` 45 天/至少留 2000 行；
`strategy_generation_experiments` 60 天/2000 行；`strategy_domain_events` 60 天/5000 行。
行情/参考表（`kline_1d` 等）在硬 allowlist 外，工具会拒绝操作。

> 现状（2026-05-29）：三张运营表数据都还在保留窗口内（dry-run deletable=0），
> 说明当前体量是"近期工作数据"而非陈旧日志；3.2GB 主因是 `kline_1d` 行情。
> 因此上线前的动作是：(a) 把 SLO 改成分表门禁；(b) 让 retention 随工厂常驻定期跑，
> 防止运营表长期累积；(c) 行情库按"行情仓库"独立容量规划。

### 6.3 旁路 soak 监控

```bash
# 工厂/孵化负载运行时，旁路只读监控运营表体积与大行：
python scripts/ops/db_soak.py \
  --db data/db/akshare_mcp.sqlite3 \
  --duration-min 360 --interval-sec 300 \
  --max-db-mb 4096 --max-row-kb 256 \
  --out reports/ops/db_soak_20260529.json
```

> soak 的 `--max-db-mb` 现已不再用 100，应按"行情仓库 + 运营表预算"设阈（示例 4096）。
> 真正要盯的是 `--max-row-kb`（单行大对象）和运营表增长斜率。

---

## 7. 观测与告警

监控配置位于 `monitoring/`：

| 文件 | 作用 |
| --- | --- |
| `monitoring/prometheus.yml` | 抓取配置 |
| `monitoring/blackbox.yml` | health 探针 |
| `monitoring/alertmanager.yml` | 告警路由 |
| `monitoring/otel-collector-config.yml` | trace/metric 采集 |
| `monitoring/alerts/agent-readiness.rules.yml` | Agent health 告警规则 |

SLO 与告警映射见 `docs/runbook/SLO.md`。

---

## 8. CI / 验收门禁（P0-1）

CI：`.github/workflows/ci.yml`（GitHub Actions）在 push/PR 上运行：

- `make test-agent`、`make test-finance`
- Desktop `npm test` + `typecheck` + `build`
- 包边界守门 + 端点漂移门禁

本地完整验收：

```bash
make test-agent
make test-finance
cd desktop && npm test && npm run typecheck && npm run build
python scripts/code_graph/check_endpoint_drift.py
python scripts/code_graph/build_aiask_code_graph.py   # 图谱重建
```

---

## 9. 故障恢复

| 症状 | 处置 |
| --- | --- |
| Agent /health 失败 | 查进程与端口 8767；看 `data/logs/`；重启 `aiask-agent` |
| 工厂常驻卡死/异常 | 切短模式 `--status` 排查；断路器 `STRATEGY_FACTORY_MAX_CONSECUTIVE_FAILURES`（默认 5）会自动 open + backoff |
| DB 膨胀 | 跑 §6 soak 定位大行/大表；按 §6 治理；勿在生产直接 VACUUM 大库（会长时间锁库） |
| 端点漂移报警 | 跑 `check_endpoint_drift.py`；如为新增端点，更新 `reports/code-graph/endpoint-allowlist.json` 并说明分类 |
| live 下单被拒 | 预期行为：检查 `confirm_token` 与 `broker_token` 配置；拒绝即安全 |
| ActionIntent 卡在 awaiting_confirmation | Desktop 控制台确认/拒绝；超时（默认 24h）自动 expired |

---

## 10. 相关文档

- 就绪评审：`docs/architecture/AIASK_OVERALL_READINESS_REVIEW_2026-05-29.md`
- SLO/告警：`docs/runbook/SLO.md`
- 架构总览：`AGENT.md`
- 端点漂移 allowlist：`reports/code-graph/endpoint-allowlist.json`
