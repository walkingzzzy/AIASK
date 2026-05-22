"""多阶段 AI 策略生成 — Stage 定义与注册表。

每个 Stage 拥有:
- 专属 system prompt（短而聚焦）
- 输入/输出 JSON schema（用于验证）
- 独立 fallback 函数（LLM 不可用时降级到本地规则引擎）
- 独立的 max_tokens / temperature 配置
"""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'strategy_stages_parts', ['context.py', 'specs.py', 'runtime.py', 'postprocess.py'], future_annotations=True)
