import { Badge, DataTable, SectionCard } from '@/components/ui';
import { executionChipButtonCls } from '@/app/execution/components/execution-panel-styles';
import type { ExecutionTasksResponse } from '@aiask/shared-types';

type ExecutionTasksPanelProps = {
  executionTasks: ExecutionTasksResponse['tasks'];
  onRefresh: () => void;
  onSelectTask: (taskId: string, artifactId: string) => void;
};

export default function ExecutionTasksPanel({
  executionTasks,
  onRefresh,
  onSelectTask,
}: ExecutionTasksPanelProps) {
  return (
    <SectionCard className="mb-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="m-0 font-medium">执行任务列表</h3>
          <p className="mb-0 mt-1 text-xs text-text-secondary">
            这里展示 execution_manager.list 返回的任务，点选后会刷新当前详情和执行制品结果。
          </p>
        </div>
        <button type="button" onClick={onRefresh} className={executionChipButtonCls}>
          刷新任务
        </button>
      </div>
      <DataTable
        rows={executionTasks as unknown as Record<string, unknown>[]}
        emptyText="暂无执行任务"
        searchable
        rowKey="taskId"
        onRowClick={(row) => onSelectTask(String(row.taskId ?? '').trim(), String(row.artifactId ?? '').trim())}
        columns={[
          { key: 'taskId', label: '任务 ID' },
          { key: 'artifactId', label: '执行制品' },
          { key: 'code', label: '标的' },
          { key: 'algorithm', label: '算法' },
          { key: 'status', label: '状态' },
          { key: 'warningCount', label: '告警' },
          {
            key: 'createdAt',
            label: '创建时间',
            render: (value: unknown) => String(value ?? '').slice(0, 16) || '-',
          },
        ]}
        mobileCardRender={(row) => (
          <div className="space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">{String(row.taskId ?? '-')}</div>
                <div className="text-xs text-text-secondary">
                  {String(row.code ?? '-')} · {String(row.algorithm ?? '-')}
                </div>
              </div>
              <Badge variant={String(row.status ?? '').includes('completed') ? 'success' : 'neutral'}>
                {String(row.status ?? '-')}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
              <div>执行制品：{String(row.artifactId ?? '-')}</div>
              <div>告警：{String(row.warningCount ?? 0)}</div>
            </div>
          </div>
        )}
      />
    </SectionCard>
  );
}
