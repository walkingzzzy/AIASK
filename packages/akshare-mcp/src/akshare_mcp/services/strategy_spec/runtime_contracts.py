"""Runtime-contract helpers for strategy specs."""

from akshare_mcp._fragment_loader import exec_fragments as _exec_fragments

_exec_fragments(globals(), 'runtime_contracts_parts', ['runtime_contract_models.py', 'runtime_contract_builders.py'], future_annotations=True)
