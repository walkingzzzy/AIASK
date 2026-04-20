"""因子研究专用大模型 provider。"""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'factor_llm_provider_parts', ['context.py', 'specs.py', 'runtime.py'], future_annotations=True)
