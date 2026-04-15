'use client';

import { LineChart, BarChart } from '@/components/charts';
import { Badge, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { formatMultipleTestingMode } from '@/app/strategy-market/lib/strategy-detail-view';
import type {
  IncubationOverviewResponse,
  IncubationAccount,
  IncubationMetric,
  ReviewReportResponse,
  StrategyMetric,
  StrategyReview,
  VectorProfile,
} from '../types';
import { heroPrimaryButtonCls } from './strategy-detail-panel-styles';

type FactorBarItem = {
  name: string;
  value: number;
};

type StrategyDetailOverviewTabProps = {
  allMetrics: StrategyMetric | null;
  metrics: StrategyMetric[];
  reviews: StrategyReview[];
  navSeries: number[];
  navCategories: string[];
  factorBars: FactorBarItem[];
  incubationOverview: IncubationOverviewResponse | null | undefined;
  latestQualityReport: ReviewReportResponse | null | undefined;
  incubationAccount: IncubationAccount | null | undefined;
  latestIncubationMetric: IncubationMetric | null | undefined;
  openRiskEventsCount: number;
  vectorProfilesCount: number;
  highConfidenceQualityUiEnabled: boolean;
  promotionReady: boolean;
  strategyAvgRating: number | null | undefined;
  sampleWindow: string;
  turnoverRate: number | null;
  capacityLabel: string;
  capacityValue: number | null;
  multipleTestingMode: string | null;
  deflatedSharpeRatio: number | null;
  pboValue: number | null;
  hansenSpaPvalue: number | null;
  whiteRealityCheckPvalue: number | null;
  rating: number;
  setRating: (value: number) => void;
  comment: string;
  setComment: (value: string) => void;
  reviewPending: boolean;
  userId: string | null;
  onReview: () => void;
};

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item));
}

function qualityBadgeVariant(
  value: unknown,
): 'success' | 'danger' | 'warning' | 'info' | 'neutral' {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'strong' || normalized === 'comparable_ready') return 'success';
  if (normalized === 'mixed' || normalized === 'diagnostic_ready') return 'info';
  if (normalized === 'insufficient_evidence' || normalized === 'insufficient') return 'warning';
  if (normalized === 'weak' || normalized === 'missing') return 'danger';
  return 'neutral';
}

function qualityLabelText(value: unknown) {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'strong') return '强';
  if (normalized === 'mixed') return '混合';
  if (normalized === 'weak') return '弱';
  if (normalized === 'insufficient_evidence') return '证据不足';
  if (normalized === 'missing') return '缺失';
  if (normalized === 'insufficient') return '样本不足';
  if (normalized === 'diagnostic_ready') return '诊断可用';
  if (normalized === 'comparable_ready') return '可比较';
  return normalized || '-';
}

function executionLineageStatusText(value: unknown) {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'mapped_runtime_action') return 'mapped runtime';
  if (normalized === 'unmapped_runtime_action') return 'unmapped runtime';
  if (normalized === 'mapped_trade_step') return 'mapped step';
  if (normalized === 'claim_only') return 'claim only';
  if (normalized === 'missing') return 'missing';
  return normalized || '-';
}

export function StrategyDetailOverviewTab({
  allMetrics,
  metrics,
  reviews,
  navSeries,
  navCategories,
  factorBars,
  incubationOverview,
  latestQualityReport,
  incubationAccount,
  latestIncubationMetric,
  openRiskEventsCount,
  vectorProfilesCount,
  highConfidenceQualityUiEnabled,
  promotionReady,
  strategyAvgRating,
  sampleWindow,
  turnoverRate,
  capacityLabel,
  capacityValue,
  multipleTestingMode,
  deflatedSharpeRatio,
  pboValue,
  hansenSpaPvalue,
  whiteRealityCheckPvalue,
  rating,
  setRating,
  comment,
  setComment,
  reviewPending,
  userId,
  onReview,
}: StrategyDetailOverviewTabProps) {
  const incubationOverviewRecord = asRecord(incubationOverview);
  const signalQuality = asRecord(incubationOverviewRecord.signal_quality);
  const executionQuality = asRecord(incubationOverviewRecord.execution_quality);
  const executionAudit = asRecord(executionQuality.audit);
  const executionDiagnostics = asRecord(incubationOverviewRecord.execution_diagnostics);
  const hardGateResult = asRecord(incubationOverviewRecord.hard_gate_result);
  const semanticLineage = asRecord(incubationOverviewRecord.semantic_lineage);
  const executionLineage = asRecord(incubationOverviewRecord.execution_lineage);
  const runtimePlaybookProvenance = asRecord(
    incubationOverviewRecord.runtime_playbook_provenance ?? semanticLineage.runtime_playbook_provenance,
  );
  const claimToTradePlanMap = asRecord(semanticLineage.claim_to_trade_plan_map);
  const tradePlanToDslMap = asRecord(semanticLineage.trade_plan_to_dsl_map);
  const predictionQualityLabel = String(
    incubationOverviewRecord.prediction_quality_label ?? '',
  ).trim().toLowerCase();
  const executionQualityLabel = String(
    incubationOverviewRecord.execution_quality_label ?? '',
  ).trim().toLowerCase();
  const confidenceContractStatus = String(
    incubationOverviewRecord.confidence_contract_status ?? '',
  ).trim().toLowerCase();
  const qualityDiagnosis = String(
    incubationOverviewRecord.quality_diagnosis ?? '',
  ).trim();
  const executionConversionEfficiency = Number(
    executionQuality.execution_conversion_efficiency
      ?? executionAudit.execution_conversion_efficiency
      ?? executionDiagnostics.execution_conversion_efficiency
      ?? executionQuality.nav_conversion_proxy
      ?? Number.NaN,
  );
  const coverageRatio = Number(signalQuality.coverage_ratio ?? Number.NaN);
  const primarySkillLcb = Number(signalQuality.primary_skill_lcb ?? Number.NaN);
  const hardGatePassed = Boolean(hardGateResult.passed);
  const semanticClaimCount = Object.keys(asRecord(claimToTradePlanMap.claim_to_trade_step_ids)).length;
  const semanticTradeStepCount = Object.keys(asRecord(tradePlanToDslMap.trade_step_to_dsl_sections)).length;
  const executionLineageRows = asRecordArray(executionLineage.recent_runtime_actions).slice(0, 4);
  const executionLineageTradeStepCount = Number(
    executionLineage.trade_step_count
      ?? executionLineage.mapped_trade_step_count
      ?? semanticTradeStepCount
      ?? Number.NaN,
  );
  const executionLineageRuntimeCount = Number(executionLineage.runtime_action_count ?? Number.NaN);
  const executionLineageUnmappedCount = Number(executionLineage.unmapped_runtime_action_count ?? Number.NaN);
  const playbookDerivationLabels = Array.isArray(runtimePlaybookProvenance.derivation_labels)
    ? runtimePlaybookProvenance.derivation_labels.map((item) => String(item)).filter(Boolean)
    : [];
  const showHighConfidencePanel = highConfidenceQualityUiEnabled && [
    predictionQualityLabel,
    executionQualityLabel,
    confidenceContractStatus,
    qualityDiagnosis,
  ].some(Boolean);

  return (
    <>
      {allMetrics ? (
        <KpiGrid cols={6}>
          <KpiCard title="总收益" value={fmtPct(allMetrics.total_return ?? 0)} change={allMetrics.total_return} />
          <KpiCard title="年化收益" value={fmtPct(allMetrics.annual_return ?? 0)} />
          <KpiCard title="Sharpe" value={fmtNum(allMetrics.sharpe_ratio ?? 0, 2)} />
          <KpiCard title="最大回撤" value={fmtPct(allMetrics.max_drawdown ?? 0)} />
          <KpiCard title="胜率" value={fmtPct(allMetrics.win_rate ?? 0)} />
          <KpiCard title="交易次数" value={allMetrics.trade_count ?? '-'} />
        </KpiGrid>
      ) : null}

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[1.4fr_1fr]">
        {navSeries.length > 1 ? (
          <SectionCard className="mt-0 p-3">
            <h3 className="mt-0">净值轨迹</h3>
            <LineChart
              categories={navCategories}
              series={[{ name: 'NAV', data: navSeries, color: '#1a73e8' }]}
              height={280}
            />
          </SectionCard>
        ) : null}
        <SectionCard className="mt-0 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="mt-0">运行摘要</h3>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
                把孵化状态、风险信号与统计修正并列呈现，方便先判断是否值得继续跟踪，再决定要不要切到工厂审查。
              </p>
            </div>
            <Badge variant={promotionReady ? 'success' : 'warning'}>
              {promotionReady ? '达到上架条件' : '仍在孵化观察'}
            </Badge>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">孵化上下文</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <div>
                  孵化阶段：
                  <span className="font-medium text-text-primary">
                    {incubationAccount?.stage ?? latestIncubationMetric?.stage ?? '-'}
                  </span>
                </div>
                <div>
                  账户状态：<span className="font-medium text-text-primary">{incubationAccount?.status ?? '-'}</span>
                </div>
                <div>
                  最新 NAV：
                  <span className="font-medium text-text-primary">{fmtNum(latestIncubationMetric?.nav ?? 0, 4)}</span>
                </div>
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">风险与画像</div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <div className="text-2xl font-semibold text-text-primary">{openRiskEventsCount}</div>
                  <div className="mt-1 text-xs text-text-secondary">开放风险事件</div>
                </div>
                <div>
                  <div className="text-2xl font-semibold text-text-primary">{vectorProfilesCount}</div>
                  <div className="mt-1 text-xs text-text-secondary">向量画像数</div>
                </div>
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">质量门</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <div>
                  质量评级：
                  <span className="font-medium text-text-primary">
                    {latestQualityReport?.summary?.validation_grade ?? '-'}
                  </span>
                </div>
                <div>
                  DSR：
                  <span className="font-medium text-text-primary">
                    {deflatedSharpeRatio == null ? '-' : fmtNum(deflatedSharpeRatio, 4)}
                  </span>
                </div>
                <div>
                  PBO：
                  <span className="font-medium text-text-primary">{pboValue == null ? '-' : fmtNum(pboValue, 4)}</span>
                </div>
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">统计修正</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                <div>
                  SPA p-value：
                  <span className="font-medium text-text-primary">
                    {hansenSpaPvalue == null ? '-' : fmtNum(hansenSpaPvalue, 4)}
                  </span>
                </div>
                <div>
                  White RC：
                  <span className="font-medium text-text-primary">
                    {whiteRealityCheckPvalue == null ? '-' : fmtNum(whiteRealityCheckPvalue, 4)}
                  </span>
                </div>
                <div>
                  多重检验：
                  <span className="font-medium text-text-primary">
                    {formatMultipleTestingMode(multipleTestingMode)}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            {latestIncubationMetric?.decision ? (
              <Badge
                variant={
                  latestIncubationMetric.decision === 'promote'
                    ? 'success'
                    : latestIncubationMetric.decision === 'halt'
                      ? 'danger'
                      : 'warning'
                }
              >
                最新决策: {latestIncubationMetric.decision}
              </Badge>
            ) : null}
            {promotionReady ? (
              <Badge variant="success">达到上架条件</Badge>
            ) : (
              <Badge variant="warning">仍在孵化观察</Badge>
            )}
            {openRiskEventsCount > 0 ? (
              <Badge variant="danger">存在实时风控告警</Badge>
            ) : (
              <Badge variant="neutral">无实时风控告警</Badge>
            )}
            {multipleTestingMode ? (
              <Badge variant={multipleTestingMode === 'formal_runtime' ? 'success' : 'warning'}>
                多重检验: {formatMultipleTestingMode(multipleTestingMode)}
              </Badge>
            ) : null}
            {pboValue != null ? (
              <Badge variant={pboValue > 0.55 ? 'danger' : 'info'}>PBO {fmtNum(pboValue, 4)}</Badge>
            ) : null}
            {hansenSpaPvalue != null ? (
              <Badge variant={hansenSpaPvalue > 0.2 ? 'warning' : 'success'}>SPA p {fmtNum(hansenSpaPvalue, 4)}</Badge>
            ) : null}
          </div>
        </SectionCard>
      </div>

      <SectionCard className="p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="mt-0">可信信息</h3>
            <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
              合同字段、样本边界与容量口径放在同一层，避免这类“可信来源”被埋在指标流里。
            </p>
          </div>
          <Badge variant="info">Contract First</Badge>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <div className="metric-tile rounded-[24px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">样本期</div>
            <div className="mt-3 text-base font-semibold text-text-primary">{sampleWindow}</div>
          </div>
          <div className="metric-tile rounded-[24px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">最近换手</div>
            <div className="mt-3 text-base font-semibold text-text-primary">
              {turnoverRate == null ? '-' : fmtPct(turnoverRate)}
            </div>
          </div>
          <div className="metric-tile rounded-[24px] p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">{capacityLabel}</div>
            <div className="mt-3 text-base font-semibold text-text-primary">
              {capacityValue == null ? '-' : fmtNum(capacityValue, 2)}
            </div>
          </div>
        </div>
        <div className="mt-3 text-xs leading-6 text-text-secondary">
          样本期优先取策略合同字段，缺失时回退到孵化账户 NAV 区间；容量优先展示合同声明，缺失时回退到模拟盘当前总资产。
        </div>
      </SectionCard>

      {showHighConfidencePanel ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="mt-0">高置信质量</h3>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
                把预测质量、执行转化和合同就绪度放在同一块，只做增量展示，不替代现有验证卡片。
              </p>
            </div>
            <Badge variant="info">High Confidence</Badge>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {predictionQualityLabel ? (
              <Badge variant={qualityBadgeVariant(predictionQualityLabel)}>
                预测质量: {qualityLabelText(predictionQualityLabel)}
              </Badge>
            ) : null}
            {executionQualityLabel ? (
              <Badge variant={qualityBadgeVariant(executionQualityLabel)}>
                执行质量: {qualityLabelText(executionQualityLabel)}
              </Badge>
            ) : null}
            {confidenceContractStatus ? (
              <Badge variant={qualityBadgeVariant(confidenceContractStatus)}>
                合同状态: {qualityLabelText(confidenceContractStatus)}
              </Badge>
            ) : null}
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">预测轴</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {Number.isFinite(primarySkillLcb) ? fmtNum(primarySkillLcb, 4) : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">primary skill LCB</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">覆盖率</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {Number.isFinite(coverageRatio) ? fmtPct(coverageRatio) : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">signal coverage / forward coverage</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">执行轴</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {Number.isFinite(executionConversionEfficiency)
                  ? fmtPct(executionConversionEfficiency)
                  : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">execution conversion efficiency</div>
            </div>
          </div>
          <div className="mt-3 rounded-[24px] border border-border bg-surface-alt px-4 py-3 text-sm text-text-secondary">
            {qualityDiagnosis || '当前尚无额外诊断文本，先以标签和合同状态作为高置信质量参考。'}
          </div>
        </SectionCard>
      ) : null}

      {(Object.keys(hardGateResult).length > 0 || Object.keys(semanticLineage).length > 0 || Object.keys(executionLineage).length > 0) ? (
        <SectionCard className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="mt-0">闭环语义</h3>
              <p className="mb-0 mt-2 text-sm leading-6 text-text-secondary">
                把 hard gate、diagnostic only 和 semantic lineage 分开讲清楚，避免把排序分误读成硬通过。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.keys(hardGateResult).length > 0 ? (
                <Badge variant={hardGatePassed ? 'success' : 'warning'}>
                  Hard Gate: {hardGatePassed ? '通过' : '未通过'}
                </Badge>
              ) : null}
              <Badge variant={executionDiagnostics.diagnostic_only ? 'info' : 'neutral'}>
                {executionDiagnostics.diagnostic_only ? 'Diagnostic Only' : 'Runtime Contract'}
              </Badge>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">硬门结果</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {String(hardGateResult.pipeline_stage ?? incubationOverviewRecord.pipeline_stage ?? '-')}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {String(hardGateResult.execution_audit_gate_status ?? incubationOverviewRecord.execution_audit_gate_status ?? '-')}
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Semantic Lineage</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {semanticClaimCount} claims / {semanticTradeStepCount} steps
              </div>
              <div className="mt-1 text-xs text-text-secondary">claim → trade step → DSL rule</div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Playbook 来源</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {playbookDerivationLabels.length ? playbookDerivationLabels[0] : '-'}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {runtimePlaybookProvenance.derived_from_defaults == null
                  ? 'provenance unavailable'
                  : runtimePlaybookProvenance.derived_from_defaults
                    ? 'derived from defaults'
                    : 'provided by compile output'}
              </div>
            </div>
            <div className="metric-tile rounded-[24px] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">Step-level Lineage</div>
              <div className="mt-3 text-base font-semibold text-text-primary">
                {Number.isFinite(executionLineageTradeStepCount) ? executionLineageTradeStepCount : semanticTradeStepCount}
              </div>
              <div className="mt-1 text-xs text-text-secondary">
                {Number.isFinite(executionLineageRuntimeCount) ? `${executionLineageRuntimeCount} runtime actions` : 'runtime actions unavailable'}
                {Number.isFinite(executionLineageUnmappedCount) ? ` / unmapped ${executionLineageUnmappedCount}` : ''}
              </div>
            </div>
          </div>
          <div className="mt-3 rounded-[24px] border border-border bg-surface-alt px-4 py-3 text-sm text-text-secondary">
            {[
              semanticClaimCount ? `claim → trade step 映射 ${semanticClaimCount} 条` : '',
              semanticTradeStepCount ? `trade step → DSL 映射 ${semanticTradeStepCount} 条` : '',
              playbookDerivationLabels.length ? `runtime playbook: ${playbookDerivationLabels.join(' / ')}` : '',
              Number.isFinite(executionLineageRuntimeCount) ? `runtime actions ${executionLineageRuntimeCount}` : '',
              String(executionDiagnostics.remediation_action ?? '').trim(),
            ].filter(Boolean).join('；') || '当前未返回额外 lineage 细节。'}
          </div>
          {executionLineageRows.length ? (
            <div className="mt-4 rounded-[24px] border border-border bg-surface-alt px-4 py-4">
              <div className="text-sm font-medium text-text-primary">Recent Runtime Actions</div>
              <div className="mt-3 space-y-2 text-sm text-text-secondary">
                {executionLineageRows.map((item, index) => (
                  <div
                    key={`${String(item.signal_id ?? item.signal_date ?? index)}-${String(item.applied_trade_step_id ?? index)}`}
                    className="rounded-[18px] border border-border bg-surface px-3 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2 text-text-primary">
                      <Badge variant="info">{String(item.runtime_action_reason ?? 'runtime')}</Badge>
                      <span>{String(item.code ?? '-')}</span>
                      <span className="text-text-secondary">{String(item.signal_date ?? '-')}</span>
                    </div>
                    <div className="mt-2 text-xs leading-6">
                      Claim: {String(item.applied_claim_id ?? '-')} · Trade Step: {String(item.applied_trade_step_id ?? '-')}
                    </div>
                    <div className="text-xs leading-6">
                      状态: {executionLineageStatusText(item.lineage_status)} · 来源: {String(item.runtime_action_source ?? '-')}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </SectionCard>
      ) : null}

      {metrics.length > 1
        ? (() => {
            const sorted = [...metrics].sort((left, right) => (left.period ?? '').localeCompare(right.period ?? ''));
            const periods = sorted.map((item) => item.period ?? '');
            const returns = sorted.map((item) => Number(item.total_return ?? 0));
            const sharpes = sorted.map((item) => Number(item.sharpe_ratio ?? 0));
            return (
              <SectionCard className="p-3">
                <h3 className="mt-0">各期表现</h3>
                <LineChart
                  categories={periods}
                  series={[
                    { name: '总收益', data: returns, color: '#1a73e8' },
                    { name: 'Sharpe', data: sharpes, color: '#f59e0b', yAxisIndex: 1 },
                  ]}
                  height={260}
                  yAxisName="收益率"
                  y2AxisName="Sharpe"
                />
              </SectionCard>
            );
          })()
        : null}

      {factorBars.length > 0 ? (
        <SectionCard className="p-3">
          <h3 className="mt-0">因子暴露度</h3>
          <BarChart
            items={factorBars.map((item) => ({ label: item.name, value: item.value, color: '#6366f1' }))}
            height={220}
          />
        </SectionCard>
      ) : null}

      <SectionCard className="p-4 sm:p-5">
        <h3 className="mt-0">
          用户评价
          {strategyAvgRating != null ? (
            <span className="ml-2 text-sm text-amber-500">
              {'★'.repeat(Math.round(strategyAvgRating))} {strategyAvgRating.toFixed(1)}
            </span>
          ) : null}
        </h3>

        <div className="panel-soft mb-4 rounded-[24px] p-3 sm:p-4">
          <div className="mb-3 text-xs leading-6 text-text-secondary">
            用更轻的 glass 表单承接评分与短评，既保留互动感，也不会把整块界面拉回传统后台风格。
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={rating}
              onChange={(event) => setRating(Number(event.target.value))}
              className="w-auto min-w-[104px] text-sm"
            >
              {[5, 4, 3, 2, 1].map((value) => (
                <option key={value} value={value}>
                  {value} 星
                </option>
              ))}
            </select>
            <input
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="写一条评价..."
              className="min-w-[220px] flex-1 text-sm"
            />
            <button onClick={onReview} disabled={reviewPending || !userId} className={heroPrimaryButtonCls}>
              {reviewPending ? '提交中...' : !userId ? '登录后可评价' : '提交'}
            </button>
          </div>
        </div>

        {reviews.length ? (
          <div className="space-y-3">
            {reviews.map((review, index) => (
              <div
                key={`${review.user_id}-${review.created_at ?? index}`}
                className="panel-soft rounded-[22px] p-4 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-amber-400">{'★'.repeat(review.rating)}</span>
                  <span className="text-text-secondary">{review.user_id}</span>
                </div>
                {review.comment ? <p className="mt-1 text-text-secondary">{review.comment}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-secondary">暂无评价</p>
        )}
      </SectionCard>
    </>
  );
}
