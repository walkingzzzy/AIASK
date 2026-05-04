'use client';

import { Badge, DataTable, KpiCard, SectionCard } from '@/components/ui';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { normalizeStrategyPercentMetric } from '@/lib/strategy-metrics';
import { formatDateTime, shortText } from '@/app/strategy-market/lib/factory-review-view-model';
import { qualityBadgeVariant, qualityLabelText } from './helpers';
import type {
  FactoryReviewAuditRows,
  FactoryReviewPanelProps,
  FactoryReviewSummaryState,
} from './types';
import type {
  ExecutionAuditAcceptanceResponse,
  IncubationAccount,
  IncubationMetric,
  IncubationOverviewResponse,
  PromotionReview,
  ReviewReportResponse,
  RuntimeControl,
} from '../../types';

type SummarySectionProps = {
  review: ReviewReportResponse | null;
  incubation: IncubationOverviewResponse | null | undefined;
  latestMetric: IncubationMetric | null | undefined;
  currentAccount: IncubationAccount | null | undefined;
  latestPromotionReview: PromotionReview | null | undefined;
  runtimeControl: RuntimeControl | null | undefined;
  executionAuditAcceptance: ExecutionAuditAcceptanceResponse | null | undefined;
  summaryState: FactoryReviewSummaryState;
  reviewAuditRows: FactoryReviewAuditRows;
  eventFilters: FactoryReviewPanelProps['eventFilters'];
  onEventFilterChange: FactoryReviewPanelProps['onEventFilterChange'];
  onRebuildProjection: FactoryReviewPanelProps['onRebuildProjection'];
  rebuildProjectionPending: boolean;
  onRunExecutionAuditAcceptance: () => void;
  runExecutionAuditAcceptancePending: boolean;
  promotionReadyBadge: boolean;
  signalSnapshotStatus: string;
  executionSnapshotStatus: string;
  traceEvidenceGapCodes: string[];
};

export function SummarySection({
  review,
  incubation,
  latestMetric,
  currentAccount,
  latestPromotionReview,
  runtimeControl,
  executionAuditAcceptance,
  summaryState,
  reviewAuditRows,
  eventFilters,
  onEventFilterChange,
  onRebuildProjection,
  rebuildProjectionPending,
  onRunExecutionAuditAcceptance,
  runExecutionAuditAcceptancePending,
  promotionReadyBadge,
  signalSnapshotStatus,
  executionSnapshotStatus,
  traceEvidenceGapCodes,
}: SummarySectionProps) {
  const acceptanceMatrix = executionAuditAcceptance?.acceptance_matrix ?? {};
  const acceptanceBlockers = executionAuditAcceptance?.blockers ?? [];
  const acceptanceRecommendations = executionAuditAcceptance?.recommendations ?? [];
  const tradeAuditSummary = executionAuditAcceptance?.trade_audit_summary ?? {};
  const verification = executionAuditAcceptance?.verification ?? {};
  const coverage = verification.coverage ?? {};
  const orderCoverage = coverage.paper_orders ?? {};
  const tradeCoverage = coverage.paper_trades ?? {};
  const realizedTradeCount = Number(tradeAuditSummary.realized_trade_count ?? Number.NaN);
  const incompletePositionCount = Number(tradeAuditSummary.incomplete_position_count ?? Number.NaN);

  return (
    <>
      <SectionCard className="p-3">
        <h3 className="mt-0">工厂质检摘要</h3>
        <DataTable
          columns={[
            { key: 'item', label: '指标' },
            { key: 'value', label: '结果' },
          ]}
          rows={reviewAuditRows}
        />
        {(
          review?.run_correction?.multiple_testing_mode
          || review?.validation_profile?.profile
          || review?.position_assumption
          || review?.committee_review?.decision
          || review?.task_preference?.preference_strength
          || Number(review?.attempt_adjustment?.penalty ?? 0) > 0
          || review?.constraint_check?.constraint_violation
        ) ? (
          <div className="mt-3 flex gap-2 flex-wrap text-sm">
            {review?.run_correction?.multiple_testing_mode ? (
              <Badge variant={review.run_correction.multiple_testing_mode === 'formal_runtime' ? 'success' : 'warning'}>
                多重检验: {review.run_correction.multiple_testing_mode === 'formal_runtime' ? '正式论文实现' : review.run_correction.multiple_testing_mode}
              </Badge>
            ) : null}
            {(review?.run_correction?.pbo ?? review?.quality_gate?.pbo) != null ? (
              <Badge variant={Number(review?.run_correction?.pbo ?? review?.quality_gate?.pbo) > 0.55 ? 'danger' : 'info'}>
                PBO {fmtNum(review?.run_correction?.pbo ?? review?.quality_gate?.pbo, 4)}
              </Badge>
            ) : null}
            {(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue) != null ? (
              <Badge variant={Number(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue) > 0.2 ? 'warning' : 'success'}>
                SPA p {fmtNum(review?.run_correction?.hansen_spa_pvalue ?? review?.quality_gate?.hansen_spa_pvalue, 4)}
              </Badge>
            ) : null}
            {review?.validation_profile?.profile ? (
              <Badge variant="neutral">
                验证画像: {review.validation_profile.profile}
              </Badge>
            ) : null}
            {review?.committee_review?.decision ? (
              <Badge variant={review.committee_review.decision === 'accept' ? 'success' : review.committee_review.decision === 'reject' ? 'danger' : 'warning'}>
                评审: {review.committee_review.decision}
                {review.committee_review.final_score != null ? ` ${fmtNum(review.committee_review.final_score, 4)}` : ''}
              </Badge>
            ) : null}
            {review?.committee_review?.execution_score != null ? (
              <Badge variant={Number(review.committee_review.execution_score) >= 0.5 ? 'success' : 'warning'}>
                执行 {fmtNum(review.committee_review.execution_score, 2)}
              </Badge>
            ) : null}
            {review?.committee_review?.capacity_score != null ? (
              <Badge variant={Number(review.committee_review.capacity_score) >= 0.5 ? 'success' : 'warning'}>
                容量 {fmtNum(review.committee_review.capacity_score, 2)}
              </Badge>
            ) : null}
            {review?.committee_review?.task_alignment_score != null ? (
              <Badge variant={Number(review.committee_review.task_alignment_score) >= 0.45 ? 'success' : 'warning'}>
                对齐 {fmtNum(review.committee_review.task_alignment_score, 2)}
              </Badge>
            ) : null}
            {review?.position_assumption ? (
              <Badge variant="neutral">
                仓位: {review.position_assumption}
              </Badge>
            ) : null}
            {review?.task_preference?.preference_strength ? (
              <Badge variant={review.task_preference.preference_strength === 'hard' ? 'warning' : 'info'}>
                偏好强度: {review.task_preference.preference_strength}
              </Badge>
            ) : null}
            {review?.task_preference?.override_applied ? (
              <Badge variant="success">
                证据已压过偏好
              </Badge>
            ) : null}
            {Number(review?.attempt_adjustment?.penalty ?? 0) > 0 ? (
              <Badge variant="warning">
                尝试惩罚 {fmtNum(review?.attempt_adjustment?.penalty, 4)}
              </Badge>
            ) : null}
            {review?.constraint_check?.constraint_violation ? (
              <Badge variant="danger">
                约束违例: {review.constraint_check.constraint_violation}
              </Badge>
            ) : null}
          </div>
        ) : null}
        {review?.quality_gate?.reasons?.length ? (
          <div className="mt-3 text-sm text-danger">
            <div className="font-medium mb-1">未通过原因</div>
            <ul className="m-0 pl-5">
              {review.quality_gate.reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          </div>
        ) : null}
        {review?.reports?.length ? (
          <div className="mt-3 text-sm text-text-secondary">
            <div className="font-medium mb-1">报告历史</div>
            <ul className="m-0 pl-5">
              {review.reports.map((item, index) => (
                <li key={`${item.report_type ?? 'report'}-${item.updated_at ?? index}`}>
                  {item.report_type ?? '-'} / {item.summary?.review_source ?? '-'} / {item.summary?.raw_validation_grade ?? item.summary?.validation_grade ?? '-'} → {item.summary?.effective_validation_grade ?? item.summary?.validation_grade ?? '-'}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </SectionCard>

      {executionAuditAcceptance ? (
        <SectionCard className="p-3">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <h3 className="mt-0 mb-1">Timescale 执行审计校验</h3>
              <p className="mb-0 text-sm text-text-secondary">
                汇总迁移、回填、成交到仓位闭环和强校验状态，帮助确认执行审计是否可以进入下一步。
              </p>
            </div>
            <button
              onClick={onRunExecutionAuditAcceptance}
              disabled={runExecutionAuditAcceptancePending}
              className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
            >
              {runExecutionAuditAcceptancePending ? '正在回填校验' : '执行回填校验'}
            </button>
          </div>
          <div className="flex gap-2 flex-wrap mb-3">
            <Badge variant={acceptanceMatrix.overall_ready ? 'success' : 'warning'}>
              总体：{acceptanceMatrix.overall_ready ? '已就绪' : '待确认'}
            </Badge>
            <Badge variant={acceptanceMatrix.schema_ready ? 'success' : 'danger'}>
              结构：{acceptanceMatrix.schema_ready ? '已就绪' : '缺失'}
            </Badge>
            <Badge variant={acceptanceMatrix.migration_ready ? 'success' : 'warning'}>
              迁移：{acceptanceMatrix.migration_ready ? '已就绪' : '待确认'}
            </Badge>
            <Badge variant={acceptanceMatrix.fill_round_trip_ready ? 'success' : 'warning'}>
              成交闭环：{acceptanceMatrix.fill_round_trip_ready ? '已就绪' : '未闭环'}
            </Badge>
            <Badge variant={acceptanceMatrix.hard_gate_ready ? 'success' : 'warning'}>
              强校验：{acceptanceMatrix.hard_gate_ready ? '已就绪' : '阻塞'}
            </Badge>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <KpiCard title="状态" value={executionAuditAcceptance.status ?? '-'} />
            <KpiCard title="已实现成交" value={Number.isFinite(realizedTradeCount) ? realizedTradeCount : '-'} />
            <KpiCard title="未闭环仓位" value={Number.isFinite(incompletePositionCount) ? incompletePositionCount : '-'} />
            <KpiCard title="执行门禁" value={String(tradeAuditSummary.execution_audit_gate_status ?? '-')} />
          </div>
          <DataTable
            columns={[
              { key: 'item', label: '校验项' },
              { key: 'value', label: '结果' },
            ]}
            rows={[
              { item: 'paper_orders.position_id 覆盖率', value: orderCoverage.position_id_ratio == null ? '-' : fmtPct(normalizeStrategyPercentMetric(orderCoverage.position_id_ratio)) },
              { item: 'paper_trades.position_id 覆盖率', value: tradeCoverage.position_id_ratio == null ? '-' : fmtPct(normalizeStrategyPercentMetric(tradeCoverage.position_id_ratio)) },
              { item: '本地证据链', value: acceptanceMatrix.native_lineage_ready ? 'native_ready' : 'missing' },
              { item: 'Trade Evidence', value: acceptanceMatrix.trade_evidence_ready ? 'ready' : 'insufficient' },
              { item: 'Backfill 执行', value: executionAuditAcceptance.backfill_executed ? '是' : '否' },
              { item: '验证方法', value: executionAuditAcceptance.method ?? '-' },
            ]}
          />
          {acceptanceBlockers.length ? (
            <div className="mt-3 text-sm text-danger">
              <div className="font-medium mb-1">当前阻塞项</div>
              <ul className="m-0 pl-5">
                {acceptanceBlockers.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
          {acceptanceRecommendations.length ? (
            <div className="mt-3 text-sm text-text-secondary">
              <div className="font-medium mb-1">建议动作</div>
              <ul className="m-0 pl-5">
                {acceptanceRecommendations.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      <SectionCard className="p-3">
        <h3 className="mt-0">孵化观察窗口</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <KpiCard title="Sharpe" value={fmtNum(incubation?.sharpe_ratio ?? latestMetric?.sharpe_ratio, 2)} />
          <KpiCard
            title="最大回撤"
            value={fmtPct(normalizeStrategyPercentMetric(incubation?.max_drawdown ?? latestMetric?.max_drawdown))}
          />
          <KpiCard title="前向IC(5D)" value={fmtNum(incubation?.forward_ic_5d ?? latestMetric?.forward_ic_5d, 4)} />
          <KpiCard title="前向Sharpe(5D)" value={fmtNum(incubation?.forward_sharpe_5d ?? latestMetric?.forward_sharpe_5d, 4)} />
        </div>
        <div className="flex gap-2 flex-wrap text-sm">
          <Badge variant={promotionReadyBadge ? 'success' : 'warning'}>
            {promotionReadyBadge ? '达到上架条件' : '快照/追踪仍在观察中'}
          </Badge>
          <Badge variant={incubation?.deprecation_risk ? 'danger' : 'neutral'}>
            {incubation?.deprecation_risk ? '存在淘汰风险' : '暂无淘汰风险'}
          </Badge>
          {signalSnapshotStatus ? (
            <Badge variant={qualityBadgeVariant(signalSnapshotStatus)}>
              Signal Snapshot: {qualityLabelText(signalSnapshotStatus)}
            </Badge>
          ) : null}
          {executionSnapshotStatus ? (
            <Badge variant={qualityBadgeVariant(executionSnapshotStatus)}>
              Execution Snapshot: {qualityLabelText(executionSnapshotStatus)}
            </Badge>
          ) : null}
          {traceEvidenceGapCodes.length ? (
            <Badge variant="warning">
              Trace 缺口 {traceEvidenceGapCodes.length}
            </Badge>
          ) : null}
          {currentAccount?.account_id ? <Badge variant="info">模拟盘账户: {currentAccount.account_id}</Badge> : null}
          {latestMetric?.decision ? <Badge variant={latestMetric.decision === 'promote' ? 'success' : latestMetric.decision === 'halt' ? 'danger' : 'warning'}>最新决策: {latestMetric.decision}</Badge> : null}
        </div>
        {summaryState.blockers.length ? (
          <div className="mt-3 text-sm text-text-secondary">
            <div className="font-medium mb-1">晋级阻塞项</div>
            <ul className="m-0 pl-5">
              {summaryState.blockers.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {summaryState.riskFlags.length ? (
          <div className="mt-3 text-sm text-danger">
            <div className="font-medium mb-1">风险提示</div>
            <ul className="m-0 pl-5">
              {summaryState.riskFlags.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        {summaryState.forwardRows.length ? (
          <div className="mt-3">
            <DataTable
              columns={[
                { key: 'label', label: '观察窗口' },
                { key: 'hit_rate', label: '命中率' },
                { key: 'forward_ic', label: '前向IC' },
                { key: 'forward_sharpe', label: '前向Sharpe' },
              ]}
              rows={summaryState.forwardRows}
            />
          </div>
        ) : null}
      </SectionCard>

      {summaryState.executionLineageSummaryRows.length || summaryState.executionLineageRows.length ? (
        <SectionCard className="p-3">
          <h3 className="mt-0">执行链路</h3>
          <p className="mb-3 text-sm text-text-secondary">
            把 claim-level lineage、Step-level Lineage 和 runtime action 一起放出来，方便直接核对运行态动作到底落到哪一个 trade step。
          </p>
          {summaryState.executionLineageSummaryRows.length ? (
            <DataTable
              columns={[
                { key: 'item', label: '项目' },
                { key: 'value', label: '值' },
              ]}
              rows={summaryState.executionLineageSummaryRows}
            />
          ) : null}
          {summaryState.executionLineageRows.length ? (
            <div className="mt-3">
              <DataTable
                columns={[
                  { key: 'signal_date', label: '信号日' },
                  { key: 'code', label: '标的' },
                  { key: 'runtime_action_reason', label: '动作' },
                  { key: 'applied_claim_id', label: 'Claim' },
                  { key: 'applied_trade_step_id', label: 'Trade Step' },
                  { key: 'lineage_status', label: '状态' },
                  { key: 'runtime_action_source', label: '来源' },
                ]}
                rows={summaryState.executionLineageRows}
                pageSize={6}
              />
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      <SectionCard className="p-3">
        <h3 className="mt-0">运行时控制面</h3>
        <div className="flex flex-wrap gap-2 mb-3">
          <Badge variant={(runtimeControl?.control_mode ?? 'active') === 'active' ? 'success' : (runtimeControl?.control_mode ?? '').includes('halt') || (runtimeControl?.control_mode ?? '') === 'manual_stop' ? 'danger' : 'warning'}>
            控制模式: {runtimeControl?.control_mode ?? 'active'}
          </Badge>
          <Badge variant={runtimeControl?.status === 'released' ? 'success' : 'info'}>
            控制状态: {runtimeControl?.status ?? 'released'}
          </Badge>
          {runtimeControl?.source ? <Badge variant="neutral">来源: {runtimeControl.source}</Badge> : null}
          {latestPromotionReview?.recommendation ? <Badge variant={latestPromotionReview.recommendation === 'promote' ? 'success' : latestPromotionReview.recommendation === 'deprecate' ? 'danger' : 'warning'}>最近晋级建议: {latestPromotionReview.recommendation}</Badge> : null}
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={[
            { item: '触发事件', value: runtimeControl?.trigger_event_type ?? '-' },
            { item: '控制原因', value: runtimeControl?.reason ?? '-' },
            { item: '激活时间', value: formatDateTime(runtimeControl?.activated_at) },
            { item: '释放时间', value: formatDateTime(runtimeControl?.released_at) },
            { item: '控制摘要', value: shortText(Object.entries(runtimeControl?.action_summary ?? {}).map(([key, value]) => `${key}:${String(value)}`).join(' / '), 48) },
          ]}
        />
      </SectionCard>

      <SectionCard className="p-3">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="mt-0 mb-0">事件投影 / 回放视图</h3>
          <button
            onClick={onRebuildProjection}
            disabled={rebuildProjectionPending}
            className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {rebuildProjectionPending ? '重建中...' : '重建投影'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={summaryState.projectionRows}
        />
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">生命周期事件流</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.event_type} onChange={(e) => onEventFilterChange('event_type', e.target.value)} placeholder="事件类型" />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.from_status} onChange={(e) => onEventFilterChange('from_status', e.target.value)} placeholder="起始状态" />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.to_status} onChange={(e) => onEventFilterChange('to_status', e.target.value)} placeholder="目标状态" />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.actor_id} onChange={(e) => onEventFilterChange('actor_id', e.target.value)} placeholder="触发方" />
          <input className="border rounded px-3 py-2 text-sm" type="date" value={eventFilters.start_time} onChange={(e) => onEventFilterChange('start_time', e.target.value)} />
          <input className="border rounded px-3 py-2 text-sm" type="date" value={eventFilters.end_time} onChange={(e) => onEventFilterChange('end_time', e.target.value)} />
          <input className="border rounded px-3 py-2 text-sm" value={eventFilters.limit} onChange={(e) => onEventFilterChange('limit', e.target.value)} placeholder="返回条数" />
        </div>
        {summaryState.eventRows.length ? (
          <DataTable
            columns={[
              { key: 'created_at', label: '时间' },
              { key: 'transition', label: '状态流转' },
              { key: 'actor_id', label: '触发方' },
              { key: 'reason', label: '原因' },
              { key: 'metadata', label: 'Metadata 摘要' },
            ]}
            rows={summaryState.eventRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无生命周期事件</p>
        )}
      </SectionCard>
    </>
  );
}
