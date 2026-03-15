'use client';

import type { ReactNode } from 'react';
import { SectionCard, KpiGrid, SkeletonCard } from '@/components/ui';
import { ErrorState, EmptyState } from '@/components/status-state';
import Link from 'next/link';
import type { DashboardMarketAnomaly } from '@aiask/shared-types';

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

export interface DashboardCard {
  key: string;
  title: string;
  pending: boolean;
  error: string | null;
  content: ReactNode;
  empty: boolean;
  href: string;
  footer: ReactNode;
  emptyText?: string;
  emptyHint?: string;
  emptyAction?: ReactNode;
}

export interface DashboardCardsProps {
  mounted: boolean;
  dashboardVisibility: Record<string, boolean>;
  dashboardCards: DashboardCard[];
  /* Market anomaly feed */
  marketAnomalies: DashboardMarketAnomaly[];
  anomalyDegraded: boolean;
}

/* ------------------------------------------------------------------ */
/* Dashboard Cards Grid                                                */
/* ------------------------------------------------------------------ */

function CardGrid({ mounted, dashboardVisibility, dashboardCards }: Pick<DashboardCardsProps, 'mounted' | 'dashboardVisibility' | 'dashboardCards'>) {
  if (!mounted) return null;
  const visible = dashboardCards.filter((c) => dashboardVisibility[c.key]);
  if (visible.length === 0) return null;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
      {visible.map((card) => (
        <SectionCard key={card.key} className="p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="mt-0 mb-0">{card.title}</h3>
            <Link href={card.href} className="text-xs text-primary no-underline">查看详情</Link>
          </div>
          {card.error ? <ErrorState text={card.error} />
            : card.pending ? <KpiGrid cols={3}><SkeletonCard /><SkeletonCard /><SkeletonCard /></KpiGrid>
              : card.empty ? <EmptyState text={card.emptyText ?? '暂无可展示数据'} hint={card.emptyHint} action={card.emptyAction} />
                : card.content}
          {card.footer}
        </SectionCard>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Market Anomaly Feed                                                 */
/* ------------------------------------------------------------------ */

function AnomalyFeed({ marketAnomalies, anomalyDegraded }: Pick<DashboardCardsProps, 'marketAnomalies' | 'anomalyDegraded'>) {
  return (
    <SectionCard className="p-4 mb-4">
      <h3 className="mt-0">市场异动榜</h3>
      {anomalyDegraded && marketAnomalies.length > 0 && (
        <div className="text-xs text-warning mb-2">部分数据源不可用，异动信息可能不完整</div>
      )}
      {marketAnomalies.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {marketAnomalies.map((item) => (
            <Link key={`${item.title}-${item.href}`} href={item.href} className="glass rounded-lg px-3 py-2 no-underline text-inherit flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{item.title}</div>
                <div className={`text-xs ${item.tone === 'danger' ? 'text-danger' : item.tone === 'success' ? 'text-success' : item.tone === 'warning' ? 'text-warning' : 'text-primary'}`}>{item.value}</div>
              </div>
              <span className="text-xs text-text-secondary">查看</span>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState text="暂无异动数据" />
      )}
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/* Composed export                                                     */
/* ------------------------------------------------------------------ */

export function DashboardCards(props: DashboardCardsProps) {
  return (
    <>
      <CardGrid mounted={props.mounted} dashboardVisibility={props.dashboardVisibility} dashboardCards={props.dashboardCards} />
      <AnomalyFeed marketAnomalies={props.marketAnomalies} anomalyDegraded={props.anomalyDegraded} />
    </>
  );
}
