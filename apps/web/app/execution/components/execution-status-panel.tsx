import Link from 'next/link';
import type { FormEventHandler } from 'react';
import { Badge, SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import { briefSummary } from '@/lib/execution-normalizers';
import {
  executionChipButtonCls,
  executionNoteCardCls,
  executionSidePanelCls,
} from '@/app/execution/components/execution-panel-styles';
import type { ExecutionArtifactResponse, ExecutionWorkbenchResponse } from '@aiask/shared-types';

type ExecutionStatusPanelProps = {
  currentExecutionId: string;
  executionIdInput: string;
  onExecutionIdChange: (value: string) => void;
  artifactIdInput: string;
  onArtifactIdChange: (value: string) => void;
  onStatusSubmit: FormEventHandler<HTMLFormElement>;
  onArtifactSubmit: FormEventHandler<HTMLFormElement>;
  executionWorkbench: ExecutionWorkbenchResponse | null;
  latestExecution: unknown;
  workbenchMessage: string | null;
  statusPayload: Record<string, unknown> | null;
  pendingOrderCount: number;
  artifactData: ExecutionArtifactResponse | null;
  currentArtifactId: string;
  executionWorkbenchError: string | null;
  taskDetailError: string | null;
  artifactError: string | null;
  onOpenArtifactDetail: (artifactId: string) => void;
  artifactDetailHref: string;
};

export default function ExecutionStatusPanel({
  currentExecutionId,
  executionIdInput,
  onExecutionIdChange,
  artifactIdInput,
  onArtifactIdChange,
  onStatusSubmit,
  onArtifactSubmit,
  executionWorkbench,
  latestExecution,
  workbenchMessage,
  statusPayload,
  pendingOrderCount,
  artifactData,
  currentArtifactId,
  executionWorkbenchError,
  taskDetailError,
  artifactError,
  onOpenArtifactDetail,
  artifactDetailHref,
}: ExecutionStatusPanelProps) {
  const workbenchWarnings = executionWorkbench?.warnings ?? [];
  const workbenchOrders = executionWorkbench?.orderContext?.recentOrders ?? [];
  const artifactDetailId = artifactData?.artifactId || currentArtifactId;

  return (
    <SectionCard className="mb-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="m-0 font-medium">执行状态</h3>
        <Badge variant={executionWorkbench?.overview ? 'success' : 'neutral'}>
          {currentExecutionId ? '可查询' : '等待 execution_id'}
        </Badge>
      </div>
      <form onSubmit={onStatusSubmit} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex min-w-[280px] flex-col gap-1 text-xs text-text-secondary">
          <span>execution_id</span>
          <input
            value={executionIdInput}
            onChange={(event) => onExecutionIdChange(event.target.value)}
            className="text-sm"
          />
        </label>
        <button type="submit" className={executionChipButtonCls}>
          查询状态
        </button>
      </form>
      <form onSubmit={onArtifactSubmit} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex min-w-[280px] flex-col gap-1 text-xs text-text-secondary">
          <span>artifact_id</span>
          <input
            value={artifactIdInput}
            onChange={(event) => onArtifactIdChange(event.target.value)}
            className="text-sm"
          />
        </label>
        <button type="submit" className={executionChipButtonCls}>
          查询 artifact
        </button>
      </form>
      {executionWorkbenchError ? <p className="mt-2 text-xs font-medium text-danger">{executionWorkbenchError}</p> : null}
      {taskDetailError ? <p className="mt-2 text-xs font-medium text-danger">{taskDetailError}</p> : null}
      {artifactError ? <p className="mt-2 text-xs font-medium text-danger">{artifactError}</p> : null}
      {workbenchMessage && !executionWorkbench?.overview ? (
        <div className={`${executionNoteCardCls} mt-3`}>{workbenchMessage}</div>
      ) : null}
      {latestExecution ? (
        <div className={`${executionSidePanelCls} mt-3`}>
          <div className="text-sm font-medium text-text-primary">最近一次执行返回</div>
          <div className="mt-2 text-xs text-text-secondary">{briefSummary((latestExecution as Record<string, unknown>).execution ?? latestExecution)}</div>
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-text-secondary">查看原始返回</summary>
            <pre className="mb-0 mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-[11px]">
              {JSON.stringify(latestExecution, null, 2)}
            </pre>
          </details>
        </div>
      ) : null}
      {executionWorkbench?.overview ? (
        <div className={`${executionSidePanelCls} mt-3`}>
          <div className="text-sm font-medium text-text-primary">执行工作台结果</div>
          <div className="mt-2 text-xs text-text-secondary">{workbenchMessage || briefSummary(statusPayload)}</div>
          <div className="mt-3 grid gap-3 2xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.9fr)]">
            <div className={executionNoteCardCls}>
              <div className="text-xs font-medium text-text-primary">结构化摘要</div>
              <div className="mt-2 text-xs leading-6 text-text-secondary">
                任务 {executionWorkbench.overview.executionId || '-'}，状态 {executionWorkbench.overview.status || '-'}
                ，算法 {executionWorkbench.overview.algorithm || '-'}，告警 {executionWorkbench.overview.warningCount ?? 0} 条。
              </div>
              {workbenchWarnings.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {workbenchWarnings.slice(0, 3).map((item) => (
                    <div key={item.id} className="panel-soft rounded-[18px] px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs font-medium text-text-primary">{item.title}</div>
                        <Badge
                          variant={
                            item.severity === 'high'
                              ? 'warning'
                              : item.severity === 'medium'
                                ? 'neutral'
                                : 'success'
                          }
                        >
                          {item.severity || 'unknown'}
                        </Badge>
                      </div>
                      {item.message ? <div className="mt-1 text-xs text-text-secondary">{item.message}</div> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
            <div className={executionNoteCardCls}>
              <div className="text-xs font-medium text-text-primary">账户上下文</div>
              <div className="mt-2 space-y-2 text-xs text-text-secondary">
                <div>账户：{executionWorkbench.orderContext?.accountId || '-'}</div>
                <div>挂单：{executionWorkbench.orderContext?.pendingOrderCount ?? pendingOrderCount}</div>
                <div>持仓：{executionWorkbench.orderContext?.positionsCount ?? '-'}</div>
                <div>
                  总资产：
                  {executionWorkbench.orderContext?.totalValue != null
                    ? fmtNum(executionWorkbench.orderContext.totalValue)
                    : '-'}
                </div>
              </div>
              {workbenchOrders.length > 0 ? (
                <div className="panel-soft mt-3 rounded-[18px] p-2">
                  <div className="text-xs font-medium text-text-primary">最近订单</div>
                  <div className="mt-2 space-y-2">
                    {workbenchOrders.slice(0, 3).map((item) => (
                      <div key={item.id} className="flex items-center justify-between gap-2 text-xs text-text-secondary">
                        <span>
                          {item.code || '-'} · {item.direction || '-'}
                        </span>
                        <span>{item.status || '-'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          {statusPayload && Object.keys(statusPayload).length > 0 ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-text-secondary">查看状态原始数据</summary>
              <pre className="mb-0 mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-[11px]">
                {JSON.stringify(statusPayload, null, 2)}
              </pre>
            </details>
          ) : null}
        </div>
      ) : executionWorkbenchError ? null : (
        <p className="mt-3 text-sm text-text-secondary">查询执行状态中...</p>
      )}
      {artifactData ? (
        <div className={`${executionSidePanelCls} mt-3`}>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-text-primary">Artifact 关联执行</div>
            <Badge variant={artifactData.count > 0 ? 'success' : 'neutral'}>
              {artifactData.count > 0 ? `${artifactData.count} 条任务` : '暂无任务'}
            </Badge>
          </div>
          <div className="mt-2 text-xs text-text-secondary">
            artifact {artifactData.artifactId}，最新任务 {artifactData.latestTaskId || '-'}。
          </div>
          {artifactData.count > 0 && artifactDetailId ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onOpenArtifactDetail(artifactDetailId)}
                aria-label="打开 artifact 详情页面板"
                className={executionChipButtonCls}
              >
                打开 artifact 详情页
              </button>
              <Link href={artifactDetailHref} className={`${executionChipButtonCls} no-underline text-inherit`}>
                打开独立详情链接
              </Link>
            </div>
          ) : (
            <div className="mt-3">
              <Link href={artifactDetailHref} className={`${executionChipButtonCls} no-underline text-inherit`}>
                查看 artifact 空态
              </Link>
            </div>
          )}
          {artifactData.latestTask ? (
            <div className="mt-3 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
              <div>标的：{artifactData.latestTask.code || '-'}</div>
              <div>状态：{artifactData.latestTask.status || '-'}</div>
              <div>算法：{artifactData.latestTask.algorithm || '-'}</div>
              <div>告警：{artifactData.latestTask.warningCount ?? 0}</div>
            </div>
          ) : null}
        </div>
      ) : null}
    </SectionCard>
  );
}
