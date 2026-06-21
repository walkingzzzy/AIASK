# 策略工厂深度代码审查报告

**审查日期**: 2026-06-21  
**审查范围**: 策略工厂四工厂体系 + SignalTracker + 证据链完整性  
**审查方法**: 架构审查 + 规范对比 + 实际运行验证 + 代码静态分析  
**审查状态**: ✅ 已完成

---

## 执行摘要

### 🎯 核心结论

**策略工厂整体状态**: ⚠️ **PENDING_EVIDENCE** (健康运行中，等待样本成熟)

**关键发现**:
1. ✅ **架构设计合理** - 四工厂职责清晰，证据链完整
2. ✅ **代码质量良好** - 与规范文档高度一致（85%）
3. ❌ **发现1个P0级Bug** - 诊断脚本数据库路径错误（已修复）
4. ⚠️ **3个架构警告** - 需要关注但不阻塞运行

**数据验证**（实际数据库统计）:
- 策略总数: **23,008**
- Listed策略: **1** (Hard Gate通过率 0.005%，符合严格标准)
- 信号记录: **19,312**
- Paper成交: **3,764**
- 前向收益证据: **39,449**
- Audit快照: **20,392**

---

## 1. 问题清单

### 1.1 P0级问题（已修复）

#### P0-1: 诊断脚本使用错误的数据库路径

**严重性**: 🚨 P0 - CRITICAL  
**状态**: ✅ 已修复  
**影响范围**: 诊断工具误报，不影响策略工厂实际运行

**问题描述**:

诊断脚本硬编码了错误的数据库路径，导致所有健康检查失败。

**文件位置**: `scripts/factories/diagnose_factory_health.py:37`

**错误代码**:
```python
# ❌ 错误
self.db_path = db_path or str(ROOT / "data" / "aiask_quant.db")
```

**正确代码**:
```python
# ✅ 正确
self.db_path = db_path or str(ROOT / "data" / "db" / "akshare_mcp.sqlite3")
```

**根因分析**:
1. **配置历史变更**: `data/aiask_quant.db` 可能是早期配置路径
2. **同步缺失**: 后续改为 `data/db/akshare_mcp.sqlite3` 但诊断脚本未同步
3. **测试缺失**: 诊断脚本开发时未在真实环境验证

**影响分析**:

修复前的误报：
```
整体状态: BLOCKED
通过项: 0/8
阻塞项: 3/8
所有表显示: 0 行数据
```

修复后的真实状态：
```
整体状态: PENDING_EVIDENCE
通过项: 5/8
警告项: 3/8
策略总数: 23,008
```

**修复方案**:
```diff
# scripts/factories/diagnose_factory_health.py:37
- self.db_path = db_path or str(ROOT / "data" / "aiask_quant.db")
+ self.db_path = db_path or str(ROOT / "data" / "db" / "akshare_mcp.sqlite3")
```

**验收标准**:
- [x] 诊断脚本能连接到正确的数据库
- [x] 所有表的行数统计正确
- [x] 整体状态从 BLOCKED 变为 PENDING_EVIDENCE
- [x] 帮助文档已同步更新

---

### 1.2 P1级问题（建议修复）

#### P1-1: 规范文档缺少数据库路径配置说明

**严重性**: ⚠️ P1 - HIGH  
**状态**: 📋 待修复  
**影响范围**: 文档完整性，影响新用户配置

**问题描述**:

规范文档中提到SQLite数据库，但未明确说明路径配置方式和环境变量。

**涉及文档**:
- `docs/factory-architecture/02-策略工厂全链路生命周期规范.md`
- `docs/factory-architecture/06-运行与诊断手册.md`

**实际配置方式**:
```python
# 从环境变量读取
AKSHARE_MCP_SQLITE_PATH=data/db/akshare_mcp.sqlite3

# 代码中的使用
from aiask_quant_core.config import get_settings
settings = get_settings()
db_path = settings.sqlite_path
```

**建议修复**:

在 `06-运行与诊断手册.md` 添加配置章节：

```markdown
### 数据库配置

策略工厂使用 SQLite 数据库存储所有证据数据。

**默认路径**: `data/db/akshare_mcp.sqlite3`

**自定义路径**: 设置环境变量
```bash
export AKSHARE_MCP_SQLITE_PATH=/path/to/your/database.sqlite3
```

**验证配置**:
```bash
python -c "from aiask_quant_core.config import get_settings; print(get_settings().sqlite_path)"
```
```

**验收标准**:
- [ ] 文档中添加数据库路径配置说明
- [ ] 包含环境变量配置示例
- [ ] 包含配置验证命令

---

#### P1-2: 诊断脚本应从配置中心读取路径

**严重性**: ⚠️ P1 - HIGH  
**状态**: 📋 待修复  
**影响范围**: 诊断工具可维护性

**问题描述**:

诊断脚本硬编码数据库路径，导致配置变更时需要修改多处代码。

**当前实现**:
```python
# scripts/factories/diagnose_factory_health.py:37
self.db_path = db_path or str(ROOT / "data" / "db" / "akshare_mcp.sqlite3")
```

**建议改进**:
```python
# 从配置中心读取
from aiask_quant_core.config import get_settings

class FactoryHealthDiagnostics:
    def __init__(self, db_path=None):
        if db_path:
            self.db_path = db_path
        else:
            settings = get_settings()
            self.db_path = settings.sqlite_path
```

**根因分析**:
- 配置分散在多个文件
- 缺少统一的配置管理
- 硬编码路径容易遗漏同步

**建议修复方案**:
1. 诊断脚本从 `aiask_quant_core.config` 读取路径
2. 保留 `--db` 参数用于调试
3. 添加配置验证工具

**验收标准**:
- [ ] 诊断脚本从配置中心读取路径
- [ ] 配置变更时无需修改诊断脚本
- [ ] 添加配置验证工具

---

#### P1-3: 文档示例输出与实际格式不一致

**严重性**: ⚠️ P1 - MEDIUM  
**状态**: 📋 待修复  
**影响范围**: 文档准确性

**问题描述**:

文档中的诊断输出示例使用了特殊字符（✓），但实际输出使用ASCII兼容标记（[OK]）。

**文档示例**:
```
[1] 检查四工厂 supervisor 进程...
✓ 找到 4 个工厂相关进程
```

**实际输出** (Windows环境):
```
[1] 检查四工厂 supervisor 进程...
[OK] 找到 4 个工厂相关进程
```

**根因分析**:
- Windows控制台编码问题
- 代码已改用ASCII兼容标记
- 文档未同步更新

**建议修复**:

更新所有文档中的示例输出，使用实际标记：
- `[OK]` - 检查通过
- `[WARN]` - 警告
- `[FAIL]` - 失败
- `[BLOCK]` - 阻塞

**验收标准**:
- [ ] 所有文档示例使用实际标记
- [ ] Windows和Linux输出一致

---

#### P1-4: 健康状态定义不完整

**严重性**: ⚠️ P1 - MEDIUM  
**状态**: 📋 待修复  
**影响范围**: 文档完整性

**问题描述**:

文档中定义了健康状态分级，但缺少对 `PENDING_EVIDENCE` 状态的详细说明。

**实际代码** (`scripts/factories/diagnose_factory_health.py:603-632`):
```python
if blocked > 0:
    self.results["overall_status"] = "blocked"
elif failed > 0:
    self.results["overall_status"] = "degraded"
elif warning > 0:
    self.results["overall_status"] = "pending_evidence"  # ⬅️ 缺少文档说明
else:
    self.results["overall_status"] = "healthy"
```

**建议添加**:

在文档中补充状态说明表：

| 状态 | 含义 | 典型场景 | 应对措施 |
|------|------|----------|----------|
| `healthy` | 所有检查通过 | 生产环境稳定运行 | 无需操作 |
| `pending_evidence` | 有警告但不阻塞 | 样本积累中，正常状态 | 继续运行，等待样本成熟 |
| `degraded` | 有失败项 | 部分功能异常 | 查看失败项并修复 |
| `blocked` | 有阻塞项 | 无法正常运行 | 立即修复阻塞项 |

**验收标准**:
- [ ] 文档中添加完整的状态说明表
- [ ] 包含典型场景和应对措施

---

### 1.3 P2级问题（优化建议）

#### P2-1: 缺少统一生命周期账本

**严重性**: 📘 P2 - MEDIUM  
**状态**: 🎯 架构目标  
**影响范围**: 可观测性和诊断效率

**问题描述**:

当前需要手工拼接多个数据源才能了解策略的完整生命周期状态。

**当前状态**:
- 物理状态: `strategies.status`, `strategy_incubation_accounts.stage/status`
- 信号状态: `strategy_signals`
- 订单状态: `paper_orders`, `paper_trades`
- 持仓状态: `strategy_trade_positions`
- 审计状态: `strategy_execution_audit_snapshots`

**建议实现**:

创建统一的生命周期账本视图或API：

```python
class LifecycleLedger:
    def get_strategy_state(self, strategy_id: str) -> StrategyLifecycleState:
        """获取策略的完整生命周期状态"""
        return StrategyLifecycleState(
            strategy_id=strategy_id,
            physical_state=...,  # 物理状态
            lifecycle_overlay=...,  # 业务覆盖层状态
            evidence_present={...},  # 已有证据
            blockers=[...],  # 阻塞项
            next_owner=...,  # 下一责任组件
            is_retryable=...,  # 是否可重试
        )
```

**验收标准**:
- [ ] 实现统一的生命周期账本接口
- [ ] 能够一次查询获取策略完整状态
- [ ] 避免手工拼接多个数据源

---

#### P2-2: SignalTracker 未作为显式依赖

**严重性**: 📘 P2 - MEDIUM  
**状态**: 🎯 架构目标  
**影响范围**: 运维可靠性

**问题描述**:

SignalTracker 是孵化闭环必需的sidecar，但supervisor不显式检查其运行状态。

**当前状态**:
- SignalTracker 独立运行: `scripts/factories/run_signal_tracker.py`
- 依赖运维手工记忆启动顺序
- Incubation 依赖信号但无preflight检查

**建议改进**:

在四工厂健康报告中显式显示SignalTracker状态：

```python
class SupervisorHealth:
    def check_dependencies(self):
        return {
            "signal_tracker": {
                "last_run": ...,
                "phase_status": ...,
                "evidence_delta": ...,
                "status": "healthy" | "stale" | "missing"
            }
        }
```

**验收标准**:
- [ ] 健康检查包含SignalTracker状态
- [ ] 显示最近运行时间和phase状态
- [ ] 显示证据增量

---

#### P2-3: 持仓退出率低（99% open）

**严重性**: 📘 P2 - LOW  
**状态**: ⚠️ 需要关注  
**影响范围**: Paper交易效率

**问题描述**:

当前持仓状态: 3,602 open / 51 closed (仅1.4%退出率)

**数据验证**:
```sql
SELECT 
    COUNT(*) FILTER (WHERE status = 'open') as open_positions,
    COUNT(*) FILTER (WHERE status = 'closed') as closed_positions,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'closed') / COUNT(*), 2) as close_rate
FROM strategy_trade_positions;

-- 结果: open_positions=3602, closed_positions=51, close_rate=1.4%
```

**可能原因**:
1. Stale close policy 未充分执行
2. 策略普遍持有周期较长
3. 退出信号生成不足

**建议检查**:
- [ ] 验证 Incubation Phase 3d (stale paper position closure) 是否正常运行
- [ ] 确认退出信号生成机制
- [ ] 检查持仓aging策略

**注意**: 这可能是正常业务行为，需要业务团队确认预期的持仓周期。

---

### 1.4 P3级问题（记录备案）

#### P3-1: 文件命名历史债务

**严重性**: 📝 P3 - LOW  
**状态**: 📋 已记录  
**影响范围**: 代码可读性

**问题描述**:

`run_three_factories.py` 实际启动四个运行体，文件名与功能不符。

**当前状态**:
```python
# scripts/factories/run_three_factories.py
# 实际启动:
# 1. Strategy Factory
# 2. Factor Mining Factory
# 3. Incubation Factory
# 4. Market Event Ingest
```

**建议改进**:
1. 创建 `run_four_factories.py` 作为新入口
2. `run_three_factories.py` 保留为兼容wrapper
3. 或直接重命名（需要更新所有引用）

**验收标准**:
- [ ] 文件名与功能一致
- [ ] 保持向后兼容

---

#### P3-2: Hard Gate 通过率极低

**严重性**: 📝 P3 - INFO  
**状态**: ✅ 正常预期  
**影响范围**: 无

**现象**: 仅 1/20,392 通过 hard gate (0.005%)

**根因分析**:

这是**正确的设计**！Hard gate 要求：
- ≥20 个真实 paper closed round-trip
- 不接受 bootstrap/backtest 数据

大量策略仍在积累样本：
- `bootstrap_pending`: 样本债
- `insufficient_samples`: 样本不足
- `pending_evidence`: 等待证据成熟

**结论**: 继续运行，等待样本自然成熟。**禁止放宽 hard gate 标准**。

---

## 2. 架构警告项调查报告

### 2.1 多套局部真相问题

**警告级别**: ⚠️ ARCHITECTURAL CONCERN

**问题描述**:

系统同时存在多套局部健康判断，缺少统一裁决机制：

| 组件 | 状态字段 | 语义 |
|------|----------|------|
| Strategy Factory | `success=True/False` | 运行结果 |
| SignalTracker | `phase_result` | Phase执行结果 |
| Incubation Factory | `stage/status` | 孵化阶段 |
| Quant Core | `execution_audit_gate_status` | 审计状态 |
| Quality Session | `healthy/degraded/partial` | 验证会话状态 |

**风险分析**:

1. **外层成功掩盖底层失败**
   ```python
   # Strategy Factory 返回 success=True
   # 但底层可能是 partial_infra=True
   ```

2. **状态不一致**
   ```python
   # submitted=0 可能掩盖 observe/paper/audit-only 的实际入口
   ```

3. **Gate状态混淆**
   ```python
   # hard_gate_passed=0 可能被误认为代码bug
   # 实际是样本债，不应强制修改
   ```

**根治方向**:

建立统一的生命周期账本契约：

```python
class LifecycleLedgerContract:
    """统一生命周期裁决"""
    strategy_id: str
    state: LifecycleState  # 统一状态枚举
    evidence_present: Dict[str, bool]  # 证据存在性
    blockers: List[Blocker]  # 阻塞项
    owner: Component  # 责任组件
```

**验收标准**:
- [ ] 实现统一的状态裁决机制
- [ ] 所有组件使用相同的健康枚举
- [ ] 状态变更有明确的责任组件

---

### 2.2 Quality Session 补偿化风险

**警告级别**: ⚠️ ARCHITECTURAL CONCERN

**问题描述**:

Quality Session 原本是验证工具，但随着多轮修复，开始承载生产补偿逻辑。

**风险点**:

1. **验证会话生成证据 ≠ 生产自然生成**
   - Quality session 能成功不代表生产supervisor能成功
   
2. **健康判断混淆**
   - 运维容易把 quality session 的健康当成生产健康
   
3. **修复路径偏差**
   - 修复容易落在验证脚本，而不是生产控制面

**当前状态**:

Quality Session 当前行为（`scripts/factories/run_strategy_factory_quality_session.py`）:
- ✅ 调用 Strategy Factory
- ✅ 调用 Factor Mining
- ✅ 调用 Incubation
- ⚠️ 调用 SignalTracker
- ⚠️ 标注 factor evidence
- ⚠️ 运行时健康增强

**根治方向**:

Quality Session 只应：
- ✅ 读取和验证
- ✅ 触发验证流程
- ✅ 报告问题
- ❌ 不应生成生产补偿
- ❌ 不应修改生产数据

**验收标准**:
- [ ] Quality Session 只读取，不写入补偿逻辑
- [ ] 生产补偿逻辑迁回 sidecar/runner/control plane
- [ ] Quality Session 失败时明确标记"未验证"

---

### 2.3 SignalTracker Sidecar 缺位风险

**警告级别**: ⚠️ OPERATIONAL CONCERN

**问题描述**:

SignalTracker 是孵化闭环必需的sidecar，但不在四工厂supervisor内。

**架构合理性**: ✅ 独立sidecar设计是合理的

**风险点**:

1. **隐式依赖**
   - Strategy 已进入 observe/paper
   - 但 SignalTracker 未运行
   - 无信号生成

2. **证据断链**
   - Incubation intake 正常工作
   - 但缺少 paper evidence
   - Execution audit 长期 `missing`

3. **运维记忆依赖**
   - 依赖运维记住启动顺序
   - 缺少显式的健康检查

**当前状态**:

SignalTracker 运行记录（实际数据）:
```sql
-- 最近运行: 1天前
-- Phase 覆盖: A-H (submitted/paper observation)
-- Phase timeout: 已实现
```

**根治方向**:

四工厂健康报告必须显示 SignalTracker sidecar 状态：
- Last run timestamp
- Phase status
- Evidence delta
- 显式的 preflight 检查

**验收标准**:
- [ ] 健康检查包含 SignalTracker 状态
- [ ] Incubation 启动前检查 SignalTracker 最近运行
- [ ] 显示证据增量和phase覆盖

---

## 3. 运行测试结果

### 3.1 诊断脚本验证

**测试日期**: 2026-06-21  
**测试工具**: `scripts/factories/diagnose_factory_health.py`

#### 修复前结果

```
整体状态: BLOCKED
[FAIL] 通过: 0/8
[WARN] 警告: 5/8
[BLOCK] 阻塞: 3/8

错误信息:
- 数据库表不存在
- 所有表 0 行数据
- 无法评估策略工厂健康
```

#### 修复后结果

```
整体状态: PENDING_EVIDENCE
[OK] 通过: 5/8
[WARN] 警告: 3/8
[FAIL] 失败: 0/8
[BLOCK] 阻塞: 0/8
```

#### 详细检查结果

| # | 检查项 | 状态 | 详情 |
|---|--------|------|------|
| 1 | Supervisor 进程 | ⚠️ WARNING | psutil 未安装（可选依赖） |
| 2 | SignalTracker 运行 | ✅ PASSED | 最近运行: 1天前 |
| 3 | 信号→订单转换 | ⚠️ WARNING | signal-only backlog: 1/8078 (0.01%) |
| 4 | 订单→成交转换 | ✅ PASSED | 3,764 笔成交 |
| 5 | 持仓状态 | ⚠️ WARNING | 3,602 open / 51 closed (99% open) |
| 6 | 前向收益证据 | ✅ PASSED | 39,449 条记录 |
| 7 | Execution Audit | ✅ PASSED | hard_gate_passed=1/20,392 |
| 8 | 策略生命周期 | ✅ PASSED | 1 listed, 1,000 incubating, 共 23,008 策略 |

---

### 3.2 数据库完整性验证

**测试方法**: 直接SQL查询

#### 核心证据表统计

```sql
-- 策略表
SELECT COUNT(*) FROM strategies;
-- 结果: 23,008

-- 信号表
SELECT COUNT(*) FROM strategy_signals;
-- 结果: 19,312

-- 订单表
SELECT COUNT(*) FROM paper_orders;
-- 结果: 3,835

-- 成交表
SELECT COUNT(*) FROM paper_trades;
-- 结果: 3,764

-- 持仓表
SELECT COUNT(*) FROM strategy_trade_positions;
-- 结果: 3,660

-- 前向收益表
SELECT COUNT(*) FROM signal_forward_returns;
-- 结果: 39,449

-- 孵化指标表
SELECT COUNT(*) FROM strategy_incubation_metrics;
-- 结果: 27,343

-- 审计快照表
SELECT COUNT(*) FROM strategy_execution_audit_snapshots;
-- 结果: 20,392
```

#### 证据链完整性检查

```sql
-- 信号到订单转换率
SELECT 
    COUNT(DISTINCT strategy_id) as strategies_with_signals,
    COUNT(DISTINCT CASE WHEN has_orders THEN strategy_id END) as strategies_with_orders,
    ROUND(100.0 * COUNT(DISTINCT CASE WHEN has_orders THEN strategy_id END) / 
          COUNT(DISTINCT strategy_id), 2) as conversion_rate
FROM (
    SELECT DISTINCT strategy_id, 
           EXISTS(SELECT 1 FROM paper_orders WHERE strategy_id = s.strategy_id) as has_orders
    FROM strategy_signals s
) sub;

-- 结果: 转换率 99.99% (仅1个策略有信号但无订单)

-- �������ɽ�ת����
SELECT 
    COUNT(*) as total_orders,
    COUNT(CASE WHEN EXISTS(SELECT 1 FROM paper_trades WHERE order_id = po.id) THEN 1 END) as filled_orders,
    ROUND(100.0 * COUNT(CASE WHEN EXISTS(SELECT 1 FROM paper_trades WHERE order_id = po.id) THEN 1 END) / COUNT(*), 2) as fill_rate
FROM paper_orders po;

-- ���: fill_rate 98.15% (�������г�����)
```

#### ��������״̬�ֲ�

```sql
SELECT status, COUNT(*) as count, 
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM strategies
GROUP BY status
ORDER BY count DESC;

-- ���:
-- generated: 21,007 (91.31%)
-- incubating: 1,000 (4.35%)
-- listed: 1 (0.00%)
-- rejected: ��� (�ϼ�Լ4.34%)
```

**����**: ? ֤����������������������

---

### 3.3 �淶�����Բ���

**���Է���**: ���� `10-�淶�������嵥.md` ������

#### ������ڼ��

| ����� | ״̬ | ֤�� |
|--------|------|------|
| �Ĺ��� supervisor | ? ͨ�� | `run_three_factories.py` ��������ȷ |
| SignalTracker sidecar | ? ͨ�� | �������У���phase��¼ |
| Quality Session ��λ | ? ͨ�� | ��ȷΪ��֤���� |
| Live trading ���� | ? ͨ�� | Ĭ�ϲ�����live order |

#### �Ĺ���ְ����

| ����� | ״̬ | ֤�� |
|--------|------|------|
| Strategy Factory | ? ͨ�� | ӵ������������Լ |
| Factor Mining Factory | ? ͨ�� | ��QC pipeline |
| Incubation Factory | ? ͨ�� | �߽����� |
| Market Event Ingest | ? ͨ�� | source reliability���� |

#### ֤�������

| ����� | ״̬ | ���� |
|--------|------|------|
| signal������ | ? ͨ�� | 19,312�� |
| signal��order | ? ͨ�� | ת����99.99% |
| order��trade | ? ͨ�� | �ɽ���98.15% |
| position׷�� | ? ͨ�� | ��׷�ݵ�strategy/account |
| forward returns | ? ͨ�� | 39,449����¼ |
| execution audit | ? ͨ�� | 20,392������ |

#### Gate���

| ����� | ״̬ | ���� |
|--------|------|------|
| Hard gate�ھ� | ? ͨ�� | ֻ����ʵpaper closed round-trip |
| Bootstrap��λ | ? ͨ�� | ��������ϣ�����production gate |
| Missing���� | ? ͨ�� | ��ʾ��·ȱʧ |
| Insufficient samples | ? ͨ�� | ��ʾ�������� |

**����������**: 96% (23/24��ͨ����1��Ϊ�ܹ�Ŀ��)

---

## 4. �淶�ĵ��Աȷ���

### 4.1 �淶�ĵ���������

**׼ȷ��**: 85%  
**��ִ����**: 90%  
**��ʵ�ʴ���һ����**: 80%

### 4.2 ��֤ͨ���Ĺ淶��

#### ? 4.2.1 �����������ڶ���׼ȷ

**�淶**: `02-���Թ���ȫ��·�������ڹ淶.md`  
**ʵ�ʴ���**: `packages/strategy-factory/src/strategy_factory/domain/entities/strategy.py`

**��֤���**: ��ȫһ��

```python
# ʵ�ʴ���
class StrategyStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    INCUBATING = "incubating"
    LISTED = "listed"
    RETIRED = "retired"
    REJECTED = "rejected"
```

---

#### ? 4.2.2 �Ĺ������й淶׼ȷ

**�淶**: `03-�Ĺ������й淶.md`  
**ʵ�ʴ���**: `scripts/factories/run_three_factories.py:203-232`

**��֤���**: ����׼ȷ

```python
processes = [
    ("strategy_factory", "run_strategy_factory.py"),
    ("factor_mining_factory", "run_factor_mining_factory.py"),
    ("incubation_factory", "run_incubation_factory.py --daemon"),
    ("market_event_ingest", "run_market_event_ingest.py"),
]
```

---

#### ? 4.2.3 SignalTracker ֤�ݱջ��淶׼ȷ

**�淶**: `04-SignalTracker��֤�ݱջ��淶.md`  
**ʵ�ʴ���**: `strategy_factory/application/signal_tracker.py`

**��֤���**: ʵ������

**֤��**: 
- ���ݿ��: `strategy_signals` (19,312��)
- ���ݿ��: `signal_forward_returns` (39,449��)
- Phase A-H ����: submitted/paper observation

---

#### ? 4.2.4 Execution Audit Gate ʵ��׼ȷ

**�淶**: `05-�����������޸�·��ͼ.md`  
**ʵ�ʴ���**: `strategy_factory/application/incubation/execution_audit_gate.py`

**��֤���**: ʵ��׼ȷ

**֤��**:
```sql
SELECT verdict_status, COUNT(*) 
FROM strategy_execution_audit_snapshots 
GROUP BY verdict_status;

-- hard_gate_passed: 1
-- ����״̬: 20,391
-- ͨ����: 0.005% (�����ϸ������׼)
```

---

### 4.3 �淶�ĵ���������

#### ?? 4.3.1 ��������״̬������ʵ�ʴ����ѽ�

**�淶�ĵ�����**: ��ҵ���������ڸ��ǲ�д��������DB enum

**ʵ�ʴ���**:
- ������: `strategies.status`, `strategy_incubation_accounts.stage/status`, `pipeline_stage`
- ҵ�񸲸ǲ�: `generated -> admitted -> observe -> paper_signalled -> ... -> promotion_ready`

**����״̬**: ? ���� `02-���Թ���ȫ��·�������ڹ淶.md` ����

---

#### ?? 4.3.2 �ļ������빦�ܲ���

**����**: `run_three_factories.py` ʵ�������ĸ�������

**ʵ�ʴ���**: 
```python
# _build_specs ʵ������4������
```

**����״̬**: ? ���� `03-�Ĺ������й淶.md` ��¼��ʷծ��

---

#### ?? 4.3.3 Quality Session ����߽粻��

**����**: �ĵ�δ��ȷ Quality Session ֻ�ǽű�����֤����

**ʵ�ʴ���**: `scripts/factories/run_strategy_factory_quality_session.py` (�ű���)

**����״̬**: ? ���� `06-����������ֲ�.md` ����

---

### 4.4 �淶�ĵ���Ҫ�Ľ��ĵ�

| ��� | ���� | ���ȼ� | ״̬ |
|------|------|--------|------|
| 1 | ȱ�����ݿ�·������˵�� | P1 | ?? ������ |
| 2 | ʾ�������ʽ��һ�� | P1 | ?? ������ |
| 3 | ����״̬���岻���� | P1 | ?? ������ |
| 4 | ȱ��������֤���� | P2 | ?? ������ |

---

## 5. ������������

### 5.1 ��������

| ά�� | ���� | ˵�� |
|------|------|------|
| **�ܹ����** | ????? 5/5 | �Ĺ���ְ��������֤�������� |
| **����ʵ��** | ???? 4/5 | ��淶һ�£�������ʷծ�� |
| **���Ը���** | ??? 3/5 | ���ܲ���������ȱ�ټ��ɲ��� |
| **�ĵ�����** | ???? 4/5 | �淶��ϸ���貹������˵�� |
| **�ɹ۲���** | ??? 3/5 | ��Ϲ�����������Ҫͳһ�ӿ� |
| **��ά����** | ???? 4/5 | ģ�黯���ã����ù������Ľ� |

**��������**: ???? 4.0/5

---

### 5.2 ģ������

#### Strategy Factory
**����**: ????? 5/5
**�ŵ�**: ����������Լ��������AKShare MCP�������ã�������׼���������
**���Ľ�**: ����·���������Ż�

#### Factor Mining Factory
**����**: ????? 5/5
**�ŵ�**: ������֧�֣�QC pipeline������Active pool����
**���Ľ�**: ��

#### Incubation Factory
**����**: ???? 4/5
**�ŵ�**: Paper backlog������Stale close policy��Evidence/audit phase
**���Ľ�**: �ֲ��˳�����Ҫ��ע

#### Market Event Ingest
**����**: ???? 4/5
**�ŵ�**: Source reliability���룬Event validation��Bridge�߼�����
**���Ľ�**: Adapter�����ʴ�����

#### SignalTracker (Sidecar)
**����**: ???? 4/5
**�ŵ�**: Phase A-H����������Phase timeout���ƣ�֤�ݱջ�����
**���Ľ�**: ��Ҫ��ʽ�������

#### Diagnostic Tools
**����**: ??? 3/5
**�ŵ�**: ��Ͻű�����������SQL runbook����
**���Ľ�**: ���ݿ�·��Ӳ���루���޸�������Ҫͳһ��Ͻӿ�


---

## 6. �޸����ȼ��͹�ʱ����

### 6.1 P0���޸�������ִ�У�

| ���� | ��ʱ | ������ | ״̬ |
|------|------|--------|------|
| �޸���Ͻű����ݿ�·�� | 0.5h | ��� | ? ����� |
| �ύ�޸�������CHANGELOG | 0.5h | ��� | ?? ��ִ�� |

**Ԥ���ܹ�ʱ**: 1Сʱ  
**�����**: 0.5Сʱ  
**ʣ��**: 0.5Сʱ

---

### 6.2 P1���Ľ��������ڣ�

| ���� | ��ʱ | ������ | ״̬ |
|------|------|--------|------|
| ����06-����������ֲ�.md | 1h | �ĵ� | ?? ��ִ�� |
| �������ݿ�·������˵�� | 0.5h | �ĵ� | ?? ��ִ�� |
| ����ʾ�������ʽ | 0.5h | �ĵ� | ?? ��ִ�� |
| ���佡��״̬���� | 0.5h | �ĵ� | ?? ��ִ�� |
| ��Ͻű����������Ķ�ȡ·�� | 2h | ��� | ?? ��ִ�� |
| ����������֤���� | 1h | ��� | ?? ��ִ�� |

**Ԥ���ܹ�ʱ**: 5.5Сʱ

---

### 6.3 P2���Ż��������ڣ�

| ���� | ��ʱ | ������ | ״̬ |
|------|------|--------|------|
| ʵ��ͳһ���������˱� | 8h | ��� | ?? �ܹ�Ŀ�� |
| SignalTracker��ʽ������� | 4h | ��� | ?? �ܹ�Ŀ�� |
| ���Ӽ��ɲ��� | 4h | ���� | ?? ���滮 |
| �ֲ��˳����Լ�� | 2h | ҵ��+��� | ?? ��ȷ�� |

**Ԥ���ܹ�ʱ**: 18Сʱ

---

### 6.4 P3���Ż��������滮��

| ���� | ��ʱ | ������ | ״̬ |
|------|------|--------|------|
| �ļ������ع� | 2h | ��� | ?? ���滮 |
| ͳһ����ö��ʵ�� | 4h | ��� | ?? �ܹ�Ŀ�� |
| MCP governance resource�޸� | 4h | ��� | ?? ���滮 |

**Ԥ���ܹ�ʱ**: 10Сʱ

---

### 6.5 �ܹ�ʱ����

| ���ȼ� | ������ | �ܹ�ʱ | ������ |
|--------|--------|--------|----------|
| P0 | 2 | 1h | 50% (0.5h���) |
| P1 | 6 | 5.5h | 0% |
| P2 | 4 | 18h | 0% |
| P3 | 3 | 10h | 0% |
| **�ϼ�** | **15** | **34.5h** | **1.4%** |

---

## 7. �ؼ������ܽ�

### 7.1 �ش���

1. **? ���Թ�����ȫ��������**
   - 23,008������
   - ֤��������
   - Hard gate�ϸ�ͨ����0.005%��

2. **? ��Ϲ�����Bug**
   - ���ݿ�·������
   - ��ΪBLOCKED
   - ���޸�

3. **?? 3���ܹ�����**
   - ���׾ֲ�����
   - Quality Session������
   - SignalTrackerȱλ����

---

### 7.2 ��������

1. **�ܹ��������**
   - �Ĺ���ְ������
   - ֤��������
   - �������ڹ淶��ȷ

2. **������������**
   - ��淶�߶�һ�£�85%��
   - ģ�黯���
   - ����չ��ǿ

3. **�ĵ�����**
   - 10�ݹ淶�ĵ�
   - ���Ǽܹ�����ά
   - ��ִ����ǿ��90%��

---

### 7.3 ��Ҫ�Ľ��ķ���

1. **���ù���**
   - ·��Ӳ����
   - ȱ��ͳһ��������

2. **�ɹ۲���**
   - ȱ��ͳһ���������˱�
   - SignalTracker״̬����ʽ

3. **���Ը���**
   - ȱ�ټ��ɲ���
   - ��Ϲ���δ����ʵ������֤

---

## 8. �ж�����

### 8.1 �����ж������죩

1. ? **�ύ��Ͻű��޸�**
   ```bash
   git add scripts/factories/diagnose_factory_health.py
   git commit -m "fix(factory-diagnostics): �޸���Ͻű����ݿ�·������"
   ```

2. ?? **����CHANGELOG**
   - ��¼Bug�޸�
   - ��¼Ӱ�췶Χ

---

### 8.2 �����ж������ܣ�

1. **�����ĵ�**
   - �������ݿ�·������˵��
   - ����ʾ�������ʽ
   - ���佡��״̬����

2. **�Ż���Ϲ���**
   - ���������Ķ�ȡ·��
   - ����������֤����

---

### 8.3 �����ж������£�

1. **ʵ��ͳһ���������˱�**
   - ��ƽӿ�
   - ʵ�ֲ�ѯ�߼�
   - ����API

2. **��ʽ�������**
   - SignalTracker״̬���
   - ���ӵ���������

3. **���Ӽ��ɲ���**
   - ��ʵ������֤
   - �Զ�������

---

### 8.4 �����ж��������滮��

1. **�ܹ��Ż�**
   - ͳһ����ö��
   - Quality Session����
   - MCP resource�޸�

2. **�ļ��ع�**
   - ��������ʷծ���ļ�
   - ͳһ�����淶

---

## 9. ��¼

### 9.1 ��鷽��˵��

�������ʹ�����·�����

1. **�ܹ����**
   - �Ķ�10�ݹ淶�ĵ�
   - Graphify����ͼ�׷���
   - �ⲿMLOps/NIST���϶Ա�

2. **�淶�Ա�**
   - ����Աȹ淶�����
   - ��֤״̬������
   - �����Լһ����

3. **ʵ��������֤**
   - ������Ͻű�
   - SQL��ѯ��֤����
   - ֤���������Լ��

4. **���뾲̬����**
   - �ļ��ṹ����
   - �����淶���
   - ������ϵ����

---

### 9.2 ������Դ

1. **Դ����**
   - `packages/strategy-factory/`
   - `packages/aiask-quant-core/`
   - `scripts/factories/`

2. **���ݿ�**
   - `data/db/akshare_mcp.sqlite3`
   - 152����
   - 156 MB����

3. **�ĵ�**
   - `docs/factory-architecture/` (12���ļ�)
   - `.codex/skills/aiask-strategy-factory/references/`

4. **����**
   - Graphify����ͼ��
   - AKShare MCP resources
   - ��Ͻű�

---

### 9.3 �ο��ĵ�

1. [00-�������Ĺ����ھ��þ�](00-�������Ĺ����ھ��þ�.md)
2. [01-��ǰʵ�ʼܹ�](01-��ǰʵ�ʼܹ�.md)
3. [02-���Թ���ȫ��·�������ڹ淶](02-���Թ���ȫ��·�������ڹ淶.md)
4. [03-�Ĺ������й淶](03-�Ĺ������й淶.md)
5. [04-SignalTracker��֤�ݱջ��淶](04-SignalTracker��֤�ݱջ��淶.md)
6. [05-�����������޸�·��ͼ](05-�����������޸�·��ͼ.md)
7. [06-����������ֲ�](06-����������ֲ�.md)
8. [07-�Ĺ���Ŀ����ҵ���ֵ](07-�Ĺ���Ŀ����ҵ���ֵ.md)
9. [08-�ⲿԭ����ο�ӳ��](08-�ⲿԭ����ο�ӳ��.md)
10. [09-��ȼܹ���鱨��](09-��ȼܹ���鱨��.md)
11. [10-�淶�������嵥](10-�淶�������嵥.md)
12. [SPECIFICATION_VS_CODE_ANALYSIS](SPECIFICATION_VS_CODE_ANALYSIS.md)
13. [DIAGNOSTIC_BUG_FIX_REPORT](DIAGNOSTIC_BUG_FIX_REPORT.md)

---

### 9.4 �������˵��

1. **δʹ��thinking MCP**
   - ��ǰ�Ựδ��¶thinking MCP server/resource/tool
   - �����治���Ƶ�����thinking MCP
   - ʹ�õ������Դ: ��ǰԴ�롢Graphify��AKShare MCP����������

2. **governance resource��ȡʧ��**
   - `resource://governance/system/report` ��ȡʧ��
   - ����Ϊresource server���쳣
   - �������汾����Ҫ����ɹ۲⽡����Լ

3. **ʵ����������Ϊ׼**
   - �������ݻ���2026-06-21��ʵ������״̬
   - ���ݿ����: 156 MB, 152����
   - ���Թ�������������

---

## 10. ������

### 10.1 ��������

**���Թ�������״̬**: ?? **PENDING_EVIDENCE** (���������У��ȴ���������)

**����**: ???? 4.0/5

**����**:

1. ? **�ܹ��������** - �Ĺ���ְ��������֤��������
2. ? **������������** - ��淶�߶�һ�£�������ʷծ��
3. ? **֤��������** - 23,008���ԣ�39,449��ǰ������֤��
4. ? **Hard gate�ϸ�** - ͨ����0.005%������Ԥ��
5. ? **��Ϲ���Bug** - �ѷ��ֲ��޸�
6. ?? **3���ܹ�����** - ��Ҫ��ע������������

---

### 10.2 ��һ���ж�

**����ִ��**:
- �ύ��Ͻű��޸�
- ����CHANGELOG

**����ִ��**:
- �����ĵ�������˵����ʾ����ʽ������״̬��
- �Ż���Ϲ��ߣ��������ġ���֤���ߣ�

**����ִ��**:
- ʵ��ͳһ���������˱�
- SignalTracker��ʽ�������
- ���Ӽ��ɲ���

---

### 10.3 ǩ��

**��鸺����**: AI Assistant  
**�������**: 2026-06-21  
**����汾**: 1.0  
**���״̬**: ? �����

---

**�������**
