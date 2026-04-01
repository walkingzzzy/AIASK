import { Badge, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { fmtNum } from '@/lib/data-utils';
import type { ExecutionInsight } from '@/lib/execution-normalizers';
import {
  executionChipButtonCls,
  executionSidePanelCls,
} from '@/app/execution/components/execution-panel-styles';

type ExecutionReviewPanelProps = {
  executionInsight: ExecutionInsight | null;
  activeExecutionCode: string;
  executionGuidance: string[];
  onOpenPerformanceReview: () => void;
  onOpenRiskReview: () => void;
  onOpenStockDetail: (code: string) => void;
};

export default function ExecutionReviewPanel({
  executionInsight,
  activeExecutionCode,
  executionGuidance,
  onOpenPerformanceReview,
  onOpenRiskReview,
  onOpenStockDetail,
}: ExecutionReviewPanelProps) {
  return (
    <SectionCard className="mb-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="m-0 font-medium">执行复盘摘要</h3>
          <p className="mb-0 mt-1 text-xs text-text-secondary">
            把执行结果直接串到绩效、风险和个股详情，避免执行完成后链路中断。
          </p>
        </div>
        <Badge variant={executionInsight?.hasHighSeverity ? 'warning' : executionInsight ? 'success' : 'neutral'}>
          {executionInsight?.hasHighSeverity ? '高严重级告警' : executionInsight ? '可复盘' : '等待执行结果'}
        </Badge>
      </div>

      <KpiGrid cols={5} className="mt-4">
        <KpiCard title="执行算法" value={executionInsight?.algorithm || '-'} />
        <KpiCard title="计划分片" value={executionInsight?.slices ?? '-'} />
        <KpiCard title="执行状态" value={executionInsight?.status || '-'} />
        <KpiCard title="告警数量" value={executionInsight?.warningCount ?? '-'} />
        <KpiCard
          title="预估成本"
          value={executionInsight?.estimatedCostTotal != null ? fmtNum(executionInsight.estimatedCostTotal) : '-'}
        />
      </KpiGrid>

      <div className="mt-4 grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
        <div className="panel-soft rounded-[24px] p-4">
          <div className="text-sm font-medium text-text-primary">当前摘要</div>
          <div className="mt-2 text-xs leading-6 text-text-secondary">
            {executionInsight
              ? `任务 ${executionInsight.taskId || '-'}，标的 ${executionInsight.code || activeExecutionCode || '-'}，总量 ${executionInsight.totalShares ?? '-'} 股，计划时长 ${executionInsight.durationMinutes ?? '-'} 分钟，软闸门画像 ${executionInsight.softGateProfile || '-'}。`
              : '提交执行或输入 execution_id 后，这里会汇总执行计划、告警和复盘入口。'}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={onOpenPerformanceReview} className={executionChipButtonCls}>
              打开绩效复盘
            </button>
            <button type="button" onClick={onOpenRiskReview} className={executionChipButtonCls}>
              打开风险中心
            </button>
            {activeExecutionCode ? (
              <button type="button" onClick={() => onOpenStockDetail(activeExecutionCode)} className={executionChipButtonCls}>
                打开个股详情
              </button>
            ) : null}
          </div>
        </div>

        <div className={executionSidePanelCls}>
          <div className="text-sm font-medium text-text-primary">下一步建议</div>
          <ul className="mb-0 mt-2 space-y-2 pl-4 text-xs leading-5 text-text-secondary">
            {executionGuidance.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </SectionCard>
  );
}
