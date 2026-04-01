import { PeerComparisonTable } from '@/components/peer-comparison';
import { SectionCard } from '@/components/ui';

type StockPeersTabProps = {
  activeCode: string | null;
};

export default function StockPeersTab({ activeCode }: StockPeersTabProps) {
  return (
    <SectionCard tabAttached className="p-4 sm:p-5">
      <h3 className="mt-0">🏭 同行业对比</h3>
      {activeCode ? <PeerComparisonTable code={activeCode} /> : <p className="text-sm text-text-secondary">查询股票后显示同行对比</p>}
    </SectionCard>
  );
}
