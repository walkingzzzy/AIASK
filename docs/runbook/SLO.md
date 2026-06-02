# AIASK SLO 与上线门禁

> 解决就绪评审 P1-4（SLO/告警缺统一）与"上线就绪度矩阵 / 上线门禁"落地。
> 配套监控配置见 `monitoring/`，运维步骤见 `docs/runbook/AIASK_OPERATIONS_RUNBOOK.md`。

最后更新：2026-05-29

---

## 1. 服务级目标（SLO）

| 服务 | 指标 | 目标 | 数据来源 |
| --- | --- | --- | --- |
| Agent HTTP | `/health` 探针成功率 | ≥ 99%（受限运行期内） | `monitoring/blackbox.yml` + `agent-readiness.rules.yml` |
| Agent HTTP | `/health/detailed` 成功率 | ≥ 99% | 同上 |
| Agent HTTP | `/v1/responses` p95 延迟 | ≤ 30s（含模型调用） | OTEL（`otel-collector-config.yml`） |
| 数据就绪 | 关键表 freshness 通过率 | 100% 关键表有显式 freshness/fallback 标注 | `check_freshness` / `/v1/financial-system/readiness` |
| SQLite | 运营表（task_runs/experiments/domain_events）增长 | 各表保留期内有界，retention 定期跑 | `scripts/ops/db_retention.py` |
| SQLite | 单行大对象 | ≤ 256 KB | `scripts/ops/db_soak.py` + `bounded_json_text` |
| SQLite | 行情仓库（kline_1d 等） | 按行情仓库独立容量规划（非 100MB） | `scripts/ops/db_soak.py` |
| 策略工厂 | dry-run 单周期可重复通过 | 100% | `run_strategy_factory.py --once` |

---

## 2. 告警映射

| 告警 | 规则文件 | severity | 触发 |
| --- | --- | --- | --- |
| `AiaskAgentHealthProbeFailed` | `monitoring/alerts/agent-readiness.rules.yml` | critical | `/health` 探针 2m 失败 |
| `AiaskAgentDetailedHealthProbeFailed` | 同上 | warning | `/health/detailed` 5m 失败 |

> 待补充告警（建议）：DB size 超阈、freshness gate 失败、工厂断路器 open、ActionIntent 失败率。

---

## 3. 上线门禁清单（与就绪评审一致）

| 门禁 | 最小验收 | 当前状态（2026-05-29） |
| --- | --- | --- |
| CI 自动化 | push/PR 自动跑 test-agent/test-finance/desktop/边界/漂移 | ✅ 已建 `.github/workflows/ci.yml`（待首次远端执行验证） |
| Agent registry policy | 所有 model-visible 工具 `agent_*`，无 forbidden manager token | ✅ 由 `tools/policy.py` + 现有测试保证 |
| Endpoint drift | 无未解释 server-only/desktop-only | ✅ `check_endpoint_drift.py` 0 未解释 |
| 包边界 | strategy-factory 不依赖 akshare-mcp / 不触 live trading | ✅ decoupling + no-live-trading 守门测试通过 |
| Data freshness | 关键表 freshness/placeholder/fallback 可见 | ⏳ 工具已具备，UI/API 全量门禁待收敛（P0-3） |
| Strategy Factory dry-run | 短模式可重复通过 + 质量门禁证据 | ⏳ 待 stage 回归 |
| DB soak | 运营表保留期内有界；单行 < 256 KB；行情库独立核算 | ⚠️ **根因已澄清**：3.2GB 主体是 `kline_1d` 合法行情（非膨胀）；运营表当前在保留窗口内（deletable=0）。已交付 `db_retention.py`（dry-run 默认）+ `db_soak.py`；需将 retention 接入常驻定期运行 |
| Live trading negative | 缺/错 token 全部拒绝并有 trade_risk envelope | ✅ 单元覆盖（`test_trade_guard.py`） |
| Broker sandbox positive | 仅 sandbox 正确 token 通过且有审计 | ❌ 需券商沙箱账号，端到端未做（P0-2） |

图例：✅ 已落地可验证 / ⏳ 能力具备待回归 / ❌ 未通过或需外部条件。

---

## 4. 受限上线准入（必须全部满足）

1. live order 默认禁用，且 negative 测试通过。
2. CI 在目标分支跑绿。
3. endpoint drift 0 未解释。
4. 数据 freshness 在 UI/API 可见。
5. 策略工厂限 dry-run/paper。
6. DB soak 至少跑过一次并记录（即使现状不达标，也要有数据与治理计划）。

> 无约束生产与真实交易暂不开放，需单独审批 + sandbox/小额度受控账户验证。
