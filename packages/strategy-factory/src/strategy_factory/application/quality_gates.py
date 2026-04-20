"""策略工厂分级门禁。

Gate-0: 结构校验 — JSON 合法、strategy_type 合法、DSL 可编译
Gate-1: 快速筛选 — 少量代表性股票快速回测
Gate-2: 完整回测 — 仅对 Gate-1 Top-K 执行（复用 BacktestFilter）
Gate-3: 提交门禁 — 质量报告 + 风险报告 + 去重（委托 submission_gate / submitter 调用）
"""

from .precompile_contract import validate_precompile_candidate_contract
from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'quality_gates_parts', ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py'], future_annotations=True)
