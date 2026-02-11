# AIASK 项目代码审查优化方案（OPTIMIZATION_PLAN）

> 文档位置：项目根目录 `./OPTIMIZATION_PLAN.md`
> 依据来源：基于已完成的《AIASK 全面代码审查报告》整理
> 适用范围：`packages/akshare-mcp` 及其相关配置、工具、服务、存储与测试模块

---

## 1. 执行摘要（P0 / P1 / P2）

### P0（立即处理）
1. **依赖与运行环境定义冲突**（安装/部署高风险）
   涉及 `pyproject.toml`、`setup.py`、`requirements.txt`、README 多源不一致。
2. **数据同步后台任务可靠性不足**（数据一致性风险）
   `services/data_sync.py` 中 `asyncio.create_task(...)` 缺少任务追踪、重试与关闭前回收。
3. **向量检索实现与设计目标偏离**（可扩展性风险）
   当前主路径偏 Python 侧候选集计算，未充分体现向量索引数据库能力。

### P1（短周期处理）
4. **批量回测前置取数串行化**，Ray 并行优势被 IO 阶段吞噬。
5. **SimpleCache 文件缓存无显式并发控制**，高并发下存在竞争与统计偏差风险。
6. **部分因子实现金融严谨性不足**（如 beta 随机模拟）。

### P2（中长期治理）
7. **Manager 聚合注册体量过大**，维护复杂度升高。
8. **文档与仓库现实结构存在偏差**，影响上手与交付流程一致性。

---

## 2. 代码结构问题清单（附文件路径与代码示例）

## 2.1 数据同步职责过重 + 落库任务“放飞”
**文件路径：** `packages/akshare-mcp/src/akshare_mcp/services/data_sync.py`

```python
# packages/akshare-mcp/src/akshare_mcp/services/data_sync.py
# get_kline_with_cache() 内
# ...
cache.set(cache_key, data)

# 异步写入 TimescaleDB（无追踪、无重试、无生命周期管理）
asyncio.create_task(self._save_klines_to_db(stock_code, data))
```

**问题说明：**
- 读取路径（cache/db/api）与写回路径（落库）耦合在单函数中；
- 后台任务可能在高并发/进程退出时丢失，造成“返回成功但数据库未持久化”。

---

## 2.2 文件缓存并发安全不足
**文件路径：** `packages/akshare-mcp/src/akshare_mcp/cache.py`

```python
# packages/akshare-mcp/src/akshare_mcp/cache.py
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

with open(path, "w", encoding="utf-8") as f:
    json.dump({"ts": time.time(), "ttl": ttl_seconds, "payload": value}, f)
```

**问题说明：**
- 直接文件读写，无原子写保护与锁机制；
- 热点 key 场景下可能出现竞争、脏读/失败回退。

---

## 2.3 批量回测 IO 阶段串行
**文件路径：** `packages/akshare-mcp/src/akshare_mcp/tools/backtest.py`

```python
# packages/akshare-mcp/src/akshare_mcp/tools/backtest.py
for code in normalized_codes:
    klines, _ = await _fetch_klines(db, code, start_date, end_date)
    if klines:
        klines_dict[code] = klines
```

**问题说明：**
- 回测前置取数为逐只串行，股票数增加时耗时近线性；
- Ray 并行仅覆盖计算段，整体性能收益不稳定。

---

## 2.4 Manager 手工注册维护成本高
**文件路径：** `packages/akshare-mcp/src/akshare_mcp/tools/managers/__init__.py`

```python
# packages/akshare-mcp/src/akshare_mcp/tools/managers/__init__.py
register_alerts_manager(mcp)
register_portfolio_manager(mcp)
# ...
register_insight_manager(mcp)
```

**问题说明：**
- 新增 manager 需同步修改 import 与 register，容易漏改；
- 大规模工具扩张时回归与可观测性压力上升。

---

## 3. 性能瓶颈分析（含影响范围）

1. **批量回测取数串行（高影响）**
   - 影响模块：`tools/backtest.py`
   - 影响范围：批量回测任务（N 只股票）墙钟时间随 N 近线性增长。

2. **文件缓存 IO 放大（中高影响）**
   - 影响模块：`cache.py`、`tools/data_sync.py`
   - 影响范围：高频行情/指标请求场景，磁盘读写压力增大。

3. **向量检索偏内存计算（中高影响）**
   - 影响模块：`tools/vector.py`、`services/vector_search.py`
   - 影响范围：候选集扩大后 CPU 时间与延迟抖动明显。

4. **异步落库无监控（中影响）**
   - 影响模块：`services/data_sync.py`
   - 影响范围：数据一致性、故障可追踪性、恢复复杂度。

---

## 4. 功能缺陷列表（严重程度分级）

### 🔴 高
- 依赖定义冲突导致环境不可复现（安装结果依入口不同而变化）。
- 数据同步返回成功但落库可能失败（后台任务缺乏保障）。
- 文档结构与实际仓库结构偏差可能误导部署与协作流程。

### 🟡 中
- 批量回测 IO 串行导致吞吐受限。
- SimpleCache 并发安全与原子写不足。
- 向量检索未充分利用向量数据库能力。
- 部分因子实现缺乏金融严谨性（beta 随机市场收益）。

### 🟢 低
- manager 聚合入口手工维护，扩展成本高。
- 工具层部分函数偏长，职责可继续拆分。
- 错误信息风格与中英文一致性可进一步统一。

---

## 5. 优化建议方案（实施步骤 + 预期收益）

### 方案 A：依赖与版本治理统一（1~2 天）
**步骤：**
1) 以 `packages/akshare-mcp/pyproject.toml` 为唯一依赖真相源；
2) 精简 `setup.py`（薄封装）并与 pyproject 自动校验一致性；
3) 生成锁定依赖清单并纳入 CI 校验；
4) README 版本门槛由脚本检查后写入。

**收益：** 安装可复现、部署故障显著下降、团队协作稳定性提升。

### 方案 B：数据同步可靠性改造（2~4 天）
**步骤：**
1) `create_task` 改为受控队列（重试/backoff/死信）；
2) 增加指标：pending、success、fail、retry、lag；
3) 服务关闭时 flush 未完成任务；
4) 失败日志结构化，支持追踪与补偿。

**收益：** 数据一致性提升，降低“隐性丢数据”风险。

### 方案 C：批量回测性能优化（2~3 天）
**步骤：**
1) 前置取数改为并发（`asyncio.gather` + 限流）；
2) DB 增加批量 K 线读取接口；
3) 分离并输出 IO/计算耗时指标；
4) 与 `data_warmup` 联动做热点预热。

**收益：** 批量回测时延显著下降，并行收益可见。

### 方案 D：缓存层升级（3~5 天）
**步骤：**
1) 保留文件缓存为降级层；
2) 增加进程内 LRU（可选 Redis）；
3) 文件写入改“临时文件 + 原子替换”；
4) cache key 增加 namespace/version。

**收益：** 降低 IO 放大，提高并发稳定性与命中率。

### 方案 E：向量检索与因子严谨性增强（4~7 天）
**步骤：**
1) 引入 pgvector/ANN 索引检索主路径；
2) 特征计算从在线迁移到离线/增量更新；
3) beta 改为真实基准指数收益计算；
4) 关键因子增加一致性与回归测试。

**收益：** 向量检索性能更稳定，量化分析可信度提升。

---

## 6. 重构优先级建议（投入产出比）

| 优先级 | 重构项 | 预计投入 | 预期收益 | ROI |
|---|---|---:|---|---|
| P0 | 依赖与版本统一（方案 A） | 1~2 天 | 立即降低部署与环境风险 | 很高 |
| P0 | 数据同步可靠性改造（方案 B） | 2~4 天 | 消除数据一致性隐患 | 很高 |
| P1 | 批量回测并发取数（方案 C） | 2~3 天 | 批量性能显著提升 | 高 |
| P1 | 缓存层升级（方案 D） | 3~5 天 | 并发稳定性与命中率提升 | 中高 |
| P2 | 向量检索与因子增强（方案 E） | 4~7 天 | 中长期核心能力升级 | 中高（长期） |
| P2 | manager 注册自动化与工具层瘦身 | 1~2 天 | 维护效率提升 | 中 |

---

## 附：优先落地清单（建议执行顺序）
1. 当周完成：方案 A + 方案 B（先止血，保稳定）。
2. 次周完成：方案 C（先做批量回测取数并发化）。
3. 第三周：方案 D（缓存分层）。
4. 第四周起：方案 E（向量索引与因子方法学完善）。

---

## 7. 详细依据与证据链（供评审/交接使用）

> 说明：本节用于回答“为什么要改、依据是什么、如何验证改对了”。

### 7.1 关键问题证据矩阵

| 问题ID | 结论 | 证据文件 | 关键代码/现象 | 风险解释 |
|---|---|---|---|---|
| E-01 | 数据同步存在“返回成功但落库不确定”窗口 | `packages/akshare-mcp/src/akshare_mcp/services/data_sync.py` | `asyncio.create_task(self._save_klines_to_db(...))` | 后台任务未纳入任务治理，服务退出或异常时可能丢失落库 |
| E-02 | 文件缓存存在并发竞争风险 | `packages/akshare-mcp/src/akshare_mcp/cache.py` | 直接 `open(..., "w")` 写 JSON，无锁/无原子替换 | 并发写热点 key 时可能出现覆盖、失败回退、统计失真 |
| E-03 | 批量回测前置取数为串行 | `packages/akshare-mcp/src/akshare_mcp/tools/backtest.py` | `for code in normalized_codes: await _fetch_klines(...)` | IO 阶段近线性增长，Ray 并行只能覆盖计算段 |
| E-04 | manager 注册手工维护 | `packages/akshare-mcp/src/akshare_mcp/tools/managers/__init__.py` | 多个 `register_xxx_manager(mcp)` 手工调用 | 新增/删除 manager 易漏改，维护成本高 |
| E-05 | 依赖与版本口径多源 | `pyproject.toml` / `setup.py` / `requirements.txt` / README | 同一项目多套依赖入口 | 造成“本地可跑/线上失败”或行为差异 |

### 7.2 问题判定标准（避免主观化）

- **可靠性判定**：是否存在“成功返回但最终状态不可达成”的路径（如异步落库无追踪）。
- **性能判定**：关键路径是否存在可避免的串行（特别是批量场景）。
- **可维护性判定**：新增一个功能是否需要跨多处手工改动且缺乏自动校验。
- **一致性判定**：文档、安装入口、运行时行为是否可复现且口径统一。

### 7.3 对其他成员最关键的阅读建议

1. 先看 **7.1 证据矩阵**（知道问题来源）。
2. 再看 **第5节优化方案**（知道怎么改）。
3. 最后看 **第8节验收标准**（知道改完怎么算完成）。

---

## 8. 验收标准（Definition of Done）

### 8.1 方案 A（依赖统一）DoD
- [ ] `pyproject.toml` 成为唯一依赖真相源；
- [ ] `setup.py`/`requirements.txt` 与 pyproject 自动比对通过；
- [ ] CI 增加依赖一致性检查，PR 必过；
- [ ] README 的 Python 版本与实际运行门槛一致。

### 8.2 方案 B（数据同步可靠性）DoD
- [ ] 不再使用裸 `create_task` 直接放飞落库任务；
- [ ] 存在可观测指标：pending/success/fail/retry/lag；
- [ ] 进程退出前可 flush 未完成任务；
- [ ] 失败任务可追踪（日志或死信）。

### 8.3 方案 C（批量回测性能）DoD
- [ ] 批量取数改并发并带限流；
- [ ] 输出分阶段耗时（取数/计算/汇总）；
- [ ] 在同样股票数量下总体耗时显著下降（建议目标：降低 30%+）。

### 8.4 方案 D（缓存升级）DoD
- [ ] 文件写入具备原子替换机制；
- [ ] 新增内存层缓存（可选 Redis）并有命中率指标；
- [ ] 高并发压测下不出现异常写失败飙升。

### 8.5 方案 E（向量检索/因子）DoD
- [ ] 向量检索主路径可配置为索引检索；
- [ ] 因子 beta 改为真实基准收益序列计算；
- [ ] 关键因子与检索结果有回归测试。

---

## 9. 风险与回滚策略

| 变更项 | 可能风险 | 监控指标 | 回滚方案 |
|---|---|---|---|
| 数据同步任务队列化 | 吞吐下降或队列堆积 | queue depth、写入延迟、失败率 | 切回旧路径（开关），保留日志追踪 |
| 缓存分层改造 | 命中率短期波动 | hit_rate、p95 延迟、IO 使用率 | 关闭新缓存层，仅保留 SimpleCache |
| 批量并发取数 | 上游源限流/封禁 | 请求失败率、429/超时比例 | 降低并发度或回退串行 |
| 向量索引引入 | 索引构建成本与结果偏移 | 查询延迟、召回稳定性 | 保留原有候选集策略作为兜底 |

---

## 10. 沟通与实施建议（便于团队协同）

- 建议每个方案都附一张 **“前后对比”**：
  - 改动前现象（日志/指标）
  - 改动后目标
  - 验收截图或测试输出
- 每个 PR 必须包含：
  1) 变更摘要；
  2) 风险评估；
  3) 回滚步骤；
  4) 验收结果（至少 1 条量化指标）。
- 评审时按“证据 -> 方案 -> 验收”三段式推进，避免只讨论实现偏好。

> 备注：若需要，我可以继续追加《实施任务拆解版》（按文件/函数/工时/负责人模板输出），用于直接进入迭代执行。

