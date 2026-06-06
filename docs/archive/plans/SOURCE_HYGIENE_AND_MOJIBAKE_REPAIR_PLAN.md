# AIASK Source Hygiene And Mojibake Repair Plan

## Scope

本清单用于配合 OpenBB 借鉴能力平台化落地，先记录可安全执行的源码卫生事项，不和 provider contract / fetcher / quality gate 改造混成一次不可回滚的大清理。

## Cache Hygiene

- `.gitignore` 已覆盖 `__pycache__/`、`*.py[cod]`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`.venv/`、`venv/`、`desktop/node_modules/`、`desktop/dist/` 等生成物。
- 后续清理建议只清理工作区源码和测试目录下的 `__pycache__` / `.pyc`，不要清理 `packages/agent/.venv` 等虚拟环境内部缓存，避免影响本地解释器和依赖状态。
- PowerShell 安全清理建议先 dry-run 列表，再删除：

```powershell
Get-ChildItem -Path packages,desktop -Recurse -Directory -Filter __pycache__ |
  Where-Object { $_.FullName -notmatch '\\.venv\\|\\venv\\|\\node_modules\\' } |
  Select-Object -ExpandProperty FullName
```

## Mojibake Repair Priorities

优先修复用户可见、测试断言可见、工具描述可见的乱码文本，不优先改内部注释，避免大面积文本 churn。

- `packages/akshare-mcp/src/akshare_mcp/tools/tool_catalog.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/search.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/basic_data.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/technical.py`
- `packages/akshare-mcp/src/akshare_mcp/tools/finance.py`
- `packages/akshare-mcp/tests/test_provider_contracts.py`

## Safety Rules

- 不修复 `.pyc`、缓存、第三方依赖或 `.venv` 中的文本。
- 每次只修复一个模块域，并跑对应测试。
- 修复描述和 docstring 时保持工具名、参数名、返回 shape、错误码不变。
- 用户可见中文修复后，补一条测试或快照断言，防止乱码回流。
