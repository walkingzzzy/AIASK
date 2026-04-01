import Link from 'next/link';
import { Badge, KpiCard, KpiGrid, SectionCard, Skeleton, SkeletonCard } from '@/components/ui';
import { LoadingState } from '@/components/status-state';
import { fmtAmount, fmtNum, fmtPct } from '@/lib/data-utils';
import { stockLinkChipCls, stockPrimaryLinkCls } from '@/app/stock/components/stock-panel-styles';
import type { NormalizedQuote } from '@aiask/shared-types';

type StockSnapshotProps = {
  quote?: NormalizedQuote;
  loading: boolean;
  priceChangePct: number;
  chgColor: string;
  amplitude: string;
  quickLinks: Array<{ label: string; href: string }>;
  contextCode: string;
};

export default function StockSnapshot({
  quote,
  loading,
  priceChangePct,
  chgColor,
  amplitude,
  quickLinks,
  contextCode,
}: StockSnapshotProps) {
  return (
    <SectionCard className="mt-0 min-h-[320px] p-4 sm:p-5">
      {quote ? (
        <>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="eyebrow">Snapshot</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">报价与关键指标</h2>
              <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
                这一屏优先回答“现在价格处在什么位置、波动强弱如何、还有哪些最值得继续看”的问题。
              </p>
            </div>
            <Badge variant={priceChangePct >= 0 ? 'danger' : 'success'}>{priceChangePct >= 0 ? '偏强' : '承压'}</Badge>
          </div>
          <KpiGrid cols={4}>
            <KpiCard title="现价" value={fmtNum(Number(quote.price))} className={chgColor} />
            <KpiCard title="涨跌幅" value={fmtPct(Number(quote.changePercent ?? quote.change_pct ?? 0))} className={chgColor} />
            <KpiCard title="涨跌额" value={fmtNum(Number(quote.change), 2)} className={chgColor} />
            <KpiCard title="振幅" value={amplitude} />
            <KpiCard title="成交量" value={fmtAmount(Number(quote.volume))} suffix="股" />
            <KpiCard title="成交额" value={fmtAmount(Number(quote.amount))} suffix="元" />
            <KpiCard title="最高/最低" value={`${fmtNum(Number(quote.high))} / ${fmtNum(Number(quote.low))}`} />
            <KpiCard title="开盘/昨收" value={`${fmtNum(Number(quote.open))} / ${fmtNum(Number(quote.prevClose))}`} />
          </KpiGrid>

          <div className="mt-3 flex flex-wrap gap-2">
            {quickLinks.map((link) => (
              <Link key={link.href} href={link.href} className={stockLinkChipCls}>
                {link.label}
              </Link>
            ))}
            {contextCode ? (
              <>
                <Link href={`/paper-trading?code=${contextCode}`} className={stockPrimaryLinkCls}>
                  去模拟下单
                </Link>
                <Link href={`/backtest?code=${contextCode}`} className={stockLinkChipCls}>
                  回测分析
                </Link>
                <Link href={`/assistant?code=${contextCode}`} className={stockLinkChipCls}>
                  AI诊断
                </Link>
              </>
            ) : null}
          </div>
        </>
      ) : (
        <div className="space-y-4" aria-hidden="true">
          <KpiGrid cols={4}>
            {Array.from({ length: 8 }).map((_, index) => (
              <SkeletonCard key={index} />
            ))}
          </KpiGrid>
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="w-[96px]" height={28} />
            ))}
          </div>
          <div className="pt-2">
            {loading ? (
              <LoadingState text="正在加载个股报价与关键指标..." />
            ) : (
              <p className="m-0 text-sm text-text-secondary">
                输入股票代码后，这里会先展示报价头部、关键指标和快捷动作，避免结果返回时把主图整体推下去。
              </p>
            )}
          </div>
        </div>
      )}
    </SectionCard>
  );
}
