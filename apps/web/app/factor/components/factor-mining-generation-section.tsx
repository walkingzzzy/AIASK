import { Badge, DataTable, KpiCard, KpiGrid, SectionCard } from '@/components/ui';
import { EmptyState, ErrorState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { factorMiningNoteCardCls, factorMiningPanelCls, factorMiningPrimaryButtonCls } from '@/app/factor/components/factor-mining-panel-styles';
import { joinList, mcpError } from '@/app/factor/components/factor-mining-mappers';
import { BadgeValue, MiningCheckbox, MiningField, renderWarnings } from '@/app/factor/components/factor-mining-support';

type FactorMiningGenerationSectionProps = {
  generationCodes: string;
  setGenerationCodes: (value: string) => void;
  generationCandidateCount: string;
  setGenerationCandidateCount: (value: string) => void;
  generationLookbackBars: string;
  setGenerationLookbackBars: (value: string) => void;
  generationArtifactId: string;
  setGenerationArtifactId: (value: string) => void;
  generationAllowFallback: boolean;
  setGenerationAllowFallback: (value: boolean) => void;
  generationPersistArtifact: boolean;
  setGenerationPersistArtifact: (value: boolean) => void;
  generationPending: boolean;
  onRun: () => void;
  generationData: unknown;
  generationRoot: Record<string, unknown>;
  generationCandidates: Array<Record<string, unknown>>;
  generationBlocked: Array<Record<string, unknown>>;
  generationDedupSummary: Record<string, unknown>;
  generationWarnings: unknown[];
  generationEpisode: Record<string, unknown>;
  generationEpisodeNovelty: Record<string, unknown>;
  generationEpisodeMemory: Record<string, unknown>;
  generationEpisodePrompt: Record<string, unknown>;
  generationEpisodeWarmup: Record<string, unknown>;
  generationEpisodeBlocked: Record<string, unknown>;
};

function displayWarmupStatus(value: unknown) {
  const status = String(value ?? 'disabled');
  if (status === 'disabled') return '未启用';
  if (status === 'ready') return '已就绪';
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  return status;
}

export default function FactorMiningGenerationSection({
  generationCodes,
  setGenerationCodes,
  generationCandidateCount,
  setGenerationCandidateCount,
  generationLookbackBars,
  setGenerationLookbackBars,
  generationArtifactId,
  setGenerationArtifactId,
  generationAllowFallback,
  setGenerationAllowFallback,
  generationPersistArtifact,
  setGenerationPersistArtifact,
  generationPending,
  onRun,
  generationData,
  generationRoot,
  generationCandidates,
  generationBlocked,
  generationDedupSummary,
  generationWarnings,
  generationEpisode,
  generationEpisodeNovelty,
  generationEpisodeMemory,
  generationEpisodePrompt,
  generationEpisodeWarmup,
  generationEpisodeBlocked,
}: FactorMiningGenerationSectionProps) {
  const generationError = generationData ? mcpError(generationData) : null;

  return (
    <SectionCard className="p-4 sm:p-5">
      <h3 className="mt-0">候选生成</h3>
      <div className={factorMiningPanelCls}>
        <div className="grid gap-3 lg:grid-cols-4">
          <MiningField
            id="factor-mining-codes"
            label="股票池"
            value={generationCodes}
            onChange={setGenerationCodes}
            placeholder="多个 6 位代码用英文逗号分隔"
          />
          <MiningField
            id="factor-mining-candidate-count"
            label="候选数量"
            type="number"
            value={generationCandidateCount}
            onChange={setGenerationCandidateCount}
            placeholder="默认 6"
          />
          <MiningField
            id="factor-mining-lookback"
            label="回看 K 线"
            type="number"
            value={generationLookbackBars}
            onChange={setGenerationLookbackBars}
            placeholder="默认 220"
          />
          <MiningField
            id="factor-mining-artifact-id"
            label="自定义制品 ID"
            value={generationArtifactId}
            onChange={setGenerationArtifactId}
            placeholder="可选"
          />
        </div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[repeat(2,minmax(0,220px))_auto]">
          <MiningCheckbox label="允许本地备用执行" checked={generationAllowFallback} onChange={setGenerationAllowFallback} />
          <MiningCheckbox label="持久化制品" checked={generationPersistArtifact} onChange={setGenerationPersistArtifact} />
          <div className="flex items-end">
            <button type="button" disabled={generationPending} onClick={onRun} className={`${factorMiningPrimaryButtonCls} w-full lg:w-auto`}>
              {generationPending ? '生成中...' : '生成候选'}
            </button>
          </div>
        </div>
      </div>

      {generationError ? (
        <ErrorState text={generationError} />
      ) : generationData ? (
        <>
          <KpiGrid cols={6}>
            <KpiCard title="制品" value={String(generationRoot.artifact_id ?? '-')} />
            <KpiCard title="保留候选" value={String(generationRoot.candidate_count ?? generationCandidates.length)} />
            <KpiCard title="生成模式" value={String(generationRoot.generation_mode ?? '-')} />
            <KpiCard title="去重前" value={String(generationRoot.pre_dedup_candidate_count ?? '-')} />
            <KpiCard title="去重后" value={String(generationDedupSummary.kept_count ?? generationRoot.candidate_count ?? '-')} />
            <KpiCard title="被拦截" value={String(generationDedupSummary.blocked_count ?? generationBlocked.length)} />
          </KpiGrid>
          <div className="mt-3 flex flex-wrap gap-2">
            <BadgeValue value={generationRoot.fallback_used} trueText="已使用备用执行" falseText="LLM 主链成功" />
            <BadgeValue value={generationRoot.degraded} trueText="存在降级/警告" falseText="无降级" />
          </div>
          {renderWarnings(generationWarnings)}
          {Object.keys(generationEpisode).length > 0 ? (
            <div className={`${factorMiningPanelCls} mt-4`}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">研究过程</div>
              <div className="mt-3 grid gap-3 xl:grid-cols-2">
                <div className={factorMiningNoteCardCls}>
                  <div className="font-medium text-text-primary">主题</div>
                  <div className="mt-2 leading-6">{String(generationEpisode.theme ?? '-')}</div>
                </div>
                <div className={factorMiningNoteCardCls}>
                  <div className="font-medium text-text-primary">核心假设</div>
                  <div className="mt-2 leading-6">{String(generationEpisode.hypothesis_summary ?? '-')}</div>
                </div>
                <div className={factorMiningNoteCardCls}>
                  <div className="font-medium text-text-primary">新颖度与记忆重叠</div>
                  <div className="mt-2 leading-6">
                    平均新颖度 {fmtNum(generationEpisodeNovelty.avg_novelty_score, 3)}，高新颖候选{' '}
                    {String(generationEpisodeNovelty.high_novelty_count ?? 0)} 个，记忆命中{' '}
                    {String(generationEpisodeMemory.matched_candidate_count ?? 0)} 个。
                  </div>
                </div>
                <div className={factorMiningNoteCardCls}>
                  <div className="font-medium text-text-primary">提示词与预热</div>
                  <div className="mt-2 leading-6">
                    提示词行数 {String(generationEpisodePrompt.row_count ?? 0)}，成功样例{' '}
                    {String(generationEpisodePrompt.memory_success_examples ?? 0)} 条，预热状态{' '}
                    {displayWarmupStatus(generationEpisodeWarmup.status)}。
                  </div>
                </div>
                <div className={factorMiningNoteCardCls}>
                  <div className="font-medium text-text-primary">被拦截候选</div>
                  <div className="mt-2 leading-6">
                    共 {String(generationEpisodeBlocked.count ?? 0)} 个，原因：
                    {joinList(Object.keys(generationEpisodeBlocked.reason_counts as Record<string, unknown> | undefined ?? {}))}
                  </div>
                </div>
                <div className={factorMiningNoteCardCls}>
                  <div className="font-medium text-text-primary">研究过程标识</div>
                  <div className="mt-2 leading-6">{String(generationEpisode.episode_id ?? generationRoot.artifact_id ?? '-')}</div>
                </div>
              </div>
            </div>
          ) : null}
          {generationCandidates.length > 0 ? (
            <DataTable
              rows={generationCandidates}
              searchable
              columns={[
                { key: 'name', label: '候选名称', sortable: true },
                {
                  key: 'family',
                  label: '因子族',
                  sortable: true,
                  render: (value) => (value ? <Badge variant="info">{String(value)}</Badge> : '-'),
                },
                { key: 'expression_dsl', label: '表达式', render: (value, row) => String(value ?? row.expression ?? '-') },
                { key: 'expected_regime', label: '适用环境', render: (value) => joinList(value) },
                { key: 'novelty_score', label: '新颖度', align: 'right', render: (value) => fmtNum(value, 3) },
              ]}
              onExport={() => exportCSV(generationCandidates, 'factor-mining-candidates')}
            />
          ) : (
            <EmptyState text="尚未生成候选因子" />
          )}
          {generationBlocked.length > 0 ? (
            <div className="mt-4">
              <h4 className="mb-2 text-sm font-medium text-text-primary">被拦截候选</h4>
              <DataTable
                rows={generationBlocked}
                searchable
                onExport={() => exportCSV(generationBlocked, 'factor-mining-blocked')}
              />
            </div>
          ) : null}
        </>
      ) : (
        <EmptyState text="填好股票池后即可生成候选因子" />
      )}
    </SectionCard>
  );
}
