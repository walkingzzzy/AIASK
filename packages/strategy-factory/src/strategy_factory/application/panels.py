"""策略工厂面板、验证与风险报告。"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'panels_parts', ['normalizers.py', 'policy.py', 'evaluation.py'], future_annotations=True)
