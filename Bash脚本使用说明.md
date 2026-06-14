# 策略工厂Bash脚本使用说明

**生成时间**: 2026-06-13 12:40

---

## 📁 生成的脚本

### 1. `start_four_factories_24h.sh` - 启动脚本

**功能**: 启动策略工厂四工厂24小时集成会话

**包含的工厂**:
- StrategyFactory（策略工厂）
- FactorMiningFactory（因子挖掘）
- IncubationFactory（孵化工厂）  
- SignalTracker（信号追踪）

### 2. `stop_all_factories.sh` - 停止脚本

**功能**: 优雅地停止所有策略工厂相关进程

---

## 🚀 快速使用

### 启动24小时会话

```bash
# 方式1：直接运行
bash start_four_factories_24h.sh

# 方式2：如果已设置可执行权限
./start_four_factories_24h.sh
```

### 停止所有服务

```bash
# 方式1：直接运行
bash stop_all_factories.sh

# 方式2：如果已设置可执行权限
./stop_all_factories.sh
```

---

## ⚙️ 配置参数（在脚本中修改）

### start_four_factories_24h.sh 配置区

```bash
# 运行参数
HOURS=24              # 运行时长（小时）
PAUSE_SEC=60          # 轮间暂停（秒）
UNIVERSE_LIMIT=300    # 股票池大小
WITH_INCUBATION=true  # 启用孵化工厂
```

**修改方法**:
1. 用文本编辑器打开 `start_four_factories_24h.sh`
2. 找到"配置区"部分
3. 修改参数值
4. 保存并运行

---

## 📊 脚本特性

### 启动脚本特性

✅ **智能检查**
- 检查现有进程，避免重复启动
- 验证Python环境
- 验证必需脚本存在

✅ **优雅启动**
- 自动生成会话ID（带时间戳）
- 后台运行（使用nohup）
- 自动记录PID
- 验证启动成功

✅ **友好输出**
- 彩色日志输出
- 详细的状态信息
- 常用命令提示

### 停止脚本特性

✅ **多重保护**
- 优先从PID文件停止
- 按进程名模式查找停止
- 优雅停止（TERM信号）
- 超时后强制停止（KILL信号）

✅ **完整清理**
- 停止所有相关进程
- 清理PID文件
- 验证清理结果
- 显示残留进程（如有）

---

## 📋 启动后的常用操作

### 查看实时日志

```bash
# 策略工厂日志
tail -f logs/factory_24h_prod_*.log

# 监控脚本日志
tail -f logs/monitor_24h_prod_*.log
```

### 检查运行状态

```bash
# 查看进程
ps aux | grep run_strategy_factory

# 查看最新轮次
tail -50 logs/factory_24h_prod_*.log | grep completed
```

### 查看数据库进度

```bash
F:/Python311/python.exe -c "
import sqlite3
conn = sqlite3.connect('data/db/akshare_mcp.sqlite3')
cur = conn.cursor()
cur.execute('''
SELECT COUNT(*), 
       SUM(CAST(json_extract(summary, '$.submitted') AS INTEGER)),
       SUM(CAST(json_extract(summary, '$.gate_3_passed') AS INTEGER))
FROM strategy_factory_runs
WHERE started_at >= datetime('now', '-24 hours')
  AND completed_at IS NOT NULL
''')
row = cur.fetchone()
print(f'近24小时: 轮数={row[0]}, 提交={row[1]}, G3通过={row[2]}')
conn.close()
"
```

---

## 🔧 故障排查

### 启动失败

**症状**: 脚本显示"启动失败"

**排查步骤**:
1. 查看日志: `tail -100 logs/factory_24h_prod_*.log`
2. 检查Python环境: `packages/akshare-mcp/.venv/Scripts/python.exe --version`
3. 检查脚本存在: `ls scripts/factories/run_strategy_factory_quality_session.py`

### 进程意外停止

**症状**: 运行一段时间后进程消失

**排查步骤**:
1. 查看日志最后部分: `tail -100 logs/factory_24h_*.log | grep -i "error\|exception"`
2. 检查系统资源: `free -h` 和 `df -h`
3. 检查数据库状态

### 停止脚本无法停止某些进程

**症状**: 停止脚本显示残留进程

**手动停止**:
```bash
# 查看进程PID
ps aux | grep run_strategy_factory | grep -v grep

# 手动终止（替换12345为实际PID）
kill -9 12345
```

---

## 📈 预期结果（24小时）

| 指标 | 预期值 |
|------|-------:|
| 完成轮数 | 50-80轮 |
| 提交策略 | 750-1200个 |
| G3通过（43%） | 320-520个 |
| 因子挖掘 | 5-8轮 |

---

## 🎯 脚本优势

### vs 手动命令

| 特性 | 手动命令 | Bash脚本 |
|------|---------|---------|
| 重复使用 | 每次输入 | 一行启动 |
| 参数记忆 | 易忘记 | 集中配置 |
| 错误处理 | 手动检查 | 自动验证 |
| 日志管理 | 手动指定 | 自动生成 |
| 进程清理 | 逐个查找 | 一键清理 |

---

## 📝 自定义建议

### 场景1：快速测试（2小时）

修改 `start_four_factories_24h.sh`:
```bash
HOURS=2
PAUSE_SEC=30
UNIVERSE_LIMIT=100
```

### 场景2：大规模验证（48小时）

修改 `start_four_factories_24h.sh`:
```bash
HOURS=48
PAUSE_SEC=120
UNIVERSE_LIMIT=500
```

### 场景3：不启用孵化工厂

修改 `start_four_factories_24h.sh`:
```bash
WITH_INCUBATION=false
```

---

## 🔐 安全提示

1. **不要在生产环境直接测试**
   - 先在测试环境验证
   - 确认数据库备份

2. **监控系统资源**
   - CPU使用率
   - 内存占用
   - 磁盘空间

3. **定期检查日志**
   - 每2-4小时检查一次
   - 关注错误和异常

---

## 📞 支持

**遇到问题?**

1. 查看完整文档: `策略工厂四工厂24小时启动指南.md`
2. 查看测试报告: `策略工厂v10完整运行报告-20260613-final.md`
3. 查看日志文件: `logs/factory_24h_*.log`

---

**脚本生成时间**: 2026-06-13 12:40  
**验证状态**: ✅ 已在v10测试中验证  
**推荐配置**: HOURS=24, PAUSE_SEC=60, UNIVERSE_LIMIT=300
