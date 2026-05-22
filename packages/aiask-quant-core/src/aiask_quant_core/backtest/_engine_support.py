"""回测引擎 - BacktestEngine 核心类"""

from aiask_quant_core._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), '_engine_support_parts', ['runtime.py', 'execution.py'], future_annotations=False)
