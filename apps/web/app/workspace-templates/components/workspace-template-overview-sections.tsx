import { Badge, SectionCard } from '@/components/ui';
import {
  previewTemplateWorkflow,
  type WorkspaceTemplateRunRecord,
  type WorkspaceTemplateWorkflowId,
} from '@/store/workbench-store';
import { WORKFLOW_OPTIONS, contextChips } from './workspace-template-support';

type WorkflowOption = (typeof WORKFLOW_OPTIONS)[number];
type WorkflowPreview = ReturnType<typeof previewTemplateWorkflow>;

type WorkspaceTemplateContextCardProps = {
  baseContextChips: string[];
};

export function WorkspaceTemplateContextCard({ baseContextChips }: WorkspaceTemplateContextCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
        <div>
          <div className="text-sm font-medium text-text-primary">当前工作区上下文</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {baseContextChips.length > 0 ? (
              baseContextChips.map((chip) => (
                <Badge key={chip} variant="neutral">
                  {chip}
                </Badge>
              ))
            ) : (
              <span className="text-xs text-text-secondary">
                当前工作区没有显式上下文，模板会按默认命名和默认参数展开。
              </span>
            )}
          </div>
          <p className="mb-0 mt-3 text-sm leading-6 text-text-secondary">
            工作区模板用于“一键新建完整工作区”，任务模板用于“向当前工作区注入一组流程任务”。现在两者都支持覆盖股票、账户、执行、组合、窗口等参数，不再局限于固定注入。
          </p>
        </div>
        <div className="rounded-xl border border-glass-border bg-surface-alt/40 p-3 text-xs text-text-secondary">
          <div className="font-medium text-text-primary">使用建议</div>
          <ol className="mb-0 mt-2 space-y-1 pl-4">
            <li>先基于当前工作区上下文选择最接近的模板。</li>
            <li>再只覆盖当前这次编排真正需要改变的参数，避免污染原始工作区上下文。</li>
            <li>确认预览链接和步骤正确后，再创建工作区或注入任务。</li>
          </ol>
        </div>
      </div>
    </SectionCard>
  );
}

type TemplateWorkflowCatalogCardProps = {
  selectedWorkflowId: WorkspaceTemplateWorkflowId;
  onSelect: (workflowId: WorkspaceTemplateWorkflowId) => void;
};

export function TemplateWorkflowCatalogCard({
  selectedWorkflowId,
  onSelect,
}: TemplateWorkflowCatalogCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-text-primary">跨模板工作流</div>
          <div className="mt-1 text-xs text-text-secondary">
            把 blueprint 和 task template 串成一条执行链，支持依赖条件、默认值策略和组合执行。
          </div>
        </div>
        <Badge variant="info">{WORKFLOW_OPTIONS.length} 个工作流</Badge>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        {WORKFLOW_OPTIONS.map((workflow) => (
          <div
            key={workflow.id}
            className={`rounded-xl border p-3 ${selectedWorkflowId === workflow.id ? 'border-primary bg-primary/5' : 'border-glass-border bg-surface-alt/40'}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">{workflow.label}</div>
                <div className="mt-1 text-xs leading-5 text-text-secondary">{workflow.description}</div>
              </div>
              <button
                type="button"
                onClick={() => onSelect(workflow.id)}
                className="rounded border border-glass-border px-3 py-1 text-xs"
              >
                预览
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="neutral">{workflow.steps.length} 步</Badge>
              <Badge variant="neutral">
                {workflow.steps.filter((step) => step.kind === 'blueprint').length} 个工作区步骤
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

type TemplateWorkflowPreviewCardProps = {
  selectedWorkflow: WorkflowOption;
  selectedWorkflowPreview: WorkflowPreview;
  hasWorkflowErrors: boolean;
  onApplyWorkflow: (workflowId: WorkspaceTemplateWorkflowId) => void;
};

export function TemplateWorkflowPreviewCard({
  selectedWorkflow,
  selectedWorkflowPreview,
  hasWorkflowErrors,
  onApplyWorkflow,
}: TemplateWorkflowPreviewCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-text-primary">{selectedWorkflow.label}</div>
          <div className="mt-1 text-xs text-text-secondary">
            可执行 {selectedWorkflowPreview.executableStepCount} 步，阻塞 {selectedWorkflowPreview.blockedStepCount}{' '}
            步，跳过 {selectedWorkflowPreview.skippedStepCount} 步。
          </div>
        </div>
        <button
          type="button"
          onClick={() => onApplyWorkflow(selectedWorkflow.id)}
          disabled={hasWorkflowErrors || selectedWorkflowPreview.executableStepCount === 0}
          className="rounded border border-primary px-3 py-1.5 text-xs text-primary disabled:opacity-50"
        >
          执行工作流
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {selectedWorkflowPreview.workspaceName ? (
          <Badge variant="neutral">目标工作区 {selectedWorkflowPreview.workspaceName}</Badge>
        ) : null}
        <Badge variant="neutral">新建工作区 {selectedWorkflowPreview.createdWorkspaceCount} 个</Badge>
        <Badge variant="neutral">最终上下文 {contextChips(selectedWorkflowPreview.context).length} 项</Badge>
      </div>

      <div className="mt-4 space-y-3">
        {selectedWorkflowPreview.steps.map((step, index) => (
          <div key={step.id} className="rounded-xl border border-glass-border bg-surface/60 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-xs font-medium text-text-primary">
                  步骤 {index + 1} · {step.label}
                </div>
                <div className="mt-1 text-sm text-text-secondary">{step.description}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge
                  variant={step.status === 'ready' ? 'success' : step.status === 'blocked' ? 'warning' : 'neutral'}
                >
                  {step.status === 'ready' ? '可执行' : step.status === 'blocked' ? '阻塞' : '跳过'}
                </Badge>
                <Badge variant="neutral">{step.kind === 'blueprint' ? '工作区模板' : '任务模板'}</Badge>
                <Badge variant="neutral">默认值 {step.defaultsStrategy}</Badge>
              </div>
            </div>
            {step.reason ? <div className="mt-2 text-xs text-warning">{step.reason}</div> : null}
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-secondary">
              <span>目标：{step.targetLabel}</span>
              {step.dependsOn.length > 0 ? <span>依赖：{step.dependsOn.join(' / ')}</span> : null}
              {step.requiredAll.length > 0 ? <span>必填：{step.requiredAll.join(' / ')}</span> : null}
              {step.requiredAny.length > 0 ? <span>任一：{step.requiredAny.join(' / ')}</span> : null}
              {step.workspaceName ? <span>工作区：{step.workspaceName}</span> : null}
            </div>
            <div className="mt-3 space-y-2">
              {step.steps.map((task, taskIndex) => (
                <div
                  key={`${step.id}-${taskIndex + 1}`}
                  className="rounded-lg border border-glass-border bg-surface px-3 py-2"
                >
                  <div className="text-[11px] font-medium text-text-primary">
                    {taskIndex + 1}. {task.pageKey}
                  </div>
                  <div className="mt-1 text-sm text-text-primary">{task.title}</div>
                  {task.href ? <div className="mt-1 break-all text-[11px] text-text-muted">{task.href}</div> : null}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

type TemplateRunsCardProps = {
  templateRuns: WorkspaceTemplateRunRecord[];
  latestTemplateRun: WorkspaceTemplateRunRecord | null;
  onClear: () => void;
  onSwitchWorkspace: (workspaceId: string) => void;
  onRollbackRun: (runId: string) => void;
};

export function TemplateRunsCard({
  templateRuns,
  latestTemplateRun,
  onClear,
  onSwitchWorkspace,
  onRollbackRun,
}: TemplateRunsCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-text-primary">模板运行态</div>
          <div className="mt-1 text-xs text-text-secondary">
            保留最近执行结果、运行记录和回滚快照，方便继续调整编排而不是盲试。
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="info">{templateRuns.length} 条记录</Badge>
          <button
            type="button"
            onClick={onClear}
            className="rounded border border-glass-border px-3 py-1 text-xs"
          >
            清空记录
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(320px,1.05fr)]">
        <div className="rounded-xl border border-glass-border bg-surface/60 p-4">
          <div className="text-sm font-medium text-text-primary">最近运行结果</div>
          {latestTemplateRun ? (
            <div className="mt-3 space-y-2 text-sm text-text-secondary">
              <div>
                名称：<span className="font-medium text-text-primary">{latestTemplateRun.label}</span>
              </div>
              <div>
                类型：<span className="font-medium text-text-primary">{latestTemplateRun.kind}</span>
              </div>
              <div>
                状态：<span className="font-medium text-text-primary">{latestTemplateRun.status}</span>
              </div>
              <div>
                摘要：<span className="font-medium text-text-primary">{latestTemplateRun.summary}</span>
              </div>
              <div>
                时间：
                <span className="font-medium text-text-primary">
                  {new Date(latestTemplateRun.createdAt).toLocaleString('zh-CN')}
                </span>
              </div>
              <div className="flex flex-wrap gap-2 pt-2">
                {latestTemplateRun.targetWorkspaceId ? (
                  <button
                    type="button"
                    onClick={() => onSwitchWorkspace(latestTemplateRun.targetWorkspaceId!)}
                    className="rounded border border-glass-border px-3 py-1 text-xs"
                  >
                    切到目标工作区
                  </button>
                ) : null}
                {latestTemplateRun.status === 'applied' ? (
                  <button
                    type="button"
                    onClick={() => onRollbackRun(latestTemplateRun.id)}
                    className="rounded border border-primary px-3 py-1 text-xs text-primary"
                  >
                    回滚最近执行
                  </button>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="mt-3 text-xs text-text-secondary">当前还没有模板执行记录。</div>
          )}
        </div>

        <div className="space-y-3">
          {templateRuns.length > 0 ? (
            templateRuns.map((run) => (
              <div key={run.id} className="rounded-xl border border-glass-border bg-surface/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium text-text-primary">{run.label}</div>
                    <div className="mt-1 text-[11px] text-text-secondary">
                      {new Date(run.createdAt).toLocaleString('zh-CN')}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={run.status === 'applied' ? 'success' : 'warning'}>{run.status}</Badge>
                    <Badge variant="neutral">{run.kind}</Badge>
                  </div>
                </div>
                <div className="mt-2 text-xs leading-5 text-text-secondary">{run.summary}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-text-secondary">
                  {run.createdWorkspaceIds.length > 0 ? <span>工作区 {run.createdWorkspaceIds.length} 个</span> : null}
                  {run.taskIds.length > 0 ? <span>任务 {run.taskIds.length} 条</span> : null}
                  {run.appliedStepIds.length > 0 ? <span>执行步骤 {run.appliedStepIds.length} 个</span> : null}
                  {run.skippedStepIds.length > 0 ? <span>跳过 {run.skippedStepIds.length} 个</span> : null}
                  {run.blockedStepIds.length > 0 ? <span>阻塞 {run.blockedStepIds.length} 个</span> : null}
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {run.targetWorkspaceId ? (
                    <button
                      type="button"
                      onClick={() => onSwitchWorkspace(run.targetWorkspaceId!)}
                      className="rounded border border-glass-border px-3 py-1 text-xs"
                    >
                      切到工作区
                    </button>
                  ) : null}
                  {run.status === 'applied' ? (
                    <button
                      type="button"
                      onClick={() => onRollbackRun(run.id)}
                      className="rounded border border-primary px-3 py-1 text-xs text-primary"
                    >
                      回滚到执行前
                    </button>
                  ) : null}
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-glass-border bg-surface/60 p-4 text-xs text-text-secondary">
              运行记录为空。执行任一工作流、工作区模板或任务模板后，这里会保留最近运行结果和回滚入口。
            </div>
          )}
        </div>
      </div>
    </SectionCard>
  );
}
