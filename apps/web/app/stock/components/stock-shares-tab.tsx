import { SectionCard } from '@/components/ui';
import { StockCapitalPanel } from '@/components/stock-capital-panel';

type StockSharesTabProps = {
  activeCode: string | null;
};

export default function StockSharesTab({ activeCode }: StockSharesTabProps) {
  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">🏦 股本结构</h3>
      {activeCode ? <StockCapitalPanel code={activeCode} /> : <p className="text-sm text-text-secondary">查询股票后显示股本数据</p>}
    </SectionCard>
  );
}
