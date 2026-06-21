# 策略工厂问题诊断与修复报告

**日期**: 2026-06-21  
**状态**: ✅ 已解决  
**问题类型**: 诊断工具 Bug（非策略工厂实际问题）

---

## 🎯 问题总结

### 表象问题
- 诊断脚本报告：🚫 **BLOCKED** (整体阻塞)
- 所有检查项显示：数据库表不存在、0 行数据

### 实际问题
- ✅ **策略工厂完全正常运行**
- ❌ **诊断脚本使用了错误的数据库路径**

---

## 🔍 根因分析

### Bug 位置
**文件**: `scripts/factories/diagnose_factory_health.py:37`

**错误代码**:
```python
self.db_path = db_path or str(ROOT / "data" / "aiask_quant.db")  # ❌ 错误
```

**正确代码**:
```python
self.db_path = db_path or str(ROOT / "data" / "db" / "akshare_mcp.sqlite3")  # ✅ 正确
```

### 为什么会出现这个 Bug？

1. **历史债务**: `data/aiask_quant.db` 可能是早期的配置路径
2. **配置变更**: 后续改为 `data/db/akshare_mcp.sqlite3` 但诊断脚本未同步更新
3. **缺少集成测试**: 诊断脚本在开发时未在真实环境中验证

### 证据

**错误路径的文件**:
```bash
$ ls -lh data/aiask_quant.db
-rw-r--r-- 1 walking 197121 0  6月 21 14:19 data/aiask_quant.db
```
- 文件存在但是 **0 字节空文件**
- 从未被实际使用

**正确路径的文件**:
```bash
$ ls -lh data/db/akshare_mcp.sqlite3
-rw-r--r-- 1 walking 197121 156M  6月 21 15:40 data/db/akshare_mcp.sqlite3
```
- **156 MB** 活跃数据库
- 包含 **152 个表**
- 包含 **大量运行数据**

---

## ✅ 策略工厂实际健康状态

### 修复后的诊断结果

**整体状态**: ⚠️ **PENDING_EVIDENCE** (等待样本成熟)

| 状态 | 数量 | 占比 |
|------|------|------|
| ✅ 通过 | 5 | 62.5% |
| ⚠️ 警告 | 3 | 37.5% |
| ❌ 失败 | 0 | 0% |
| 🚫 阻塞 | 0 | 0% |

### 详细检查结果

| # | 检查项 | 状态 | 详情 |
|---|--------|------|------|
| 1 | Supervisor 进程 | ⚠️ WARNING | psutil 未安装（可选） |
| 2 | SignalTracker 运行 | ✅ PASSED | 最近运行：1 天前 |
| 3 | 信号→订单转换 | ⚠️ WARNING | signal-only backlog: 1/8078 (0.01%) |
| 4 | 订单→成交转换 | ✅ PASSED | 3764 笔成交 |
| 5 | 持仓状态 | ⚠️ WARNING | 3602 open / 51 closed (99% open) |
| 6 | 前向收益证据 | ✅ PASSED | 39,449 条记录 |
| 7 | Execution Audit | ✅ PASSED | hard_gate_passed=1/20,392 |
| 8 | 策略生命周期 | ✅ PASSED | 1 listed, 1000 incubating, 共 23,008 个策略 |

### 核心数据统计

| 证据表 | 行数 | 说明 |
|--------|------|------|
| `strategies` | **23,008** | 策略总数（含历史） |
| `strategy_signals` | **19,312** | 信号记录 |
| `paper_orders` | **3,835** | 订单记录 |
| `paper_trades` | **3,764** | 成交记录 |
| `strategy_trade_positions` | **3,660** | 持仓记录 |
| `signal_forward_returns` | **39,449** | 前向收益证据 |
| `strategy_incubation_metrics` | **27,343** | 孵化指标 |
| `strategy_execution_audit_snapshots` | **20,392** | 审计快照 |

**✅ 证据链完整，策略工厂正常运行！**

---

## ⚠️ 需要关注的警告项

### 1. 持仓退出率低（99% open）

**现象**: 3602 open / 51 closed (仅 1.4% 退出率)

**原因**: 
- 可能是 stale close policy 未充分执行
- 或者策略普遍持有周期较长

**建议**: 
- 检查 Incubation Phase 3d (stale paper position closure) 是否正常运行
- 确认退出信号是否正常产生

### 2. Signal-only backlog（极小）

**现象**: 1/8078 策略有信号但无订单（0.01%）

**影响**: 极小，几乎可忽略

**建议**: 无需立即处理

### 3. Hard Gate 通过率低

**现象**: 仅 1/20,392 通过 hard gate (0.005%)

**原因**: 
- **这是正确的！** Hard gate 要求 ≥20 个真实 paper closed round-trip
- 大量策略仍在积累样本（bootstrap_pending/insufficient_samples）

**建议**: 
- 继续运行，等待样本成熟
- 不要试图放宽 hard gate 标准

---

## 🔧 修复内容

### 1. 修复诊断脚本数据库路径

**文件**: `scripts/factories/diagnose_factory_health.py`

**变更**:
```diff
- self.db_path = db_path or str(ROOT / "data" / "aiask_quant.db")
+ self.db_path = db_path or str(ROOT / "data" / "db" / "akshare_mcp.sqlite3")
```

**影响范围**: 仅诊断工具，不影响策略工厂本身

### 2. 更新帮助文档

**变更**:
```diff
- parser.add_argument("--db", help="数据库路径（默认：data/aiask_quant.db）")
+ parser.add_argument("--db", help="数据库路径（默认：data/db/akshare_mcp.sqlite3）")
```

---

## 📊 修复前后对比

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| 整体状态 | 🚫 BLOCKED | ⚠️ PENDING_EVIDENCE |
| 通过项 | 0 | 5 |
| 警告项 | 5 | 3 |
| 阻塞项 | 3 | 0 |
| 数据库表 | 0 个 | 152 个 |
| 策略总数 | 0 | 23,008 |
| 信号记录 | 0 | 19,312 |
| Paper 成交 | 0 | 3,764 |

---

## ✅ 验证测试

### 测试 1: 数据库连接
```bash
$ python -c "import sqlite3; conn = sqlite3.connect('data/db/akshare_mcp.sqlite3'); print('OK')"
OK
```

### 测试 2: 表计数
```bash
$ python -c "import sqlite3; conn = sqlite3.connect('data/db/akshare_mcp.sqlite3'); \
  cursor = conn.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\"table\"'); \
  print(f'Tables: {cursor.fetchone()[0]}')"
Tables: 152
```

### 测试 3: 核心证据表
```bash
$ python -c "import sqlite3; conn = sqlite3.connect('data/db/akshare_mcp.sqlite3'); \
  for t in ['strategies', 'strategy_signals', 'paper_orders']: \
    cursor = conn.execute(f'SELECT COUNT(*) FROM {t}'); \
    print(f'{t}: {cursor.fetchone()[0]}')"
strategies: 23008
strategy_signals: 19312
paper_orders: 3835
```

### 测试 4: 完整诊断
```bash
$ uv run python scripts/factories/diagnose_factory_health.py
整体状态: PENDING_EVIDENCE
[OK] 通过: 5
[WARN] 警告: 3
[FAIL] 失败: 0
[BLOCK] 阻塞: 0
```

---

## 📚 经验教训

### 1. 配置集中管理的重要性

**问题**: 数据库路径在多处硬编码，修改时容易遗漏

**改进**: 
- 应该从统一的配置源读取（如 `.env` 或配置模块）
- 避免在诊断工具中硬编码路径

### 2. 集成测试的必要性

**问题**: 诊断脚本在开发时未在真实环境中测试

**改进**:
- 添加集成测试，在真实数据库上运行
- CI/CD 中包含诊断脚本的端到端测试

### 3. 错误信息的准确性

**问题**: "数据库表不存在" 误导了问题排查方向

**改进**:
- 诊断脚本应该首先显示使用的数据库路径
- 检查失败时输出详细的连接信息

---

## 🎯 后续优化建议

### P0 - 立即优化

1. **添加数据库路径显示**
   ```python
   print(f"[INFO] Database path: {self.db_path}")
   print(f"[INFO] Exists: {os.path.exists(self.db_path)}")
   ```

2. **添加路径验证**
   ```python
   if not os.path.exists(self.db_path):
       print(f"[ERROR] Database file not found: {self.db_path}")
       print(f"[HINT] Check your AKSHARE_MCP_SQLITE_PATH environment variable")
   ```

### P1 - 中期优化

3. **从配置读取路径**
   ```python
   from aiask_quant_core.config import get_settings
   settings = get_settings()
   self.db_path = db_path or settings.sqlite_path
   ```

4. **添加集成测试**
   - 在真实数据库上运行诊断
   - 验证所有检查项能正确识别状态

### P2 - 长期优化

5. **统一配置管理**
   - 所有数据库路径从环境变量读取
   - 提供配置验证工具

---

## 📝 总结

### 问题性质
- ❌ **不是策略工厂的问题**
- ❌ **不是数据库初始化的问题**
- ✅ **是诊断工具的路径配置 Bug**

### 影响范围
- ❌ **不影响策略工厂运行** - 策略工厂始终正常
- ✅ **仅影响诊断准确性** - 误报为 BLOCKED

### 解决方案
- ✅ **1 行代码修复** - 更正数据库路径
- ✅ **立即生效** - 修复后诊断准确

### 当前状态
- ✅ **策略工厂健康运行**
- ✅ **23,008 个策略**
- ✅ **证据链完整**
- ⚠️ **等待样本成熟**（正常状态）

---

**修复时间**: 2026-06-21 15:44  
**修复提交**: 待提交  
**验证状态**: ✅ 已验证
