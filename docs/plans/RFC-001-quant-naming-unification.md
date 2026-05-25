# RFC-001:quant_manager 4 命名空间统一(P2-4.2.1)

- **状态**: Draft
- **日期**: 2026-05-24
- **作者**: AIASK 维护团队
- **诊断报告锚点**: `MCP服务诊断报告-2026-05-24.md` §4.2.1

## 问题背景

22 场景红队复测 S16-F07 / S15-F08 / S15-F09 实测,`quant_manager` 4 个 action 对同一概念使用不同命名规则:

| Action | 接受 | 拒绝 | 备注 |
|---|---|---|---|
| `factor_ic` | `mom_60d` / `momentum` | `momentum_20d` | 走 SUPPORTED_FACTORS + 部分别名 |
| `batch_compute_factors` | `momentum` / `rsi` 6 大类 | `mom_60d` / `rsi_14` | 仅 6 大类 |
| `list_factors` | 50 个标准名 + aliases | — | 完整列表 |
| `calculate_factor` | `roe_ttm` / `pe_ttm` | `roe` / `pe_ratio` | 要求 `_ttm` 后缀 |

直接后果:AI 在不同 action 间切换时,同一 factor 名时通过时拒绝,严重损害体验。

## 已落地的代码侧修复

本轮代码侧已部分修复(`packages/akshare-mcp/src/akshare_mcp/tools/factor_naming.py` 新增 273 行):

1. 统一 resolver `resolve_factor_name(name, action)` — 接受任意 alias / 后缀 / 大小写,返回 canonical
2. `list_factor_aliases()` — 返回完整 canonical → list[alias] 映射
3. `check_factor_supported(name)` — 严格校验,失败时返回 suggestion
4. `list_factors` 顶层暴露 `alias_canonical_map` 和 `naming_note`,AI 一次性看到所有别名

**剩余待办**:让 4 个 action 入口统一调用 `resolve_factor_name`,这需要 RFC 流程协调:

## 完整 RFC

### 1. 设计原则

- **canonical 标准名**:50 个 SUPPORTED_FACTORS keys 作为 canonical 名
- **alias 一站式**:任何 action 入口接受任意 alias,内部归一化到 canonical
- **零 breaking change**:现有调用方仍可用旧名;新增 alias 不影响旧 canonical 行为
- **明确 deprecation**:不建议的别名(如 `momentum_20d`)在 docstring 中标注但不废弃

### 2. 实施步骤

#### 阶段 1:工具入口接入(本 RFC 完成代码骨架)

- ✅ 创建 `factor_naming.py` 模块
- ✅ `list_factors` 暴露 alias_canonical_map
- ⏳ `factor_ic` action 入口 `name = resolve_factor_name(name, action='factor_ic')`
- ⏳ `batch_compute_factors` 同上
- ⏳ `calculate_factor` 同上(去掉 `_ttm` 强制后缀)
- ⏳ 新增 `quant_manager.normalize_factor_name` action,供 AI 在调用前先归一化

#### 阶段 2:验收测试

```python
# tests/test_factor_naming.py(新增)
def test_factor_naming_resolver_cross_action():
    """诊断报告 §4.2.1 锁:同一 factor 在 4 个 action 都通过。"""
    from akshare_mcp.tools.factor_naming import resolve_factor_name

    assert resolve_factor_name("momentum_20d") == "momentum"
    assert resolve_factor_name("mom_60d") == "mom_60d"
    assert resolve_factor_name("rsi_14") == "rsi"
    assert resolve_factor_name("roe_ttm") == "roe"
    assert resolve_factor_name("pe_ttm") == "pe_ratio"
```

#### 阶段 3:回归测试

- 跑现有 `test_quant_*` 全套(确保不 break 旧行为)
- 跑 22 场景 S16-F07 / S15-F08 / S15-F09 三个 finding 验证消除

### 3. 不在本 RFC 范围

- factor 计算逻辑统一(各 action 实现细节)
- factor metadata schema 重构
- 新增/删除 factor

### 4. 验收标准

- 4 个 action 接受同一 factor name 输入返回 success
- list_factors 顶层有 alias_canonical_map
- 全部测试通过(316 + 新增 1)
- 诊断报告 §4.2.1 复测 finding 不再复现

## 实施工时估算

- 阶段 1(代码骨架):**已完成 80%**,剩余 4 个 action 入口接入约 2 小时
- 阶段 2(测试):2 小时
- 阶段 3(回归):4 小时
- 总计:**1 工作日**

## 风险评估

**低风险**:
- factor_naming.py 是 additive(新模块,不替换现有)
- list_factor_aliases 已包含现有 quant_definitions._normalize_factor_name 的全部映射
- 现有用户传入 canonical 名仍按旧路径走,无 breaking

**潜在风险**:
- 现有 `_normalize_factor_name` 把 `momentum_20d` → `momentum`,新模块保持一致(无变更)
- `roe_ttm` → `roe` 映射可能让原本要求 TTM 财务数据的工具拿到非 TTM 数据。**Mitigation**:`SUPPORTED_FACTORS["roe"]["requires_financials"]=True`,本身已处理 TTM 计算逻辑,前端别名映射不影响内部计算。

## 后续工单

- RFC-002:RSI 算法统一(Wilder's RSI(14))
- RFC-003:4 manager(alerts/watchlist/screener/save_strategy)user_id 强制传入
- RFC-004:mkt_cap 单位统一(元)
