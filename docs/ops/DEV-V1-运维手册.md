# DEV-V1 运维手册

**策略工厂到孵化工厂过渡架构 — 一线运维参考**

最后更新: 2026-05-26
关联背景：根目录过渡架构方案与开发方案（根目录文档不属于 `docs/` 整理范围；若本地不存在，以当前运行脚本和代码为准）。

---

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 一站式运维脚本 `run_dev_v1_ops.py`](#2-一站式运维脚本-run_dev_v1_opspy)
- [3. .env 推荐配置](#3-env-推荐配置)
- [4. 标准日常运维流程](#4-标准日常运维流程)
- [5. 验收指标与红线告警](#5-验收指标与红线告警)
- [6. 故障排查](#6-故障排查)
- [7. 回滚预案](#7-回滚预案)
- [8. 关键概念速查](#8-关键概念速查)
- [9. 已知非阻塞问题](#9-已知非阻塞问题)
- [10. FAQ](#10-faq)

---

## 1. 快速开始

### 三句话理解 DEV-V1

1. **架构**: 把"D 级 + Gate-B passed"候选从被拒(`rejected`)改为走 observe lane,创建 paper 账户,让孵化工厂消费它们做前向验证
2. **toggle**: P0 (`STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED=1`) + P1 (`INCUBATION_FACTORY_PAPER_INTAKE_ENABLED=1`),已在 `.env` 持久化
3. **运维**: 用 `run_dev_v1_ops.py` 一站式跑 cycle / intake / 状态查询 / 回滚

### 5 分钟上手命令清单

```powershell
# 查当前状态(免参数)
python run_dev_v1_ops.py status

# 端到端逻辑验证(不修改 DB,5 秒内完成)
python run_dev_v1_ops.py verify

# 检查 .env toggle 是否符合 DEV-V1 推荐值
python run_dev_v1_ops.py check-toggles

# 跑一个完整流程(策略工厂 cycle + 孵化工厂 intake)
python run_dev_v1_ops.py full

# 出问题了回滚 .env
python run_dev_v1_ops.py rollback --target env
```

---

## 2. 一站式运维脚本 `run_dev_v1_ops.py`

位置: 仓库根目录 `run_dev_v1_ops.py`

### 子命令一览

| 子命令 | 作用 | 副作用 | 耗时 |
|---|---|---|---|
| `status` | 查 DEV-V1 完整状态(toggle + DB + 备份) | 无 | < 1s |
| `verify` | 端到端 5 步逻辑验证 | 无 | < 5s |
| `check-toggles` | 检查 .env 是否符合 DEV-V1 推荐值 | 无 | < 1s |
| `cycle` | 跑一次 strategy_factory cycle(产 quality_reports) | 写 DB | 6~12 分钟 |
| `intake` | 跑一次 IncubationFactoryRunner(消费 paper) | 写 DB | < 1s ~ 几秒 |
| `full` | 一站式: cycle + intake | 写 DB | 6~12 分钟 |
| `rollback` | 回滚 .env 或 DB 到 DEV-V1 落地前 | **修改文件** | < 1 分钟 |

### 详细说明

#### `status` — 状态总览

输出 6 块信息:
1. **.env Toggle 状态** — P0/P1/P3/产出密度参数生效值
2. **strategies 表 status 分布** — `rejected/draft/submitted/incubating` 各多少
3. **孵化账户(stage 分布)** — `warmup/paper/candidate/listed`
4. **quality_reports submission_lane 分布** — 验证 P0 是否触发(`observe_incubation` > 0)
5. **incubation* 事件分布** — 验证 P1 是否触发(`paper_observation_recognized` > 0)
6. **备份文件** — 可用的回滚源

#### `verify` — 端到端逻辑验证

不依赖生产 cycle,直接调用核心函数验证逻辑:
1. ✅ Toggle 解析(从 .env 真实加载)
2. ✅ P0 路径 ON: D + Gate-passed → eligible=True / reason='d_grade_observe_only_micro_budget'
3. ✅ P0 路径 OFF 对照: 验证老行为完全保留
4. ✅ P1 intake 路径: 三场景全测(toggle ON+无方法 / ON+有方法 / OFF)
5. ✅ P1 runner 路径: `_list_paper_observation` 真实查 db

#### `cycle` — 跑策略工厂 cycle

调用 `python run_strategy_factory.py --once`,日志写入 `data/logs/dev_v1_ops/cycle_<timestamp>.log`

```powershell
# 默认超时 25 分钟
python run_dev_v1_ops.py cycle

# 自定义超时
python run_dev_v1_ops.py cycle --timeout 1800
```

#### `intake` — 跑孵化工厂 intake

直接调 `IncubationFactoryRunner.run_once()`,验证 P1 完整链路。

```powershell
# 默认超时 5 分钟(实际通常 < 1 秒)
python run_dev_v1_ops.py intake

# 自定义超时
python run_dev_v1_ops.py intake --timeout 600
```

#### `full` — 一站式 cycle + intake

```powershell
python run_dev_v1_ops.py full
# 等同于:
# python run_dev_v1_ops.py cycle && python run_dev_v1_ops.py intake
```

#### `rollback` — 回滚

```powershell
# 仅回滚 .env(默认,把 DEV-V1 toggle 全部去掉)
python run_dev_v1_ops.py rollback --target env

# 回滚 DB(需要 --force 二次确认)
python run_dev_v1_ops.py rollback --target db --force

# 同时回滚 .env + DB(极端故障)
python run_dev_v1_ops.py rollback --target all --force
```

回滚保护:
- `.env` 回滚前会备份当前 `.env` 到 `.env.before_rollback_<timestamp>.bak`
- DB 回滚前会备份当前 DB 到 `data/db/akshare_mcp.before_rollback_<timestamp>.bak`
- DB 回滚必须 `--force`(防误操作)

#### `check-toggles` — 配置检查

逐项对比 .env 实际值与 DEV-V1 推荐值,不符合时显示 ⚠️ 并提示参考章节。

---

## 3. .env 推荐配置

### DEV-V1 完整推荐配置

```bash
# ─────────────────────────────────────────────────────
# Strategy Factory DEV-V1 Release Toggles (2026-05-26)
# ─────────────────────────────────────────────────────

# === P0: 允许 D 级 + Gate-passed 候选走 observe lane ===
STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED=1

# === P1: 孵化工厂消费 paper observation 候选 ===
INCUBATION_FACTORY_PAPER_INTAKE_ENABLED=1
INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT=10

# === P3: D→C 升级 family 集合扩展(暂不启用)===
# 启用方式: STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES=volatility_breakout

# === 产出密度参数(2026-05-26 调优)===
STRATEGY_LLM_MAX_CONCURRENCY=5                                # ⭐ 关键瓶颈
STRATEGY_FACTORY_RESEARCH_TASK_CONCURRENCY=5
STRATEGY_FACTORY_CANDIDATES_PER_TASK=6
STRATEGY_FACTORY_LLM_FAN_OUT_COUNT=3
STRATEGY_FACTORY_BACKTEST_CONCURRENCY=10
STRATEGY_FACTORY_BACKTEST_CODE_CONCURRENCY=8
STRATEGY_FACTORY_BULK_STOCK_MATRIX_MAX_TASKS_PER_RUN=8
STRATEGY_FACTORY_BULK_STOCK_MATRIX_MAX_CANDIDATES_PER_RUN=30
STRATEGY_FACTORY_BULK_STOCK_MATRIX_GENERATION_LIMIT_PER_TASK=3
STRATEGY_FACTORY_BULK_FAMILIES_PER_STOCK=5
STRATEGY_FACTORY_BULK_STOCK_MATRIX_FAMILIES_PER_STOCK=5
STRATEGY_FACTORY_BULK_CONCURRENCY=3

# === LLM staged 失败时回退 monolithic 路径 ===
STRATEGY_FACTORY_ALLOW_PIPELINE_EMPTY_MONOLITHIC_FALLBACK=1
```

### 参数硬上限参考(代码约束)

| 参数 | 推荐值 | 代码硬上限 |
|---|---|---|
| `STRATEGY_FACTORY_RESEARCH_TASK_CONCURRENCY` | 5 | 12 |
| `STRATEGY_FACTORY_CANDIDATES_PER_TASK` | 6 | 8 |
| `STRATEGY_FACTORY_LLM_FAN_OUT_COUNT` | 3 | 4 |
| `STRATEGY_FACTORY_BACKTEST_CONCURRENCY` | 10 | 10 |
| `STRATEGY_LLM_MAX_CONCURRENCY` | 5 | 无硬限,受 API 限速 |

### 关键发现:LLM 并发瓶颈

**`STRATEGY_LLM_MAX_CONCURRENCY` 是真正的产出瓶颈**。

代码 `_resolve_research_task_concurrency` 取 `min(RESEARCH_TASK_CONCURRENCY, llm_provider_limit)`,
即使 `RESEARCH_TASK_CONCURRENCY=5` 也会被 `STRATEGY_LLM_MAX_CONCURRENCY=1` 锁死为 1。

**修复**: 必须同时把 `STRATEGY_LLM_MAX_CONCURRENCY` 调到 5+。



---

## 4. 标准日常运维流程

### 4.1 首次启动(新环境)

```powershell
# 1. 确认 .env 配置正确
python run_dev_v1_ops.py check-toggles
# 期望: 8/8 ✅,如有 ⚠️ 需手动改 .env

# 2. 端到端逻辑验证
python run_dev_v1_ops.py verify
# 期望: 5/5 ✅

# 3. 查看初始状态
python run_dev_v1_ops.py status
# 关注: 备份文件是否就位、当前 paper 账户数

# 4. 跑首次完整流程
python run_dev_v1_ops.py full
```

### 4.2 日常每日运维

**推荐节奏**: 每天 1 次 cycle + intake,持续 7 天观察累积

```powershell
# 早晨/收盘后(18:30 默认)
python run_dev_v1_ops.py full

# 收盘后查看产出
python run_dev_v1_ops.py status
```

### 4.3 多次 cycle 累积(快速产出 paper 账户)

```powershell
# 跑 3 个 cycle 加速累积
for ($i=1; $i -le 3; $i++) {
    Write-Host "=== Cycle $i ==="
    python run_dev_v1_ops.py cycle
    Start-Sleep -Seconds 30
}

# 跑一次 intake 消费所有累积的 paper 账户
python run_dev_v1_ops.py intake

# 查看效果
python run_dev_v1_ops.py status
```

### 4.4 定时任务(Windows 任务计划)

可以创建 Windows 任务计划实现每日自动运维:

```powershell
# 创建每日 18:30 跑 full 流程的任务
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -Command `"Set-Location C:\Users\walking\Desktop\aiask; python run_dev_v1_ops.py full`""
$trigger = New-ScheduledTaskTrigger -Daily -At 18:30
Register-ScheduledTask -TaskName "DevV1-Daily-Full" -Action $action -Trigger $trigger
```

---

## 5. 验收指标与红线告警

### 5.1 验收指标(每周看一次)

| 指标 | 期望 | 查询方法 |
|---|---|---|
| `submission_lane='observe_incubation'` 累积 | ≥ 1/周 | `status` 第 4 块 |
| `paper_observation_recognized` 事件累积 | ≥ 1/周 | `status` 第 5 块 |
| `strategy_incubation_accounts` 增量 | ≥ 1/周 | `status` 第 3 块 |
| cycle 退出码 | 100% rc=0 | `data/logs/dev_v1_ops/cycle_*.err.log` |
| intake 状态 | `completed` + `phase_failures=[]` | `intake` 命令输出 |

### 5.2 红线告警(立即响应)

| 红线 | 阈值 | 响应 |
|---|---|---|
| **R1 cycle 异常退出** | rc != 0 | 查 `cycle_*.err.log`,排查后再开 |
| **R2 paper 账户激增** | 单 cycle Δ > 200 | 立即 `rollback --target env` |
| **R3 错误降级** | candidate/listed 阶段被降为 paper | 立即 `rollback --target env` + 查 SQL JOIN |
| **R4 intake 异常** | `phase_failures` 非空且非 ForwardVerifier 已知 bug | 排查后再跑 |
| **R5 P0 触发率为 0** | 连续 5 cycle 无新 `observe_incubation` 命中 | 查 LLM 是否正常 / `verify` 是否通过 |

### 5.3 健康检查清单

```powershell
# 完整健康检查(推荐每周跑一次)
python run_dev_v1_ops.py status
python run_dev_v1_ops.py verify
python run_dev_v1_ops.py check-toggles
```

---

## 6. 故障排查

### 6.1 cycle 跑 25 分钟超时

**症状**: `cycle 退出 elapsed=1500s rc=-15`

**可能原因**:
1. LLM API 限速 / 超时
2. 数据库锁(WAL 冲突)
3. backtest 数据不完整

**排查**:
```powershell
# 看最近 cycle 日志末尾
Get-Content data\logs\dev_v1_ops\cycle_*.err.log | Select-Object -Last 30

# 查 LLM 状态(直连 API)
# 用项目脚本测试
```

### 6.2 paper 账户长时间不增长

**症状**: 跑了 5+ cycle,`observe_incubation` 命中数还是 0

**可能原因**:
1. cycle 没产 D + Gate-passed 候选(数据巧合,需更多 cycle)
2. P0 toggle 没真正 ON(检查 `.env`)
3. LLM 路径全部 timeout

**排查**:
```powershell
# 1. 验证 toggle 真的 ON
python run_dev_v1_ops.py check-toggles
python run_dev_v1_ops.py verify

# 2. 看最近 cycle 的 grade 分布
python run_dev_v1_ops.py status
# 关注 quality_reports 中 grade='D' 的数量

# 3. 看 LLM 状态(从 strategy_factory_runs.summary)
# 如果 'skipped_timeout' > 'succeeded',LLM 性能不足
```

### 6.3 IncubationFactoryRunner 报 ForwardVerifier 错

**症状**: `intake` 输出中有 `ForwardVerifier: load evidence failed`

**说明**: 这是已知非阻塞 bug(`list_strategy_signal_evidence` 签名不匹配)。

**影响**: 无 — Phase 3 verification 仍正常完成,`phase_failures=[]`,paper 账户能正常被识别。

**修复**: 独立 PR 处理,不影响 DEV-V1 主线。

### 6.4 .env 修改后没生效

**症状**: 改了 `.env` 但 cycle 行为没变化

**原因**: `_load_dotenv()` 用 `setdefault`,如果某个 var **同名出现多次**,只取**第一次**;如果父进程已经设了同名 env var,会忽略 `.env` 的值。

**排查**:
```powershell
# 用工具脚本看实际生效值
python run_dev_v1_ops.py check-toggles
```

**修复**: 检查 `.env` 是否有重复定义,或父进程是否设了同名 env var。

---

## 7. 回滚预案

### 7.1 三级回滚

| 级别 | 命令 | 影响范围 | 数据丢失 |
|---|---|---|---|
| **L1** | `rollback --target env` | 只 .env(toggle 关闭) | 无 |
| **L2** | `rollback --target db --force` | DB 完全恢复 | 自 12:00 之后所有数据 |
| **L3** | `rollback --target all --force` | .env + DB 都恢复 | 同 L2 |

### 7.2 回滚后必做

1. **重启长期运行进程**(让新 .env 生效):
   ```powershell
   # 停掉 strategy_factory / incubation_factory 守护进程(如果有)
   # 重启相关服务
   ```

2. **验证回滚成功**:
   ```powershell
   python run_dev_v1_ops.py status
   python run_dev_v1_ops.py check-toggles
   ```

3. **记录回滚原因到决策日志**:
   ```powershell
   notepad data\reports\sf_dev_v1_decision_log.md
   ```

### 7.3 紧急人工回滚(脚本失效时)

```powershell
# .env 回滚
Copy-Item .env.pre_dev_v1.bak .env -Force

# DB 回滚
Copy-Item data\db\akshare_mcp.pre_dev_v1.bak data\db\akshare_mcp.sqlite3 -Force
```

---

## 8. 关键概念速查

### 8.1 Strategy Factory vs Incubation Factory

| 维度 | Strategy Factory | Incubation Factory |
|---|---|---|
| 入口 | `run_strategy_factory.py --once` | `run_incubation_factory.py --once` |
| 职责 | 策略生成(LLM/rule/local_rule) + Gate 0/1/2/3 评分 | 接纳新策略 + 信号生成 + 前向验证 + 命中率报告 |
| 写入表 | `strategy_quality_reports`, `strategies`, `strategy_generation_experiments` | `strategy_incubation_accounts`, `strategy_domain_events`(incubation*) |
| 默认运行时间 | 连续(每 5 分钟一次,可配) | 18:30 每日一次 |
| **DEV-V1 一站式** | **`run_dev_v1_ops.py cycle`** | **`run_dev_v1_ops.py intake`** |

### 8.2 P0 路径完整链路

```
LLM 生成 → quality_gate 评分
   ↓
quality_report (grade='D', gate_b='pass')
   ↓ STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED=1
   ↓ admission_authority._runtime_bootstrap_context
   ↓ runtime_bootstrap_eligible=True
   ↓ runtime_bootstrap_reason='d_grade_observe_only_micro_budget'
   ↓ submission_lane='observe_incubation'
   ↓
lifecycle_coordinator._enqueue_paper_observation
   ↓
strategy_incubation_accounts (stage='paper', status='active')
```

### 8.3 P1 路径完整链路

```
strategy_incubation_accounts (stage='paper')
   ↓
IncubationFactoryRunner.run_once()
   ↓ Phase 1: IncubationIntake.scan_and_accept(db)
   ↓ INCUBATION_FACTORY_PAPER_INTAKE_ENABLED=1
   ↓ db.list_paper_observation_strategies(limit=10)
   ↓
SQL JOIN strategies s ON a.strategy_id = s.id
WHERE s.status='submitted' AND a.stage='paper' AND a.status='active'
NOT EXISTS (a2.stage IN ('candidate', 'listed') AND a2.status='active')
   ↓ paper 候选列表
   ↓ 写入 incubation_factory.paper_observation_recognized 事件
   ↓ ensure_account(stage='warmup', source='incubation_factory_intake')
   ↓ stage 推进 paper → warmup
   ↓
Phase 2: 合并 incubating + paper → all_strategies
   ↓
Phase 3: 信号生成 + 前向验证
   ↓
Phase 4-8: pipeline_evaluation / 指标 / 命中率 / 反馈 / heartbeat
```

### 8.4 关键 toggle 默认值

| Toggle | 默认 | DEV-V1 推荐 | 含义 |
|---|---|---|---|
| `STRATEGY_FACTORY_OBSERVE_D_GRADE_ENABLED` | 0 | **1** | P0 D 级解封 |
| `INCUBATION_FACTORY_PAPER_INTAKE_ENABLED` | 0 | **1** | P1 孵化工厂消费 paper |
| `INCUBATION_FACTORY_PAPER_INTAKE_BATCH_LIMIT` | 50 | 10 | 每批最大数量 |
| `STRATEGY_FACTORY_TRADE_AWARE_EXTRA_FAMILIES` | (空) | (空,等 V5-PR-2) | P3 D→C 升级 family 扩展 |

---

## 9. 已知非阻塞问题

### 9.1 ForwardVerifier 接口签名不匹配

```
ForwardVerifier: load evidence failed for <strategy_id>:
StrategyIncubationMixin.list_strategy_signal_evidence() takes 1 positional
argument but 2 positional arguments (and 1 keyword-only argument) were given
```

- **影响**: 无,Phase 3 仍 `metrics_recorded=1` + `phase_failures=[]`
- **修复**: 独立 PR

### 9.2 LLM 部分 task 超时

```
research task <name> timed out after 120.0s (kind=external_llm_timeout)
```

- **现象**: 8 task 中 ~4 个超时
- **影响**: 无,rule-first fallback 兜底
- **缓解**: 调高 `STRATEGY_LLM_TIMEOUT_SEC=180`(默认 120)

### 9.3 cycle 总状态显示 `partial_infra`

- **原因**: snapshot_degraded(数据完整度 0.83 < 1.0)+ fear_greed 失败 + warmup_failed
- **影响**: 无,`autonomy_generated > 0` 说明产出正常
- **缓解**: V5 P3 工作流处理(独立)

---

## 10. FAQ

### Q1: 为什么我跑了 cycle,但 paper 账户没增加?

**A**: 不一定每个 cycle 都产 D + Gate-passed 候选。历史比例约 8.7%(171/1961),
所以平均每 11~12 个 cycle 才会触发一次 P0。
启用产出密度提升后(LLM 5x 并发),期望降到 1~2 cycle/触发。

跑 5+ 个 cycle 累积:
```powershell
for ($i=1; $i -le 5; $i++) { python run_dev_v1_ops.py cycle }
```

### Q2: `intake` 命令瞬间完成是正常的吗?

**A**: 是。如果 paper 账户列表为空(0 条 paper),整个 run_once 几百毫秒就完成。
跑过 1 次 intake 后,paper 候选会被推进到 `warmup` 阶段,此时再跑会显示 0 条 paper。

### Q3: 我能不能直接跑项目自带的 `run_strategy_factory.py` 而不用 `run_dev_v1_ops.py`?

**A**: 可以。`run_dev_v1_ops.py cycle` 实际上是调 `run_strategy_factory.py --once` 的 wrapper。
但 `run_dev_v1_ops.py` 提供:
- 自动日志归档(`data/logs/dev_v1_ops/`)
- 实时进度监控(每 30s 显示 err.log 增长)
- 超时控制 + 自动 terminate
- 与 status/verify/intake 配套

### Q4: P3 toggle 什么时候开?

**A**: 当前**保持默认 OFF**。等 V5-PR-2 数据验证完成后,按 Tier A/B 顺序灰度:
- **Tier B 优先**: `volatility_breakout`(占 48% 候选,优先)
- 然后: `value_factor` → `sector_rotation`
- 最后: `macro_timing / growth_factor / north_capital_track / event_structure_breakout`

详见架构方案 §16.5 + 开发方案 V5 P3 工作流深度调研。

### Q5: 决策日志在哪里?

**A**: `data/reports/sf_dev_v1_decision_log.md`,包含:
- 每次 toggle 启动的时间和原因
- 红线检查结果
- 每次 cycle/intake 的关键数据
- LLM 路径调研发现
- 产出密度提升前后对比

### Q6: 怎么验证 P0/P1 链路是否完整?

**A**:
```powershell
# 端到端 5 步验证(< 5 秒,不修改 DB)
python run_dev_v1_ops.py verify
```

5 步全 PASS = 链路完整,只待生产 cycle 自然触发。

### Q7: 我应该多频繁跑 intake?

**A**: 推荐:
- **生产**: 每天 1 次(默认 18:30)
- **测试期**: cycle 跑完后立即跑 intake 看效果
- **快速观察累积**: cycle × N 后跑 1 次 intake,集中处理

### Q8: 怎么停掉所有 DEV-V1 改动?

**A**:
```powershell
# L1: 只回滚 toggle(代码不动)
python run_dev_v1_ops.py rollback --target env

# 重启相关进程让新 .env 生效
```

DEV-V1 设计成完全 toggle 化,关掉 toggle 后行为完全等同于改前。

---

## 附录 A: 文件清单

### DEV-V1 相关文件

| 文件 | 类型 | 作用 |
|---|---|---|
| `run_dev_v1_ops.py` | 运维脚本 | 一站式 DEV-V1 运维 |
| `docs/ops/DEV-V1-运维手册.md` | 文档 | 本手册 |
| `策略工厂到孵化工厂过渡架构方案-2026-05-26.md` | 架构方案 | V4-network-p3 |
| `策略工厂到孵化工厂过渡-开发方案-2026-05-26.md` | 开发方案 | DEV-V1 + V5-PR-1 实施级 |
| `data/reports/sf_dev_v1_decision_log.md` | 决策日志 | 每次 toggle 启动/操作的记录 |
| `.env.pre_dev_v1.bak` | 备份 | DEV-V1 落地前 `.env` |
| `.env.pre_density_boost.bak` | 备份 | 产出密度提升前 `.env` |
| `data/db/akshare_mcp.pre_dev_v1.bak` | 备份 | DEV-V1 落地前 DB(2.93 GB) |
| `scripts/dev_v1_ops/` | 子目录 | 历史调研/验证脚本归档 |

### 关联代码

| 文件 | 作用 |
|---|---|
| `packages/strategy-factory/src/strategy_factory/application/_runtime_toggles.py` | DEV-V1 toggle 定义 |
| `packages/akshare-mcp/src/akshare_mcp/config/_strategy_factory_toggles.py` | toggle 镜像(akshare-mcp 侧) |
| `packages/strategy-factory/src/strategy_factory/application/_submitter_actions/runner_parts/persistence.py` | P0 D 级硬否决 toggle 化(第 51-100 行) |
| `packages/akshare-mcp/src/akshare_mcp/services/incubation_factory/intake.py` | P1 paper observation intake 逻辑 |
| `packages/akshare-mcp/src/akshare_mcp/services/incubation_factory/runner.py` | P1 Phase 2 加载 paper 候选 |
| `packages/aiask-quant-core/src/aiask_quant_core/storage/sqlite/_strategy_crud_core.py` | P1 SQL `list_paper_observation_strategies` |
| `packages/strategy-factory/src/strategy_factory/application/submission_gate/runner_parts/normalizers.py` | P3 trade-aware family Proxy |
| `packages/strategy-factory/src/strategy_factory/application/submission_gate/runner_parts/multiple_testing.py` | V5-PR-1 `_inject_run_correction_metrics` |

---

## 附录 B: 决策日志位置和格式

`data/reports/sf_dev_v1_decision_log.md` — 每次重大操作都追加一段,包含:

```markdown
## YYYY-MM-DD HH:MM <动作描述>

**前置条件**:
- ...

**操作**: <什么命令/什么修改>

**预期影响**: <反事实模拟数据>

**验收指标**:
- ...

**红线告警阈值**:
- (R1/R2/R3 ...)

**回滚预案**:
- ...

**实测数据**(操作完成后填写):
- ...

**判定**: ✅/⚠️/❌
```

---

**手册结束。** 有问题先看 `status` + `verify`,大概率自助解决。
