# S20 · 工作流/skill/产业链

- **判定**: ✅ 通过 (Pass=3 / Degraded=1 / Fail=0)
- **关键修复验证**: 🎯 **§B8 + §2.4 + §3.7 三处完美修复**

| 工具 | 状态 | 关键发现 |
|---|---|---|
| `search_stocks(keyword="茅台")` | ✅ Pass | **§B8 完美修复确认** — 中文 keyword "茅台" 正确返回 1 条(600519 贵州茅台 / 酿酒 / 1644619 亿市值),v1 中文 normalize 不工作 finding 已消失 |
| `list_skills()` | ✅ Pass | **§3.7 完美修复确认** — 36 skills,executable_count=21 / registered_only_count=15,**顶层显式两个 count 字段**(v1 仅嵌套在 registry_summary,v2 提升到顶层)。executor_coverage_ratio=0.5833 / fallback_used=true `skills_registry_unavailable` codex_registry fallback 正常 |
| `get_industry_chain(keyword="新能源")` | ✅ Pass | matched=true,2 个 chains(new_energy + ev_auto),完整 upstream(锂矿/钴矿/镍矿/稀土/芯片)/ midstream(电池材料/正极/负极/电解液/隔膜/动力电池/电机/电控)/ downstream(新能源汽车/储能/充电桩/出口) |
| `search_by_kline(600519, 20d, top_n=10)` | ⚠️ Degraded | **§2.4 完美修复确认** — `excluded_st_count=6` + `quality_filter="st_delisted_excluded_at_input"` 显式生效(v1 §S20 high finding "search_by_kline 返回 *ST 退市股(无质量过滤)" 已修复)。10 个相似股票 100% 干净(永顺泰/燕京啤酒/山西汾酒/...),搜索 backend=db→python fallback `db_empty_result`,similarity 0.5927~0.8957 合理 |

## v1 → v2 Delta
- ✅ **§B8 search_stocks 中文 normalize 完美修复**(v1 中文搜索失败 → v2 完美工作)
- ✅ **§2.4 search_by_kline ST 退市股过滤完美修复**(v1 high finding "搜索结果包含退市股" → v2 excluded_st_count=6 + quality_filter 显式)
- ✅ **§3.7 list_skills executable_count 顶层暴露完美修复**(v1 嵌套深 → v2 顶层 + execution_gap 详细 15 个 skills 列表)
- ✅ get_industry_chain 关键词模糊匹配 2 个产业链(新能源 + 新能源汽车),涵盖上中下游完整
