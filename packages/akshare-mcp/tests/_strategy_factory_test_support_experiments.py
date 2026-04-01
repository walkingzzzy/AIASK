from __future__ import annotations

class _StrategyDBExperimentMixin:
    async def save_strategy_generation_experiment(self, experiment):
        payload = dict(experiment)
        existing = self._experiments.get(payload['experiment_id']) or {}
        item = {**existing, **payload}
        self._experiments[item['experiment_id']] = item
        return dict(item)

    async def get_strategy_generation_experiment(self, experiment_id):
        item = self._experiments.get(experiment_id)
        return dict(item) if item else None

    async def list_strategy_generation_experiments(self, strategy_id=None, parent_strategy_id=None, generated_strategy_id=None, task_run_id=None, status=None, source=None, limit=20):
        rows = list(self._experiments.values())
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id or row.get('parent_strategy_id') == strategy_id or row.get('generated_strategy_id') == strategy_id]
        if parent_strategy_id:
            rows = [row for row in rows if row.get('parent_strategy_id') == parent_strategy_id]
        if generated_strategy_id:
            rows = [row for row in rows if row.get('generated_strategy_id') == generated_strategy_id]
        if task_run_id is not None:
            rows = [row for row in rows if int(row.get('task_run_id') or 0) == int(task_run_id)]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        if source:
            rows = [row for row in rows if row.get('source') == source]
        return [dict(row) for row in rows[:limit]]

    async def save_strategy_task_run(self, run):
        item = {'id': len(self._task_runs) + 1, **dict(run)}
        self._task_runs.append(item)
        return dict(item)

    async def update_strategy_task_run(self, run_id, status=None, result=None, error=None, completed_at=None):
        for item in self._task_runs:
            if int(item.get('id')) == int(run_id):
                if status is not None:
                    item['status'] = status
                if result is not None:
                    item['result'] = result
                if error is not None:
                    item['error'] = error
                if completed_at is not None:
                    item['completed_at'] = completed_at
                return dict(item)
        return None

    async def list_strategy_task_runs(self, strategy_id=None, task_name=None, task_scope=None, status=None, limit=20):
        rows = list(self._task_runs)
        if strategy_id:
            rows = [row for row in rows if row.get('strategy_id') == strategy_id]
        if task_name:
            rows = [row for row in rows if row.get('task_name') == task_name]
        if task_scope:
            rows = [row for row in rows if row.get('task_scope') == task_scope]
        if status:
            rows = [row for row in rows if row.get('status') == status]
        return [dict(row) for row in rows[:limit]]
