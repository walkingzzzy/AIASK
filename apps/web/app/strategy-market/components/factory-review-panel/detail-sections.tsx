'use client';

import { useState } from 'react';
import { Badge, DataTable, SectionCard } from '@/components/ui';
import type {
  FactoryReviewExperimentState,
  FactoryReviewIncubationState,
  FactoryReviewPanelProps,
  FactoryReviewRuntimeState,
  FactoryReviewVectorState,
} from './types';

type IncubationSectionProps = {
  incubationState: FactoryReviewIncubationState;
  onRunIncubationPipeline: FactoryReviewPanelProps['onRunIncubationPipeline'];
  runIncubationPipelinePending: boolean;
  onRunIncubationSync: FactoryReviewPanelProps['onRunIncubationSync'];
  runIncubationSyncPending: boolean;
};

export function IncubationSection({
  incubationState,
  onRunIncubationPipeline,
  runIncubationPipelinePending,
  onRunIncubationSync,
  runIncubationSyncPending,
}: IncubationSectionProps) {
  return (
    <>
      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">孵化流水线</h3>
          <button
            type="button"
            onClick={onRunIncubationPipeline}
            disabled={runIncubationPipelinePending}
            className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {runIncubationPipelinePending ? '执行中...' : '执行流水线'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={incubationState.incubationPipelineOverviewRows}
        />
        {incubationState.incubationPipelineRows.length ? (
          <DataTable
            columns={[
              { key: 'evaluated_at', label: '评估时间' },
              { key: 'pipeline_stage', label: '阶段' },
              { key: 'pipeline_status', label: '状态', render: (value) => <Badge variant={value === 'ready_for_review' || value === 'promoted' ? 'success' : value === 'blocked' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'gate_status', label: '硬门状态' },
              { key: 'gate_reasons', label: '硬门原因' },
              { key: 'priority_score', label: '优先级分' },
              { key: 'readiness_score', label: '兼容准备度' },
              { key: 'observed_days', label: '观察天数' },
              { key: 'promote_streak', label: '晋级连击' },
              { key: 'halt_streak', label: '暂停连击' },
              { key: 'latest_decision', label: '最新决策' },
              { key: 'next_action', label: '下一动作' },
              { key: 'auto_review', label: '自动评审' },
              { key: 'auto_promoted', label: '自动晋级' },
            ]}
            rows={incubationState.incubationPipelineRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无孵化流水线快照</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">晋级评审记录</h3>
        {incubationState.promotionReviewRows.length ? (
          <DataTable
            columns={[
              { key: 'reviewed_at', label: '评审时间' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'approved' ? 'success' : value === 'rejected' ? 'danger' : 'warning'}>{String(value ?? '-')}</Badge> },
              { key: 'recommendation', label: '建议' },
              { key: 'score', label: '评分' },
              { key: 'stage', label: '阶段' },
              { key: 'review_source', label: '来源' },
              { key: 'blockers', label: '阻塞项' },
              { key: 'risk_flags', label: '风险项' },
            ]}
            rows={incubationState.promotionReviewRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无晋级评审记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">孵化模拟盘账户 / NAV 闭环</h3>
          <button
            type="button"
            onClick={onRunIncubationSync}
            disabled={runIncubationSyncPending}
            className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
          >
            {runIncubationSyncPending ? '同步中...' : '执行孵化同步'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={incubationState.paperAccountOverviewRows}
        />
        {incubationState.paperNavTableRows.length ? (
          <DataTable
            columns={[
              { key: 'nav_date', label: '日期' },
              { key: 'total_value', label: '总资产' },
              { key: 'cash', label: '现金' },
              { key: 'market_value', label: '市值' },
              { key: 'daily_return', label: '日收益' },
            ]}
            rows={incubationState.paperNavTableRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无孵化模拟盘 NAV 快照</p>
        )}
        {incubationState.paperPositionRows.length ? (
          <DataTable
            columns={[
              { key: 'stock_code', label: '代码' },
              { key: 'quantity', label: '持仓' },
              { key: 'cost_price', label: '成本价' },
              { key: 'current_price', label: '现价' },
              { key: 'market_value', label: '市值' },
              { key: 'profit_rate', label: '浮盈率' },
            ]}
            rows={incubationState.paperPositionRows}
            pageSize={8}
          />
        ) : null}
        {incubationState.paperOrderRows.length ? (
          <DataTable
            columns={[
              { key: 'signal_date', label: '信号日' },
              { key: 'code', label: '代码' },
              { key: 'direction', label: '方向' },
              { key: 'shares', label: '股数' },
              { key: 'price', label: '成交价' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'filled' ? 'success' : value === 'rejected' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'commission', label: '费用' },
              { key: 'source', label: '来源' },
              { key: 'filled_at', label: '成交时间' },
            ]}
            rows={incubationState.paperOrderRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无孵化模拟盘订单记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">模拟盘孵化指标</h3>
        {incubationState.metricRows.length ? (
          <DataTable
            columns={[
              { key: 'metric_date', label: '日期' },
              { key: 'nav', label: 'NAV' },
              { key: 'daily_return', label: '日收益' },
              { key: 'max_drawdown', label: '回撤' },
              { key: 'sharpe_ratio', label: 'Sharpe' },
              { key: 'exposure_rate', label: '暴露率' },
              { key: 'alpha_decay', label: 'Alpha衰减' },
              { key: 'drift_score', label: '漂移分数' },
              { key: 'decision', label: '决策' },
            ]}
            rows={incubationState.metricRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无孵化指标沉淀</p>
        )}
      </SectionCard>
    </>
  );
}

type RuntimeSectionProps = {
  runtimeState: FactoryReviewRuntimeState;
  onRunRiskScan: FactoryReviewPanelProps['onRunRiskScan'];
  runRiskScanPending: boolean;
  onRiskRecovery: FactoryReviewPanelProps['onRiskRecovery'];
  riskRecoveryPending: boolean;
  onRunRuntimeAlertDispatch: FactoryReviewPanelProps['onRunRuntimeAlertDispatch'];
  runRuntimeAlertDispatchPending: boolean;
  onAckRuntimeAlert: FactoryReviewPanelProps['onAckRuntimeAlert'];
  ackRuntimeAlertPending: boolean;
  onSetRuntimeControl: FactoryReviewPanelProps['onSetRuntimeControl'];
  setRuntimeControlPending: boolean;
  onResolveRiskEvent: FactoryReviewPanelProps['onResolveRiskEvent'];
  resolveRiskEventPending: boolean;
  onRunRuntimeCycle: FactoryReviewPanelProps['onRunRuntimeCycle'];
  runRuntimeCyclePending: boolean;
};

export function RuntimeSection({
  runtimeState,
  onRunRiskScan,
  runRiskScanPending,
  onRiskRecovery,
  riskRecoveryPending,
  onRunRuntimeAlertDispatch,
  runRuntimeAlertDispatchPending,
  onAckRuntimeAlert,
  ackRuntimeAlertPending,
  onSetRuntimeControl,
  setRuntimeControlPending,
  onResolveRiskEvent,
  resolveRiskEventPending,
  onRunRuntimeCycle,
  runRuntimeCyclePending,
}: RuntimeSectionProps) {
  const [controlMode, setControlMode] = useState('active');

  return (
    <>
      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">运行时风险姿态</h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onRunRuntimeCycle}
              disabled={runRuntimeCyclePending}
              className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
            >
              {runRuntimeCyclePending ? '运行中...' : '运行闭环'}
            </button>
            <button
              type="button"
              onClick={onRunRiskScan}
              disabled={runRiskScanPending}
              className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
            >
              {runRiskScanPending ? '扫描中...' : '执行风控扫描'}
            </button>
            <button
              type="button"
              onClick={onRiskRecovery}
              disabled={riskRecoveryPending}
              className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
            >
              {riskRecoveryPending ? '恢复中...' : '尝试恢复'}
            </button>
          </div>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={runtimeState.runtimeRiskOverviewRows}
        />
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded border border-border bg-surface-alt px-3 py-3">
          <span className="text-xs font-medium text-text-primary">控制模式</span>
          <select
            value={controlMode}
            onChange={(event) => setControlMode(event.target.value)}
            className="rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-primary"
          >
            <option value="active">active</option>
            <option value="guarded">guarded</option>
            <option value="manual_stop">manual_stop</option>
            <option value="halt_new_orders">halt_new_orders</option>
          </select>
          <button
            type="button"
            onClick={() => onSetRuntimeControl(controlMode)}
            disabled={setRuntimeControlPending}
            className="px-3 py-1.5 text-xs rounded bg-primary text-white cursor-pointer disabled:opacity-50"
          >
            {setRuntimeControlPending ? '提交中...' : '应用控制'}
          </button>
        </div>
        {runtimeState.runtimeRiskSnapshotRows.length ? (
          <DataTable
            columns={[
              { key: 'evaluated_at', label: '评估时间' },
              { key: 'posture_level', label: '姿态', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'guarded' ? 'warning' : value === 'recovering' ? 'info' : 'success'}>{String(value ?? '-')}</Badge> },
              { key: 'escalation_level', label: '升级级别' },
              { key: 'control_mode', label: '控制模式' },
              { key: 'open_event_count', label: '开放事件' },
              { key: 'critical_open_count', label: '关键事件' },
              { key: 'warning_open_count', label: '预警事件' },
              { key: 'recommended_action', label: '建议动作' },
              { key: 'recovery_eligible', label: '可恢复' },
            ]}
            rows={runtimeState.runtimeRiskSnapshotRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无风险姿态快照</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">运行态告警</h3>
          <button
            type="button"
            onClick={onRunRuntimeAlertDispatch}
            disabled={runRuntimeAlertDispatchPending}
            className="px-3 py-1.5 text-sm rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
          >
            {runRuntimeAlertDispatchPending ? '分发中...' : '重新分发告警'}
          </button>
        </div>
        <DataTable
          columns={[
            { key: 'item', label: '项目' },
            { key: 'value', label: '值' },
          ]}
          rows={runtimeState.runtimeAlertOverviewRows}
        />
        {runtimeState.runtimeAlertRows.length ? (
          <DataTable
            columns={[
              { key: 'created_at', label: '创建时间' },
              { key: 'updated_at', label: '更新时间' },
              { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'high' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'category', label: '分类' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'resolved' ? 'success' : value === 'acknowledged' ? 'info' : 'warning'}>{String(value ?? '-')}</Badge> },
              { key: 'title', label: '标题' },
              { key: 'message', label: '内容' },
              { key: 'escalation_level', label: '升级级别' },
              { key: 'acknowledged_by', label: '确认人' },
              { key: 'acknowledged_at', label: '确认时间' },
              {
                key: 'alert_id',
                label: '操作',
                render: (value, row) => {
                  const alertId = Number(value ?? 0);
                  const status = String(row.status ?? '');
                  if (!alertId || status === 'resolved' || status === 'acknowledged') return '-';
                  return (
                    <button
                      type="button"
                      onClick={() => onAckRuntimeAlert(alertId)}
                      disabled={ackRuntimeAlertPending}
                      className="px-2 py-1 text-xs rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
                    >
                      {ackRuntimeAlertPending ? '处理中...' : '确认'}
                    </button>
                  );
                },
              },
            ]}
            rows={runtimeState.runtimeAlertRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无运行态告警</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">运行时风控事件</h3>
        {runtimeState.riskRows.length ? (
          <DataTable
            columns={[
              { key: 'event_id', label: '事件ID' },
              { key: 'detected_at', label: '发现时间' },
              { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'high' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'event_type', label: '事件类型' },
              { key: 'action', label: '动作' },
              { key: 'status', label: '状态' },
              { key: 'title', label: '标题' },
              { key: 'reason', label: '原因' },
              {
                key: 'resolve_action',
                label: '处置',
                render: (_value, row) => {
                  const eventId = Number(row.event_id ?? 0);
                  const status = String(row.status ?? '');
                  if (!eventId || status === 'resolved') return '-';
                  return (
                    <button
                      type="button"
                      onClick={() => onResolveRiskEvent(eventId)}
                      disabled={resolveRiskEventPending}
                      className="px-2 py-1 text-xs rounded border border-primary text-primary cursor-pointer disabled:opacity-50"
                    >
                      {resolveRiskEventPending ? '处理中...' : '解决'}
                    </button>
                  );
                },
              },
            ]}
            rows={runtimeState.riskRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无实时风险事件</p>
        )}
      </SectionCard>
    </>
  );
}

export function VectorsSection({ vectorState }: { vectorState: FactoryReviewVectorState }) {
  return (
    <>
      <SectionCard className="p-3">
        <h3 className="mt-0">向量画像 / 去重画像</h3>
        {vectorState.profileRows.length ? (
          <DataTable
            columns={[
              { key: 'profile_type', label: '画像类型' },
              { key: 'vector_method', label: '向量方法' },
              { key: 'metric', label: '相似度' },
              { key: 'vector_dim', label: '维度' },
              { key: 'backend', label: '后端' },
              { key: 'index_version', label: '索引版本' },
              { key: 'signature', label: '签名' },
            ]}
            rows={vectorState.profileRows}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无向量画像</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">持久化向量索引</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <DataTable
            columns={[
              { key: 'item', label: '项目' },
              { key: 'value', label: '值' },
            ]}
            rows={vectorState.vectorIndexOverviewRows}
          />
          <div className="rounded-lg border border-border/60 bg-surface/60 p-3 text-sm text-text-secondary">
            最近一次 ANN-like 索引快照记录聚类桶、向量维度与重建版本，用于相似策略粗召回后再精排。
          </div>
        </div>
        {vectorState.indexSnapshotRows.length ? (
          <DataTable
            columns={[
              { key: 'built_at', label: '构建时间' },
              { key: 'index_version', label: '索引版本' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'active' ? 'success' : value === 'stale' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'profile_count', label: '画像数' },
              { key: 'bucket_count', label: '桶数' },
              { key: 'vector_dim', label: '维度' },
              { key: 'backend', label: '后端' },
              { key: 'source', label: '来源' },
            ]}
            rows={vectorState.indexSnapshotRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无持久化向量索引快照</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">相似策略检索</h3>
        {vectorState.similarProfileRows.length ? (
          <DataTable
            columns={[
              { key: 'strategy_id', label: '相似策略' },
              { key: 'profile_type', label: '画像类型' },
              { key: 'similarity', label: '相似度' },
              { key: 'coarse_score', label: '粗排分' },
              { key: 'bucket_id', label: '命中桶' },
              { key: 'query_bucket_id', label: '查询桶' },
              { key: 'candidate_count', label: '候选数' },
              { key: 'retrieval_mode', label: '召回模式' },
              { key: 'backend', label: '后端' },
              { key: 'index_version', label: '索引版本' },
              { key: 'signature', label: '签名' },
            ]}
            rows={vectorState.similarProfileRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无相似策略命中</p>
        )}
      </SectionCard>
    </>
  );
}

export function ExperimentsSection({
  experimentState,
  canViewOperatorPanels,
  onAiGenerateCandidate,
  aiGenerateCandidatePending,
}: {
  experimentState: FactoryReviewExperimentState;
  canViewOperatorPanels: boolean;
  onAiGenerateCandidate: FactoryReviewPanelProps['onAiGenerateCandidate'];
  aiGenerateCandidatePending: boolean;
}) {
  return (
    <>
      <SectionCard className="p-3">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="m-0">任务运行记录</h3>
          {canViewOperatorPanels ? (
            <button
              type="button"
              onClick={onAiGenerateCandidate}
              disabled={aiGenerateCandidatePending}
              className="px-3 py-1.5 text-sm rounded bg-primary text-white cursor-pointer disabled:opacity-50"
            >
              {aiGenerateCandidatePending ? '提交中...' : 'AI 生成候选'}
            </button>
          ) : null}
        </div>
        {experimentState.taskRunRows.length ? (
          <DataTable
            columns={[
              { key: 'started_at', label: '开始时间' },
              { key: 'completed_at', label: '完成时间' },
              { key: 'task_name', label: '任务' },
              { key: 'task_scope', label: '范围' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'completed' ? 'success' : value === 'failed' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'trace_id', label: 'Trace' },
              { key: 'result', label: '结果摘要' },
              { key: 'error', label: '错误' },
            ]}
            rows={experimentState.taskRunRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无任务运行记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">AI 生成实验</h3>
        {experimentState.experimentRows.length ? (
          <DataTable
            columns={[
              { key: 'experiment_id', label: '实验ID' },
              { key: 'lineage', label: '父子策略' },
              { key: 'source', label: '来源' },
              { key: 'generator_type', label: '生成器' },
              { key: 'optimizer_type', label: '优化器' },
              { key: 'score', label: '评分' },
              { key: 'review_decision', label: '委员会决策' },
              { key: 'review_breakdown', label: '评分拆解' },
              { key: 'review_issues', label: '主要问题' },
              { key: 'rank', label: '排序' },
              { key: 'champion', label: '冠军' },
              { key: 'status', label: '状态', render: (value) => <Badge variant={value === 'accepted' ? 'success' : value === 'rejected' ? 'danger' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'hypothesis', label: '假设' },
              { key: 'created_at', label: '创建时间' },
            ]}
            rows={experimentState.experimentRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无 AI 生成实验记录</p>
        )}
      </SectionCard>

      <SectionCard className="p-3">
        <h3 className="mt-0">领域事件流</h3>
        {experimentState.domainEventRows.length ? (
          <DataTable
            columns={[
              { key: 'created_at', label: '时间' },
              { key: 'event_type', label: '事件' },
              { key: 'source', label: '来源' },
              { key: 'severity', label: '级别', render: (value) => <Badge variant={value === 'critical' ? 'danger' : value === 'warning' ? 'warning' : 'info'}>{String(value ?? '-')}</Badge> },
              { key: 'aggregate', label: '聚合对象' },
              { key: 'payload', label: 'Payload 摘要' },
            ]}
            rows={experimentState.domainEventRows}
            pageSize={8}
          />
        ) : (
          <p className="text-sm text-text-secondary">暂无领域事件</p>
        )}
      </SectionCard>
    </>
  );
}
