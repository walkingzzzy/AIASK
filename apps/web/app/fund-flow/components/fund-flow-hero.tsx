import Link from 'next/link';
import LightOverviewHero from '@/components/light-overview-hero';
import { Badge } from '@/components/ui';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import {
  fundFlowLinkChipCls,
  fundFlowNoteCardCls,
  fundFlowPrimaryButtonCls,
  fundFlowSecondaryButtonCls,
} from '@/app/fund-flow/components/fund-flow-panel-styles';

type FundFlowHeroProps = {
  activeTabLabel: string;
  hasError: boolean;
  loading: boolean;
  tabStatusLabel: string;
  activeCodeLabel: string;
  heroNotes: string[];
  resolvedCode: string | null;
  onOpenStockFlow: () => void;
  onOpenNorthFlow: () => void;
};

export default function FundFlowHero({
  activeTabLabel,
  hasError,
  loading,
  tabStatusLabel,
  activeCodeLabel,
  heroNotes,
  resolvedCode,
  onOpenStockFlow,
  onOpenNorthFlow,
}: FundFlowHeroProps) {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.splitCollapse);

  return (
    <LightOverviewHero
      eyebrow="Flow Workspace"
      title="资金流向工作台"
      summary="先判断钱正在流向哪里，再把个股、板块、北向和融资融券这几类观察路径收束到同一套工作台语言里。"
      badges={(
        <>
          <Badge variant="info">Flow Workspace</Badge>
          <Badge variant="neutral">{activeTabLabel}</Badge>
          <Badge variant={hasError ? 'warning' : loading ? 'warning' : 'success'}>{tabStatusLabel}</Badge>
        </>
      )}
      actions={(
        <>
          <button type="button" onClick={onOpenStockFlow} className={fundFlowPrimaryButtonCls}>
            查看个股资金流
          </button>
          <button type="button" onClick={onOpenNorthFlow} className={fundFlowSecondaryButtonCls}>
            查看北向资金
          </button>
        </>
      )}
      status={(
        <div
          data-testid="page-primary-status"
          className="rounded-[20px] border border-white/50 bg-white/28 px-4 py-3 text-sm shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]"
        >
          <div className="font-medium text-text-primary">
            当前视角 {activeTabLabel} ｜ 当前代码 {activeCodeLabel} ｜ 状态 {tabStatusLabel}
          </div>
          <p className="mb-0 mt-1 text-xs leading-6 text-text-secondary">看完资金流后可直接跳到市场、研究、风险或自选。</p>
        </div>
      )}
      metrics={[
        { key: 'flow-view', label: '当前视角', value: activeTabLabel },
        { key: 'flow-code', label: '当前代码', value: activeCodeLabel },
        { key: 'flow-status', label: '状态', value: tabStatusLabel },
      ]}
      compact={compactLayout}
      detailsTitle="展开阅读建议与快捷跳转"
      detailsContent={(
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {heroNotes.map((note) => (
              <div key={note} className={fundFlowNoteCardCls}>
                {note}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/market" className={fundFlowLinkChipCls}>
              市场看板
            </Link>
            <Link href="/research" className={fundFlowLinkChipCls}>
              研究分析
            </Link>
            <Link href="/watchlist" className={fundFlowLinkChipCls}>
              自选联动
            </Link>
            <Link href="/risk" className={fundFlowLinkChipCls}>
              风险页
            </Link>
          </div>
          {resolvedCode ? (
            <div className="flex flex-wrap items-center gap-2">
              <StockLink code={resolvedCode} name={resolvedCode} />
              <WatchlistButton code={resolvedCode} name="" />
            </div>
          ) : null}
        </div>
      )}
    />
  );
}
