"""策略工厂状态、任务合同与目标池工具。"""

from strategy_factory._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'targets_parts', ['matching.py', 'selection.py'], future_annotations=True)
