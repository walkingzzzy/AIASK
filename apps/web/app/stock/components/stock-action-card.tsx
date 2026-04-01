import Link from 'next/link';
import { Badge, SectionCard, Skeleton } from '@/components/ui';
import { EmptyState } from '@/components/status-state';
import {
  stockLinkChipCls,
  stockPrimaryLinkCls,
  stockReasonChipCls,
} from '@/app/stock/components/stock-panel-styles';
import type { StockDetailActionCard } from '@aiask/shared-types';

type StockActionCardProps = {
  actionCard: StockDetailActionCard | null;
  hasQuote: boolean;
};

export default function StockActionCard({ actionCard, hasQuote }: StockActionCardProps) {
  return (
    <SectionCard className="mt-0 min-h-[200px] p-4 sm:p-5">
      {actionCard ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_280px]">
          <div className="panel-soft rounded-[24px] p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="mb-1 mt-0">{actionCard.title}</h3>
                <p className="m-0 text-sm leading-6 text-text-secondary">{actionCard.summary}</p>
              </div>
              <Badge variant={actionCard.tone}>行动建议</Badge>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {actionCard.reasons.map((reason) => (
                <span key={reason} className={stockReasonChipCls}>
                  {reason}
                </span>
              ))}
            </div>
          </div>
          <div className="panel-soft rounded-[24px] p-4 sm:p-5">
            <div className="metric-label">推荐动作</div>
            <div className="mt-3 space-y-2">
              {actionCard.links.map((link, index) => (
                <Link key={link.href} href={link.href} className={index === 0 ? stockPrimaryLinkCls : stockLinkChipCls}>
                  {link.label}
                </Link>
              ))}
            </div>
            <p className="m-0 mt-4 text-xs leading-6 text-text-secondary">
              先沿主建议继续跳转，再按需要补充到研究页、交易页或回测页，避免在个股页停留过久。
            </p>
          </div>
        </div>
      ) : hasQuote ? (
        <EmptyState
          text="行动卡已预留完成。"
          hint="当报价、情绪和估值信号汇总完成后，这里会给出下一步操作建议，不再把图表区整体向下挤。"
          className="py-10"
        />
      ) : (
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="w-56" height={22} />
          <Skeleton className="w-full" height={18} />
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <Skeleton key={index} className="w-[92px]" height={28} />
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}
