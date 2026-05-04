import { Badge, SectionCard } from '@/components/ui';
import { ErrorState, LoadingState } from '@/components/status-state';
import { factorMiningNoteCardCls, factorMiningPanelCls } from '@/app/factor/components/factor-mining-panel-styles';

type FactorMiningIntroProps = {
  anyLoading: boolean;
  error: string | null;
};

export default function FactorMiningIntro({ anyLoading, error }: FactorMiningIntroProps) {
  return (
    <SectionCard className="p-4 sm:p-5">
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.25fr)_340px]">
        <div>
          <div className="eyebrow">AI 因子挖掘</div>
          <h3 className="mb-0 mt-2 text-xl font-semibold text-text-primary">AI 因子挖掘工作台</h3>
          <p className="mt-2 text-sm leading-7 text-text-secondary">
            这里处理候选生成、验证、研究记忆、候选池治理和调度巡检。典型顺序是“生成候选
            → 用验证制品复查 → 查看候选注册表和研究记忆 → 需要时回放研究过程”。
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="info">候选生成</Badge>
            <Badge variant="warning">验证与留痕</Badge>
            <Badge variant="success">治理与活跃池</Badge>
            <Badge variant="neutral">调度器巡检</Badge>
          </div>
        </div>

        <div className={factorMiningPanelCls}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">建议顺序</div>
          <div className="mt-4 space-y-3">
            <div className={factorMiningNoteCardCls}>1. 先生成候选，观察去重、拦截和降级提示，确认候选池质量。</div>
            <div className={factorMiningNoteCardCls}>2. 再用验证制品复查，把有效结果写入研究记忆并送进候选池治理。</div>
            <div className={factorMiningNoteCardCls}>3. 候选稳定后，再做研究过程回放与调度巡检。</div>
          </div>
        </div>
      </div>

      {anyLoading ? <LoadingState text="AI 因子挖掘正在运行..." /> : null}
      {error ? <ErrorState text={error} hint="请按生成 → 验证 → 治理的顺序检查输入" /> : null}
    </SectionCard>
  );
}
