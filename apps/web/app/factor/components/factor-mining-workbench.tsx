'use client';

import { useState } from 'react';
import { Badge, DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { EmptyState, ErrorState } from '@/components/status-state';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useApiQuery } from '@/hooks/use-api-query';
import { extractArray, extractObject, fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import FactorMiningGenerationSection from '@/app/factor/components/factor-mining-generation-section';
import FactorMiningIntro from '@/app/factor/components/factor-mining-intro';
import {
  countRows,
  flattenMemoryRows,
  flattenRegistryRows,
  flattenReplayRows,
  isRecord,
  joinList,
  mcpError,
  parseOptionalInt,
  readArtifactId,
  splitCodes,
} from '@/app/factor/components/factor-mining-mappers';
import FactorMiningObservability from '@/app/factor/components/factor-mining-observability';
import {
  factorMiningPanelCls,
  factorMiningPrimaryButtonCls,
  factorMiningSecondaryButtonCls,
} from '@/app/factor/components/factor-mining-panel-styles';
import {
  BadgeValue,
  MiningCheckbox,
  MiningField,
  MiningSelect,
  renderWarnings,
} from '@/app/factor/components/factor-mining-support';

const DEFAULT_MINING_CODES = '';

export function FactorMiningWorkbench() {
  const [formError, setFormError] = useState<string | null>(null);

  const [generationCodes, setGenerationCodes] = useState(DEFAULT_MINING_CODES);
  const [generationCandidateCount, setGenerationCandidateCount] = useState('6');
  const [generationLookbackBars, setGenerationLookbackBars] = useState('220');
  const [generationArtifactId, setGenerationArtifactId] = useState('');
  const [generationAllowFallback, setGenerationAllowFallback] = useState(true);
  const [generationPersistArtifact, setGenerationPersistArtifact] = useState(true);

  const [validationArtifactId, setValidationArtifactId] = useState('');
  const [validationCandidateIndex, setValidationCandidateIndex] = useState('0');
  const [validationCodes, setValidationCodes] = useState(DEFAULT_MINING_CODES);
  const [validationLookbackBars, setValidationLookbackBars] = useState('220');
  const [validationHorizonDays, setValidationHorizonDays] = useState('10');
  const [validationMaxDates, setValidationMaxDates] = useState('60');
  const [validationWriteMemory, setValidationWriteMemory] = useState(true);
  const [validationPersistArtifact, setValidationPersistArtifact] = useState(true);

  const [memoryOp, setMemoryOp] = useState('stats');
  const [memoryArtifactId, setMemoryArtifactId] = useState('');
  const [memoryCodes, setMemoryCodes] = useState('');
  const [memoryQueryText, setMemoryQueryText] = useState('');
  const [memoryLimit, setMemoryLimit] = useState('20');

  const [registryOp, setRegistryOp] = useState('active_pool');
  const [registryArtifactId, setRegistryArtifactId] = useState('');
  const [registryCodes, setRegistryCodes] = useState('');
  const [registryLimit, setRegistryLimit] = useState('20');
  const [registryOnlyActive, setRegistryOnlyActive] = useState(true);

  const [replayOp, setReplayOp] = useState('run');
  const [replayArtifactId, setReplayArtifactId] = useState('');
  const [replaySourceArtifactId, setReplaySourceArtifactId] = useState('');
  const [replayCodes, setReplayCodes] = useState(DEFAULT_MINING_CODES);
  const [replayCandidateLimit, setReplayCandidateLimit] = useState('5');
  const [replayLookbackBars, setReplayLookbackBars] = useState('220');
  const [replayHorizonDays, setReplayHorizonDays] = useState('10');
  const [replayMaxDates, setReplayMaxDates] = useState('60');
  const [replayPersistArtifact, setReplayPersistArtifact] = useState(true);

  const [schedulerPath, setSchedulerPath] = useState<string | null>(null);
  const schedulerQ = useApiQuery<unknown>(schedulerPath, { staleTime: 10_000 });
  const observabilityQ = useApiQuery<unknown>('/factor/observability', { staleTime: 15_000 });

  const generationMut = useApiMutation<unknown>({
    onSuccess: (payload) => {
      const artifactId = readArtifactId(payload);
      if (!artifactId) return;
      setValidationArtifactId(artifactId);
      setReplayArtifactId(artifactId);
    },
  });
  const validationMut = useApiMutation<unknown>({
    onSuccess: (payload) => {
      const artifactId = readArtifactId(payload);
      if (!artifactId) return;
      setRegistryArtifactId(artifactId);
    },
  });
  const memoryMut = useApiMutation<unknown>();
  const registryMut = useApiMutation<unknown>();
  const replayMut = useApiMutation<unknown>();
  const schedulerRunMut = useApiMutation<unknown>();

  const anyLoading =
    generationMut.isPending ||
    validationMut.isPending ||
    memoryMut.isPending ||
    registryMut.isPending ||
    replayMut.isPending ||
    schedulerQ.isFetching ||
    schedulerRunMut.isPending;
  const error =
    formError ||
    generationMut.error ||
    validationMut.error ||
    memoryMut.error ||
    registryMut.error ||
    replayMut.error ||
    schedulerQ.error ||
    schedulerRunMut.error;

  const generationRoot = extractObject(generationMut.data);
  const generationCandidates = extractArray(generationMut.data, 'candidates');
  const generationBlocked = extractArray(generationMut.data, 'blocked_candidates');
  const generationDedupSummary = isRecord(generationRoot.dedup_summary) ? generationRoot.dedup_summary : {};
  const generationWarnings = Array.isArray(generationRoot.warnings) ? generationRoot.warnings : [];
  const generationEpisode = isRecord(generationRoot.research_episode) ? generationRoot.research_episode : {};
  const generationEpisodeNovelty = isRecord(generationEpisode.novelty_summary) ? generationEpisode.novelty_summary : {};
  const generationEpisodeMemory = isRecord(generationEpisode.memory_similarity_summary)
    ? generationEpisode.memory_similarity_summary
    : {};
  const generationEpisodePrompt = isRecord(generationEpisode.prompt_context_summary)
    ? generationEpisode.prompt_context_summary
    : {};
  const generationEpisodeWarmup = isRecord(generationEpisode.startup_warmup_summary)
    ? generationEpisode.startup_warmup_summary
    : {};
  const generationEpisodeBlocked = isRecord(generationEpisode.blocked_candidate_summary)
    ? generationEpisode.blocked_candidate_summary
    : {};

  const validationRoot = extractObject(validationMut.data);
  const validationRating = isRecord(validationRoot.rating) ? validationRoot.rating : {};
  const validationMetrics = isRecord(validationRoot.metrics) ? validationRoot.metrics : {};
  const validationOos = isRecord(validationRoot.oos_validation) ? validationRoot.oos_validation : {};
  const validationWarnings = Array.isArray(validationRoot.warnings) ? validationRoot.warnings : [];

  const memoryRoot = extractObject(memoryMut.data);
  const memoryItems = flattenMemoryRows(extractArray(memoryMut.data, 'items'));
  const memoryStats = isRecord(memoryRoot.stats) ? memoryRoot.stats : {};

  const registryRoot = extractObject(registryMut.data);
  const registrySummary = isRecord(registryRoot.summary) ? registryRoot.summary : {};
  const registryActivePool = isRecord(registryRoot.active_pool) ? registryRoot.active_pool : {};
  const registryRows = flattenRegistryRows(extractArray(registryMut.data, 'items', 'top_candidates'));
  const registryFamilySummary = extractArray(registryMut.data, 'family_summary');

  const replayRoot = extractObject(replayMut.data);
  const replaySummary = isRecord(replayRoot.episode_summary) ? replayRoot.episode_summary : {};
  const replayOutcomes = extractArray(replayMut.data, 'outcomes', 'items');
  const replayRows = flattenReplayRows(extractArray(replayMut.data, 'items'));

  const schedulerRoot = extractObject(schedulerQ.data);
  const schedulerLastResult = isRecord(schedulerRoot.last_result) ? schedulerRoot.last_result : {};
  const schedulerRunRoot = extractObject(schedulerRunMut.data);
  const observabilityRoot = extractObject(observabilityQ.data);
  const observabilityOverview = isRecord(observabilityRoot.overview) ? observabilityRoot.overview : {};
  const observabilityScheduler = isRecord(observabilityRoot.scheduler) ? observabilityRoot.scheduler : {};
  const observabilityRecentRun = isRecord(observabilityRoot.recent_run) ? observabilityRoot.recent_run : {};
  const observabilityRecentValidation = isRecord(observabilityRecentRun.llm_validation)
    ? observabilityRecentRun.llm_validation
    : {};
  const observabilityRegistrySummary = isRecord(observabilityRoot.registry_summary)
    ? observabilityRoot.registry_summary
    : {};
  const observabilityActivePool = isRecord(observabilityRoot.active_pool) ? observabilityRoot.active_pool : {};
  const observabilityMemoryStats = isRecord(observabilityRoot.memory_stats) ? observabilityRoot.memory_stats : {};
  const observabilityRetrainSummary = isRecord(observabilityRoot.retrain_summary)
    ? observabilityRoot.retrain_summary
    : {};
  const observabilityRetrainQueue = extractArray(observabilityRoot, 'retrain_queue');
  const observabilityErrors = Array.isArray(observabilityRoot.errors) ? observabilityRoot.errors : [];
  const observabilityFamilyRows = extractArray(observabilityActivePool, 'family_summary');
  const observabilityRegimeRows = extractArray(observabilityActivePool, 'regime_summary');
  const observabilityExclusionRows = countRows(observabilityActivePool.exclusion_reason_counts, 'reason');
  const observabilityStageRows = countRows(observabilityRegistrySummary.registry_stage_counts, 'registry_stage');

  function requireCodes(raw: string, minimum = 1) {
    const codes = splitCodes(raw);
    if (codes.length < minimum) {
      setFormError(`至少需要 ${minimum} 个股票代码`);
      return null;
    }
    const invalid = codes.find((code) => !/^\d{6}$/.test(code));
    if (invalid) {
      setFormError(`股票代码格式错误: ${invalid}（需为 6 位数字）`);
      return null;
    }
    return codes;
  }

  function loadSchedulerStatus() {
    setFormError(null);
    if (schedulerPath) {
      void schedulerQ.refetch();
      return;
    }
    setSchedulerPath('/factor/scheduler-status');
  }

  async function runSchedulerNow() {
    setFormError(null);
    await schedulerRunMut.triggerAsync('/factor/scheduler-run-now', { method: 'POST' });
    if (schedulerPath) {
      await schedulerQ.refetch();
    } else {
      setSchedulerPath('/factor/scheduler-status');
    }
  }

  return (
    <div id="factor-mining-workbench" className="mt-5">
      <FactorMiningIntro anyLoading={anyLoading} error={error} />

      <FactorMiningObservability
        isPending={observabilityQ.isPending}
        error={observabilityQ.error}
        hasData={Boolean(observabilityQ.data)}
        degraded={Boolean(observabilityRoot.degraded)}
        observabilityOverview={observabilityOverview}
        observabilityScheduler={observabilityScheduler}
        observabilityRecentValidation={observabilityRecentValidation}
        observabilityMemoryStats={observabilityMemoryStats}
        observabilityRetrainSummary={observabilityRetrainSummary}
        observabilityRetrainQueue={observabilityRetrainQueue as Array<Record<string, unknown>>}
        observabilityErrors={observabilityErrors}
        observabilityFamilyRows={observabilityFamilyRows as Array<Record<string, unknown>>}
        observabilityRegimeRows={observabilityRegimeRows as Array<Record<string, unknown>>}
        observabilityExclusionRows={observabilityExclusionRows as Array<Record<string, unknown>>}
        observabilityStageRows={observabilityStageRows as Array<Record<string, unknown>>}
      />

      <FactorMiningGenerationSection
        generationCodes={generationCodes}
        setGenerationCodes={setGenerationCodes}
        generationCandidateCount={generationCandidateCount}
        setGenerationCandidateCount={setGenerationCandidateCount}
        generationLookbackBars={generationLookbackBars}
        setGenerationLookbackBars={setGenerationLookbackBars}
        generationArtifactId={generationArtifactId}
        setGenerationArtifactId={setGenerationArtifactId}
        generationAllowFallback={generationAllowFallback}
        setGenerationAllowFallback={setGenerationAllowFallback}
        generationPersistArtifact={generationPersistArtifact}
        setGenerationPersistArtifact={setGenerationPersistArtifact}
        generationPending={generationMut.isPending}
        onRun={() => {
          setFormError(null);
          const codes = requireCodes(generationCodes, 1);
          if (!codes) return;
          generationMut.trigger(
            '/factor/candidate-workflow',
            { method: 'POST' },
            {
              task: 'generate',
              stock_codes: codes,
              candidate_count: parseOptionalInt(generationCandidateCount),
              lookback_bars: parseOptionalInt(generationLookbackBars),
              artifact_id: generationArtifactId.trim() || undefined,
              allow_fallback: generationAllowFallback,
              persist_artifact: generationPersistArtifact,
            },
          );
        }}
        generationData={generationMut.data}
        generationRoot={generationRoot}
        generationCandidates={generationCandidates as Array<Record<string, unknown>>}
        generationBlocked={generationBlocked as Array<Record<string, unknown>>}
        generationDedupSummary={generationDedupSummary}
        generationWarnings={generationWarnings}
        generationEpisode={generationEpisode}
        generationEpisodeNovelty={generationEpisodeNovelty}
        generationEpisodeMemory={generationEpisodeMemory}
        generationEpisodePrompt={generationEpisodePrompt}
        generationEpisodeWarmup={generationEpisodeWarmup}
        generationEpisodeBlocked={generationEpisodeBlocked}
      />

      <SectionCard className="p-4 sm:p-5">
        <h3 className="mt-0">候选验证</h3>
        <p className="mt-2 text-sm text-text-secondary">
          验证优先吃上一步产出的 mining artifact。横截面验证至少需要 3 只股票。
        </p>
        <div className={factorMiningPanelCls}>
          <div className="grid gap-3 lg:grid-cols-3">
            <MiningField
              id="factor-validate-artifact"
              label="mining artifact"
              value={validationArtifactId}
              onChange={setValidationArtifactId}
              placeholder="例如 factor_llm_..."
            />
            <MiningField
              id="factor-validate-index"
              label="候选序号"
              type="number"
              value={validationCandidateIndex}
              onChange={setValidationCandidateIndex}
              placeholder="默认 0"
            />
            <MiningField
              id="factor-validate-codes"
              label="验证股票池"
              value={validationCodes}
              onChange={setValidationCodes}
              placeholder="至少 3 个代码"
            />
          </div>
          <div className="mt-3 grid gap-3 lg:grid-cols-5">
            <MiningField
              id="factor-validate-lookback"
              label="回看 K 线"
              type="number"
              value={validationLookbackBars}
              onChange={setValidationLookbackBars}
              placeholder="220"
            />
            <MiningField
              id="factor-validate-horizon"
              label="前瞻天数"
              type="number"
              value={validationHorizonDays}
              onChange={setValidationHorizonDays}
              placeholder="10"
            />
            <MiningField
              id="factor-validate-max-dates"
              label="截面日期数"
              type="number"
              value={validationMaxDates}
              onChange={setValidationMaxDates}
              placeholder="60"
            />
            <MiningCheckbox label="写入研究记忆" checked={validationWriteMemory} onChange={setValidationWriteMemory} />
            <MiningCheckbox
              label="持久化验证 artifact"
              checked={validationPersistArtifact}
              onChange={setValidationPersistArtifact}
            />
          </div>
          <div className="mt-3">
            <button
              type="button"
              disabled={validationMut.isPending}
              onClick={() => {
                setFormError(null);
                if (!validationArtifactId.trim()) {
                  setFormError('请先提供生成阶段的 artifact_id');
                  return;
                }
                const codes = requireCodes(validationCodes, 3);
                if (!codes) return;
                validationMut.trigger(
                  '/factor/candidate-workflow',
                  { method: 'POST' },
                  {
                    task: 'validate',
                    artifact_id: validationArtifactId.trim(),
                    candidate_index: parseOptionalInt(validationCandidateIndex),
                    stock_codes: codes,
                    lookback_bars: parseOptionalInt(validationLookbackBars),
                    horizon_days: parseOptionalInt(validationHorizonDays),
                    max_dates: parseOptionalInt(validationMaxDates),
                    write_memory: validationWriteMemory,
                    persist_artifact: validationPersistArtifact,
                  },
                );
              }}
              className={factorMiningPrimaryButtonCls}
            >
              {validationMut.isPending ? '验证中...' : '运行验证'}
            </button>
          </div>
        </div>

        {validationMut.data && mcpError(validationMut.data) ? (
          <ErrorState text={mcpError(validationMut.data)!} />
        ) : validationMut.data ? (
          <>
            <KpiGrid cols={6}>
              <KpiCard title="artifact" value={String(validationRoot.artifact_id ?? '-')} />
              <KpiCard title="评级" value={String(validationRating.grade ?? '-')} />
              <KpiCard title="建议" value={String(validationRating.recommendation ?? '-')} />
              <KpiCard title="总分" value={fmtNum(validationRating.total_score, 3)} />
              <KpiCard title="Rank IC" value={fmtNum(validationMetrics.rank_ic_mean, 4)} />
              <KpiCard title="OOS 通过" value={validationOos.passed ? '通过' : '未通过'} />
            </KpiGrid>
            <div className="mt-3 flex flex-wrap gap-2">
              <BadgeValue value={validationRoot.degraded} trueText="验证有警告" falseText="验证正常" />
              <BadgeValue value={validationOos.passed} trueText="样本外通过" falseText="样本外待观察" />
            </div>
            {renderWarnings(validationWarnings)}
            <DataTable
              rows={[
                {
                  name: validationRoot.candidate ? (validationRoot.candidate as Record<string, unknown>).name : '-',
                  family: validationRoot.candidate ? (validationRoot.candidate as Record<string, unknown>).family : '-',
                  expression_dsl: validationRoot.candidate
                    ? ((validationRoot.candidate as Record<string, unknown>).expression_dsl ??
                      (validationRoot.candidate as Record<string, unknown>).expression)
                    : '-',
                  rank_ic_mean: validationMetrics.rank_ic_mean,
                  rank_ic_ir: validationMetrics.rank_ic_ir,
                  coverage_ratio: isRecord(validationRoot.coverage)
                    ? validationRoot.coverage.coverage_ratio
                    : undefined,
                  turnover_mean: isRecord(validationRoot.turnover) ? validationRoot.turnover.turnover_mean : undefined,
                },
              ]}
              columns={[
                { key: 'name', label: '候选' },
                { key: 'family', label: '因子族' },
                { key: 'expression_dsl', label: '表达式' },
                { key: 'rank_ic_mean', label: 'Rank IC', align: 'right', render: (value) => fmtNum(value, 4) },
                { key: 'rank_ic_ir', label: 'Rank IC IR', align: 'right', render: (value) => fmtNum(value, 4) },
                { key: 'coverage_ratio', label: '覆盖率', align: 'right', render: (value) => fmtNum(value, 3) },
                { key: 'turnover_mean', label: '换手', align: 'right', render: (value) => fmtNum(value, 3) },
              ]}
            />
          </>
        ) : (
          <EmptyState text="生成 artifact 后，可在这里做横截面验证并写入研究记忆" />
        )}
      </SectionCard>

      <SectionCard className="p-4 sm:p-5">
        <h3 className="mt-0">研究记忆与候选池治理</h3>
        <div className="grid gap-6 xl:grid-cols-2">
          <div className={factorMiningPanelCls}>
            <h4 className="mb-2 text-sm font-medium text-text-primary">研究记忆</h4>
            <div className="grid gap-3 lg:grid-cols-2">
              <MiningSelect
                id="factor-memory-op"
                label="动作"
                value={memoryOp}
                onChange={setMemoryOp}
                options={[
                  { label: 'stats', value: 'stats' },
                  { label: 'list', value: 'list' },
                  { label: 'recall', value: 'recall' },
                  { label: 'get', value: 'get' },
                ]}
              />
              <MiningField
                id="factor-memory-artifact"
                label="artifact"
                value={memoryArtifactId}
                onChange={setMemoryArtifactId}
                placeholder="get 时必填"
              />
              <MiningField
                id="factor-memory-codes"
                label="股票池"
                value={memoryCodes}
                onChange={setMemoryCodes}
                placeholder="可选"
              />
              <MiningField
                id="factor-memory-limit"
                label="限制条数"
                type="number"
                value={memoryLimit}
                onChange={setMemoryLimit}
                placeholder="20"
              />
            </div>
            <div className="mt-3">
              <MiningField
                id="factor-memory-query"
                label="召回关键词"
                value={memoryQueryText}
                onChange={setMemoryQueryText}
                placeholder="recall 时可填 research / family / expression 关键词"
              />
            </div>
            <div className="mt-3">
              <button
                type="button"
                disabled={memoryMut.isPending}
                onClick={() => {
                  setFormError(null);
                  if (memoryOp === 'get' && !memoryArtifactId.trim()) {
                    setFormError('research_memory get 需要 artifact_id');
                    return;
                  }
                  memoryMut.trigger(
                    '/factor/research-memory',
                    { method: 'POST' },
                    {
                      op: memoryOp,
                      artifact_id: memoryArtifactId.trim() || undefined,
                      stock_codes: memoryCodes.trim() ? splitCodes(memoryCodes) : undefined,
                      query_text: memoryQueryText.trim() || undefined,
                      limit: parseOptionalInt(memoryLimit),
                    },
                  );
                }}
                className={factorMiningPrimaryButtonCls}
              >
                {memoryMut.isPending ? '查询中...' : '查询记忆'}
              </button>
            </div>

            {memoryMut.data && mcpError(memoryMut.data) ? (
              <ErrorState text={mcpError(memoryMut.data)!} />
            ) : memoryMut.data ? (
              <>
                {memoryOp === 'stats' && isRecord(memoryStats) ? (
                  <KpiGrid cols={5}>
                    <KpiCard title="记录总数" value={String(memoryStats.total_records ?? '-')} />
                    <KpiCard title="高相似记录" value={String(memoryStats.duplicate_like_count ?? '-')} />
                    <KpiCard title="失败模式" value={String(memoryStats.failure_pattern_count ?? '-')} />
                    <KpiCard title="不稳定记录" value={String(memoryStats.unstable_count ?? '-')} />
                    <KpiCard title="平均相似度" value={fmtNum(memoryStats.avg_top_similarity, 3)} />
                  </KpiGrid>
                ) : null}
                {memoryItems.length > 0 ? (
                  <DataTable
                    rows={memoryItems}
                    searchable
                    onExport={() => exportCSV(memoryItems, 'factor-research-memory')}
                  />
                ) : memoryOp !== 'stats' ? (
                  <EmptyState text="当前查询未返回研究记忆记录" />
                ) : null}
              </>
            ) : null}
          </div>

          <div className={factorMiningPanelCls}>
            <h4 className="mb-2 text-sm font-medium text-text-primary">候选池治理</h4>
            <div className="grid gap-3 lg:grid-cols-2">
              <MiningSelect
                id="factor-registry-op"
                label="动作"
                value={registryOp}
                onChange={(next) => {
                  setRegistryOp(next);
                  setRegistryOnlyActive(next === 'active_pool');
                }}
                options={[
                  { label: 'active_pool', value: 'active_pool' },
                  { label: 'summary', value: 'summary' },
                  { label: 'list', value: 'list' },
                  { label: 'get', value: 'get' },
                ]}
              />
              <MiningField
                id="factor-registry-artifact"
                label="验证 artifact"
                value={registryArtifactId}
                onChange={setRegistryArtifactId}
                placeholder="get 时必填"
              />
              <MiningField
                id="factor-registry-codes"
                label="股票池"
                value={registryCodes}
                onChange={setRegistryCodes}
                placeholder="可选"
              />
              <MiningField
                id="factor-registry-limit"
                label="限制条数"
                type="number"
                value={registryLimit}
                onChange={setRegistryLimit}
                placeholder="20"
              />
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-[220px_auto]">
              <MiningCheckbox label="只看 active" checked={registryOnlyActive} onChange={setRegistryOnlyActive} />
              <div className="flex items-end">
                <button
                  type="button"
                  disabled={registryMut.isPending}
                  onClick={() => {
                    setFormError(null);
                    if (registryOp === 'get' && !registryArtifactId.trim()) {
                      setFormError('candidate_registry get 需要 artifact_id');
                      return;
                    }
                    registryMut.trigger(
                      '/factor/candidate-registry',
                      { method: 'POST' },
                      {
                        op: registryOp,
                        artifact_id: registryArtifactId.trim() || undefined,
                        stock_codes: registryCodes.trim() ? splitCodes(registryCodes) : undefined,
                        limit: parseOptionalInt(registryLimit),
                        only_active: registryOnlyActive,
                      },
                    );
                  }}
                  className={`${factorMiningPrimaryButtonCls} w-full lg:w-auto`}
                >
                  {registryMut.isPending ? '查询中...' : '查询候选池'}
                </button>
              </div>
            </div>

            {registryMut.data && mcpError(registryMut.data) ? (
              <ErrorState text={mcpError(registryMut.data)!} />
            ) : registryMut.data ? (
              <>
                <KpiGrid cols={5}>
                  <KpiCard title="候选数" value={String(registrySummary.count ?? registryActivePool.count ?? '-')} />
                  <KpiCard title="活跃数" value={String(registrySummary.active_count ?? '-')} />
                  <KpiCard title="平均分" value={fmtNum(registrySummary.avg_total_score, 3)} />
                  <KpiCard title="最高分" value={fmtNum(registrySummary.max_total_score, 3)} />
                  <KpiCard
                    title="Top Candidate"
                    value={String((extractArray(registryMut.data, 'top_candidates')[0] ?? {}).name ?? '-')}
                  />
                </KpiGrid>
                {registryRows.length > 0 ? (
                  <DataTable
                    rows={registryRows}
                    searchable
                    onExport={() => exportCSV(registryRows, 'factor-candidate-registry')}
                  />
                ) : registryFamilySummary.length > 0 ? (
                  <DataTable
                    rows={registryFamilySummary}
                    searchable
                    onExport={() => exportCSV(registryFamilySummary, 'factor-active-pool-family-summary')}
                  />
                ) : (
                  <EmptyState text="当前查询未返回治理候选" />
                )}
              </>
            ) : null}
          </div>
        </div>
      </SectionCard>

      <SectionCard className="p-4 sm:p-5">
        <h3 className="mt-0">Episode 回放与调度巡检</h3>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
          <div className={factorMiningPanelCls}>
            <h4 className="mb-2 text-sm font-medium text-text-primary">回放 Episode</h4>
            <div className="grid gap-3 lg:grid-cols-3">
              <MiningSelect
                id="factor-replay-op"
                label="动作"
                value={replayOp}
                onChange={setReplayOp}
                options={[
                  { label: 'run', value: 'run' },
                  { label: 'summary', value: 'summary' },
                  { label: 'list', value: 'list' },
                  { label: 'get', value: 'get' },
                ]}
              />
              <MiningField
                id="factor-replay-artifact"
                label="mining / replay artifact"
                value={replayArtifactId}
                onChange={setReplayArtifactId}
                placeholder="run/get 时常用"
              />
              <MiningField
                id="factor-replay-source-artifact"
                label="source artifact"
                value={replaySourceArtifactId}
                onChange={setReplaySourceArtifactId}
                placeholder="list/summary 可选"
              />
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-4">
              <MiningField
                id="factor-replay-codes"
                label="回放股票池"
                value={replayCodes}
                onChange={setReplayCodes}
                placeholder="run 时建议 3 只以上"
              />
              <MiningField
                id="factor-replay-candidate-limit"
                label="候选上限"
                type="number"
                value={replayCandidateLimit}
                onChange={setReplayCandidateLimit}
                placeholder="5"
              />
              <MiningField
                id="factor-replay-lookback"
                label="回看 K 线"
                type="number"
                value={replayLookbackBars}
                onChange={setReplayLookbackBars}
                placeholder="220"
              />
              <MiningCheckbox
                label="持久化回放 artifact"
                checked={replayPersistArtifact}
                onChange={setReplayPersistArtifact}
              />
            </div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <MiningField
                id="factor-replay-horizon"
                label="前瞻天数"
                type="number"
                value={replayHorizonDays}
                onChange={setReplayHorizonDays}
                placeholder="10"
              />
              <MiningField
                id="factor-replay-max-dates"
                label="截面日期数"
                type="number"
                value={replayMaxDates}
                onChange={setReplayMaxDates}
                placeholder="60"
              />
            </div>
            <div className="mt-3">
              <button
                type="button"
                disabled={replayMut.isPending}
                onClick={() => {
                  setFormError(null);
                  if ((replayOp === 'run' || replayOp === 'get') && !replayArtifactId.trim()) {
                    setFormError('replay 运行或详情需要 artifact_id');
                    return;
                  }
                  if (replayOp === 'run' && replayCodes.trim()) {
                    const codes = requireCodes(replayCodes, 3);
                    if (!codes) return;
                    replayMut.trigger(
                      '/factor/replay-episode',
                      { method: 'POST' },
                      {
                        op: replayOp,
                        artifact_id: replayArtifactId.trim(),
                        stock_codes: codes,
                        candidate_limit: parseOptionalInt(replayCandidateLimit),
                        lookback_bars: parseOptionalInt(replayLookbackBars),
                        horizon_days: parseOptionalInt(replayHorizonDays),
                        max_dates: parseOptionalInt(replayMaxDates),
                        persist_artifact: replayPersistArtifact,
                      },
                    );
                    return;
                  }
                  replayMut.trigger(
                    '/factor/replay-episode',
                    { method: 'POST' },
                    {
                      op: replayOp,
                      artifact_id: replayArtifactId.trim() || undefined,
                      source_artifact_id: replaySourceArtifactId.trim() || undefined,
                      stock_codes: replayCodes.trim() ? splitCodes(replayCodes) : undefined,
                      candidate_limit: parseOptionalInt(replayCandidateLimit),
                      lookback_bars: parseOptionalInt(replayLookbackBars),
                      horizon_days: parseOptionalInt(replayHorizonDays),
                      max_dates: parseOptionalInt(replayMaxDates),
                      persist_artifact: replayPersistArtifact,
                    },
                  );
                }}
                className={factorMiningPrimaryButtonCls}
              >
                {replayMut.isPending ? '回放中...' : '执行回放'}
              </button>
            </div>

            {replayMut.data && mcpError(replayMut.data) ? (
              <ErrorState text={mcpError(replayMut.data)!} />
            ) : replayMut.data ? (
              <>
                {isRecord(replaySummary) || replayRows.length > 0 ? (
                  <KpiGrid cols={5}>
                    <KpiCard title="回放 artifact" value={String(replayRoot.artifact_id ?? '-')} />
                    <KpiCard
                      title="验证成功"
                      value={String(replaySummary.validated_count ?? replaySummary.replayed_candidate_count ?? '-')}
                    />
                    <KpiCard title="验证失败" value={String(replaySummary.failed_count ?? '-')} />
                    <KpiCard
                      title="最佳候选"
                      value={String(
                        (isRecord(replaySummary.best_candidate) ? replaySummary.best_candidate.name : undefined) ?? '-',
                      )}
                    />
                    <KpiCard
                      title="平均成功率"
                      value={
                        replayRoot.summary
                          ? `${fmtNum(Number((replayRoot.summary as Record<string, unknown>).avg_success_rate ?? 0) * 100, 1)}%`
                          : '-'
                      }
                    />
                  </KpiGrid>
                ) : null}
                {replayOutcomes.length > 0 ? (
                  <DataTable
                    rows={replayOutcomes}
                    searchable
                    onExport={() => exportCSV(replayOutcomes, 'factor-replay-outcomes')}
                  />
                ) : replayRows.length > 0 ? (
                  <DataTable
                    rows={replayRows}
                    searchable
                    onExport={() => exportCSV(replayRows, 'factor-replay-history')}
                  />
                ) : (
                  <EmptyState text="当前未返回回放结果" />
                )}
              </>
            ) : null}
          </div>

          <div className={factorMiningPanelCls}>
            <h4 className="mb-2 text-sm font-medium text-text-primary">调度器状态</h4>
            <p className="mt-2 text-sm text-text-secondary">
              `scheduler_status` 直接读取 `factor_scheduler.status()`，`run_now` 会触发一次即时批处理并回写最近结果。
            </p>
            <div className="mt-3 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={loadSchedulerStatus}
                disabled={schedulerQ.isFetching}
                className={factorMiningSecondaryButtonCls}
              >
                {schedulerQ.isFetching ? '刷新中...' : '加载状态'}
              </button>
              <button
                type="button"
                onClick={() => void runSchedulerNow()}
                disabled={schedulerRunMut.isPending}
                className={factorMiningPrimaryButtonCls}
              >
                {schedulerRunMut.isPending ? '执行中...' : '立即运行一次'}
              </button>
            </div>

            {schedulerQ.data ? (
              <>
                <KpiGrid cols={4} className="mt-3">
                  <KpiCard title="运行中" value={schedulerRoot.running ? '是' : '否'} />
                  <KpiCard title="调度时间" value={String(schedulerRoot.run_time ?? '-')} />
                  <KpiCard title="股票池规模" value={String(schedulerRoot.universe_size ?? '-')} />
                  <KpiCard title="新鲜度(s)" value={fmtNum(schedulerRoot.freshness_sec, 1)} />
                </KpiGrid>
                <div className="mt-3 flex flex-wrap gap-2">
                  {Array.isArray(schedulerRoot.quality_flags) && schedulerRoot.quality_flags.length > 0 ? (
                    schedulerRoot.quality_flags.map((item, index) => (
                      <Badge
                        key={`${String(item)}-${index}`}
                        variant={String(item).includes('fail') || String(item).includes('degraded') ? 'danger' : 'info'}
                      >
                        {String(item)}
                      </Badge>
                    ))
                  ) : (
                    <Badge variant="success">quality_flags: clean</Badge>
                  )}
                </div>
                {isRecord(schedulerLastResult) ? (
                  <DataTable
                    rows={[schedulerLastResult]}
                    columns={[
                      { key: 'computed', label: '已计算' },
                      { key: 'errors', label: '错误数' },
                      { key: 'elapsed_seconds', label: '耗时(s)', render: (value) => fmtNum(value, 1) },
                      { key: 'asof_time', label: '最近完成时间' },
                      { key: 'quality_flags', label: '质量标记', render: (value) => joinList(value) },
                    ]}
                  />
                ) : null}
              </>
            ) : (
              <EmptyState text="点击“加载状态”查看 factor scheduler 的当前状态" />
            )}

            {schedulerRunMut.data && !mcpError(schedulerRunMut.data) ? (
              <div className="mt-4">
                <h5 className="mb-2 text-sm font-medium text-text-primary">最近手动执行结果</h5>
                <DataTable
                  rows={[schedulerRunRoot]}
                  columns={[
                    { key: 'computed', label: '已计算' },
                    { key: 'errors', label: '错误数' },
                    { key: 'elapsed_seconds', label: '耗时(s)', render: (value) => fmtNum(value, 1) },
                    { key: 'universe_size', label: '股票池规模' },
                    { key: 'quality_flags', label: '质量标记', render: (value) => joinList(value) },
                  ]}
                />
              </div>
            ) : null}
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
