import Link from 'next/link';
import { Badge } from '@/components/ui';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import {
  fundFlowLinkChipCls,
  fundFlowNoteCardCls,
  fundFlowPanelCls,
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
  return (
    <section className="page-hero mb-4 p-5 sm:p-6">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info">Flow Workspace</Badge>
            <Badge variant="neutral">{activeTabLabel}</Badge>
            <Badge variant={hasError ? 'warning' : loading ? 'warning' : 'success'}>{tabStatusLabel}</Badge>
          </div>
          <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
            资金流向工作台
          </h1>
          <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
            这一页现在会先帮你判断钱正在流向哪里，再把个股、板块、北向和融资融券这几类观察路径收束到同一套工作台语言里，减少“看了一半还得重新找入口”的切换成本。
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <button type="button" onClick={onOpenStockFlow} className={fundFlowPrimaryButtonCls}>
              查看个股资金流
            </button>
            <button type="button" onClick={onOpenNorthFlow} className={fundFlowSecondaryButtonCls}>
              查看北向资金
            </button>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-4">
            <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前视角</div>
              <div className="mt-3 text-xl font-semibold text-text-primary">{activeTabLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">当前正在查看的资金流维度</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前代码</div>
              <div className="mt-3 text-xl font-semibold text-text-primary">{activeCodeLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">个股与北向明细会优先使用它</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">状态</div>
              <div className="mt-3 text-xl font-semibold text-text-primary">{tabStatusLabel}</div>
              <div className="mt-1 text-xs text-text-secondary">当前 tab 的数据加载状态</div>
            </div>
            <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">联动入口</div>
              <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">市场、研究、风险、自选</div>
              <div className="mt-1 text-xs text-text-secondary">看完资金流后可直接跳到下一步</div>
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className={fundFlowPanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">阅读建议</div>
            <div className="mt-4 space-y-3">
              {heroNotes.map((note) => (
                <div key={note} className={fundFlowNoteCardCls}>
                  {note}
                </div>
              ))}
            </div>
          </div>
          <div className={fundFlowPanelCls}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">快捷跳转</div>
            <div className="mt-4 flex flex-wrap gap-2">
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
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <StockLink code={resolvedCode} name={resolvedCode} />
                <WatchlistButton code={resolvedCode} name="" />
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
