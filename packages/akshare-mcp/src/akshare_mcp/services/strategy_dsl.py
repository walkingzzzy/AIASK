"""策略 DSL：规范化、编译与条件求值。"""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'strategy_dsl_parts', ['context.py', 'specs.py', 'runtime.py'], future_annotations=True)
