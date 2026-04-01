import { AIDiagnosisPanel } from '@/components/ai-diagnosis-panel';
import { SectionCard } from '@/components/ui';

type StockAiTabProps = {
  activeCode: string | null;
};

export default function StockAiTab({ activeCode }: StockAiTabProps) {
  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">🤖 AI 智能诊断</h3>
      {activeCode ? <AIDiagnosisPanel key={activeCode} code={activeCode} /> : <p className="text-sm text-text-secondary">请先查询股票代码</p>}
    </SectionCard>
  );
}
