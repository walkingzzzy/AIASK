import Link from 'next/link';
import { Badge } from '@/components/ui';
import { AskAiButton } from '@/components/ask-ai-button';
import { useMobile } from '@/hooks/use-mobile';
import { RESPONSIVE_BREAKPOINTS } from '@/lib/responsive-layout';
import { fmtNum, fmtPct } from '@/lib/data-utils';
import { formatStableDateTime } from '@/app/market/lib/market-view';
import {
  marketLinkChipCls,
  marketNoteCardCls,
  marketPanelCls,
  marketSidebarActionCardCls,
} from '@/app/market/components/market-panel-styles';
import type { NormalizedQuote } from '@aiask/shared-types';

type MarketHeroSectionProps = {
  activeTaskLabel: string;
  activeDisplayName: string;
  activeDisplayCode: string;
  activePeriodLabel: string;
  workspaceSummary: string;
  activeQuote: NormalizedQuote | null;
  activeChangeTone: string;
  freshnessLabel: string;
  freshness: string;
  from: string | null;
  task: string | null;
  heroNotes: string[];
  quickJumpLinks: Array<{ label: string; href: string }>;
};

export default function MarketHeroSection({
  activeTaskLabel,
  activeDisplayName,
  activeDisplayCode,
  activePeriodLabel,
  workspaceSummary,
  activeQuote,
  activeChangeTone,
  freshnessLabel,
  freshness,
  from,
  task,
  heroNotes,
  quickJumpLinks,
}: MarketHeroSectionProps) {
  const compactLayout = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const compactHero = useMobile(RESPONSIVE_BREAKPOINTS.dockOverlay);
  const visibleQuickLinks = compactLayout ? quickJumpLinks.slice(0, 2) : quickJumpLinks;

  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
      <section className="page-hero p-6 sm:p-7 xl:p-8">
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-3xl space-y-4">
              <div className="eyebrow">行情工作台 · {activeTaskLabel}</div>
              <div className="space-y-3">
                <h1>{activeDisplayName}</h1>
                <p className="page-lead mb-0">
                  先锁定观察标的，再围绕 {activePeriodLabel} 主图、实时摘要与盘口深度推进判断。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <AskAiButton
                  stockCode={activeDisplayCode}
                  prompt={activeDisplayCode ? `请解读 ${activeDisplayCode} 的当前走势与盘口` : '请分析当前行情看板'}
                  label="解读当前行情"
                />
                {!compactLayout ? (
                  <AskAiButton
                    stockCode={activeDisplayCode}
                    prompt={activeDisplayCode ? `请给 ${activeDisplayCode} 一个下一步交易建议` : '请给出行情操作建议'}
                    label="交易建议"
                  />
                ) : null}
                <Link
                  href={
                    activeDisplayCode
                      ? `/research?code=${encodeURIComponent(activeDisplayCode)}&from=market`
                      : '/research?from=market'
                  }
                  className={marketLinkChipCls}
                >
                  去研究页补信息
                </Link>
              </div>
            </div>

            <div className={`${marketPanelCls} w-full max-w-[360px] space-y-4 self-stretch`}>
              <div>
                <div className="eyebrow">当前聚焦</div>
                <h2 className="mt-2">{activeDisplayCode || '等待选择标的'}</h2>
                <p className="mt-2 text-sm leading-6 text-text-secondary">{workspaceSummary}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <div className={`${marketNoteCardCls} px-4 py-3`}>
                  <div className="metric-label">当前任务</div>
                  <div className="mt-2 text-base font-semibold text-text-primary">{activeTaskLabel}</div>
                </div>
                <div className={`${marketNoteCardCls} px-4 py-3`}>
                  <div className="metric-label">观察周期</div>
                  <div className="mt-2 text-base font-semibold text-text-primary">{activePeriodLabel}</div>
                </div>
              </div>
            </div>
          </div>

          <div className={`grid gap-3 ${compactHero ? 'grid-cols-2' : 'grid-cols-2 xl:grid-cols-4'}`}>
            <div className="metric-tile px-4 py-4">
              <div className="metric-label">当前标的</div>
              <div className="mt-2 text-lg font-semibold text-text-primary">{activeDisplayCode || '未选择'}</div>
            </div>
            <div className="metric-tile px-4 py-4">
              <div className="metric-label">实时价格</div>
              <div className={`mt-2 text-lg font-semibold ${activeChangeTone}`}>
                {fmtNum(activeQuote?.price as number | null, 2)}
              </div>
            </div>
            <div className="metric-tile px-4 py-4">
              <div className="metric-label">涨跌幅</div>
              <div className={`mt-2 text-lg font-semibold ${activeChangeTone}`}>
                {fmtPct(activeQuote?.changePercent as number | null)}
              </div>
            </div>
            {!compactHero ? (
              <div className="metric-tile px-4 py-4">
                <div className="metric-label">数据刷新</div>
                <div className="mt-2 text-sm font-medium text-text-primary">{freshnessLabel}</div>
                <div className="mt-1 text-xs text-text-secondary">抓取 {formatStableDateTime(freshness)}</div>
              </div>
            ) : null}
          </div>

          {compactHero ? (
            <details className={`${marketNoteCardCls} px-4 py-3`}>
              <summary className="cursor-pointer list-none text-xs font-medium text-text-primary">展开来源与刷新信息</summary>
              <div className="mt-3 space-y-2 text-xs text-text-secondary">
                <div>
                  数据刷新：<span className="font-medium text-text-primary">{freshnessLabel}</span>
                </div>
                <div>抓取 {formatStableDateTime(freshness)}</div>
                <div>
                  来源：{from ?? '-'} ｜ 任务：{task ?? '-'}
                </div>
              </div>
            </details>
          ) : from || task ? (
            <div className={`${marketNoteCardCls} px-4 py-3`}>
              来源：{from ?? '-'} ｜ 任务：{task ?? '-'}
            </div>
          ) : null}
        </div>
      </section>

      {!compactLayout ? (
      <div className="grid gap-4">
        <details className="page-hero p-5 sm:p-6" open={!compactLayout}>
          <summary className="flex cursor-pointer list-none items-start justify-between gap-3">
            <div>
              <div className="eyebrow">盘中提示</div>
              <h2 className="mt-2">观察节奏</h2>
            </div>
            <Badge variant="info">{activePeriodLabel}</Badge>
          </summary>
          <div className="mt-4 grid gap-3">
            {heroNotes.map((note) => (
              <div key={note} className={`${marketNoteCardCls} px-4 py-3 leading-6`}>
                {note}
              </div>
            ))}
          </div>
        </details>

        <section className={`${marketPanelCls} rounded-[32px]`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="eyebrow">快捷跳转</div>
              <h2 className="mt-2">继续下一步</h2>
            </div>
            <Badge variant="neutral">联动页面</Badge>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
            {visibleQuickLinks.map((link) => (
              <Link key={link.href} href={link.href} className={marketSidebarActionCardCls}>
                <div className="text-sm font-medium text-text-primary">{link.label}</div>
                <div className="mt-1 text-xs text-text-secondary">把当前观察上下文带到下一页继续分析。</div>
              </Link>
            ))}
          </div>
          {compactLayout && quickJumpLinks.length > visibleQuickLinks.length ? (
            <div className="mt-3 text-xs text-text-secondary">更多跳转入口可在后续工作区查看。</div>
          ) : null}
        </section>
      </div>
      ) : null}
    </section>
  );
}
