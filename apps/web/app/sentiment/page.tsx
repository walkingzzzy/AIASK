'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, Badge, Skeleton, KpiGrid, KpiCard } from '@/components/ui';
import { GaugeChart, BarChart, COLORS } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useStockCode } from '@/hooks/use-stock-code';
import { ErrorState, LoadingState, EmptyState } from '@/components/status-state';
import { fmtNum } from '@/lib/data-utils';
import { ensureRecord } from '@/lib/query-parse';
import { StockLink } from '@/components/stock-link';
import { WatchlistButton } from '@/components/watchlist-button';
import { unwrapToolPayload } from '@/lib/tool-result';

const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';

function objToItems(obj: unknown): { label: string; value: number }[] {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
  return Object.entries(obj as Record<string, unknown>)
    .filter(([, value]) => typeof value === 'number')
    .map(([key, value]) => ({ label: key.replace(/_/g, ' '), value: value as number }));
}

export default function SentimentPage() {
  const { code, setCode, codeError, validate, resolvedCode } = useStockCode();
  const autoStockSentimentPath = resolvedCode ? `/sentiment/stock?code=${encodeURIComponent(resolvedCode)}` : null;
  const [stockSentimentPath, setStockSentimentPath] = useState<string | null>(null);
  const effectiveStockSentimentPath = stockSentimentPath ?? autoStockSentimentPath;
  const stockSentimentQ = useApiQuery<unknown>(effectiveStockSentimentPath, {
    parse: (raw) => ensureRecord(raw, '个股情绪'),
  });
  const fearGreedQ = useApiQuery<unknown>('/sentiment/fear-greed', {
    parse: (raw) => ensureRecord(raw, '恐贪指数'),
  });

  const isPending = stockSentimentQ.isFetching || fearGreedQ.isFetching;

  function fetchStockSentiment() {
    if (!validate()) return;
    const path = `/sentiment/stock?code=${encodeURIComponent(code.trim())}`;
    if (path === effectiveStockSentimentPath) stockSentimentQ.refetch();
    else setStockSentimentPath(path);
  }

  const stockPayload = unwrapToolPayload(stockSentimentQ.data);
  const stockScore = (stockPayload.score as number) ?? null;
  const stockSentiment = String(stockPayload.sentiment ?? '');
  const stockComponents = objToItems(stockPayload.components);
  const stockCode = String(stockPayload.code ?? resolvedCode ?? '');

  const fearGreedPayload = unwrapToolPayload(fearGreedQ.data);
  const fearGreedIndex = (fearGreedPayload.index as number) ?? (fearGreedPayload.value as number) ?? null;
  const fearGreedLevel = String(fearGreedPayload.level ?? '');
  const fearGreedComponents = objToItems(fearGreedPayload.components);

  const sentimentSummary = useMemo(() => {
    if (stockScore == null) return null;
    if (stockScore >= 70) {
      return { title: '情绪偏热', description: '短期乐观情绪较强，适合结合估值或资金流确认是否已经过热。' };
    }
    if (stockScore <= 30) {
      return { title: '情绪偏冷', description: '市场预期较谨慎，适合叠加基本面或风险页判断是否属于错杀。' };
    }
    return { title: '情绪中性', description: '当前情绪没有明显单边倾向，更适合与技术形态和资金流一起交叉验证。' };
  }, [stockScore]);

  const resultActionLinks = useMemo(() => {
    if (!stockCode) return [];
    const encoded = encodeURIComponent(stockCode);
    return [
      { label: '个股详情', href: `/stock?code=${encoded}` },
      { label: '技术分析', href: `/technical?code=${encoded}` },
      { label: '资金流', href: `/fund-flow?code=${encoded}` },
      { label: '估值', href: `/valuation?code=${encoded}` },
      { label: '风险页', href: `/risk?code=${encoded}` },
    ];
  }, [stockCode]);

  const showStockSkeleton = stockSentimentQ.isPending && !stockSentimentQ.data;
  const showFearGreedSkeleton = fearGreedQ.isPending && fearGreedIndex == null;
  const focusCode = stockCode || code.trim() || resolvedCode || '未选择';

  function loadSampleSentiment(sampleCode = '600519') {
    setCode(sampleCode);
    const path = `/sentiment/stock?code=${encodeURIComponent(sampleCode)}`;
    if (path === effectiveStockSentimentPath) stockSentimentQ.refetch();
    else setStockSentimentPath(path);
  }

  return (
    <PageContainer>
      <section className="page-hero mb-4 p-5 sm:p-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_clamp(280px,25vw,380px)]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">Sentiment Workspace</Badge>
              <Badge variant={stockCode ? 'success' : 'warning'}>
                {stockCode ? `当前标的 ${stockCode}` : '等待选择标的'}
              </Badge>
              <Badge variant="neutral">恐贪指数</Badge>
            </div>
            <h1 className="mb-0 mt-4 text-[2rem] font-semibold tracking-[-0.03em] text-text-primary sm:text-[2.4rem]">
              情绪分析工作台
            </h1>
            <p className="mb-0 mt-3 max-w-3xl text-sm leading-7 text-text-secondary sm:text-[15px]">
              这一页同时回答两件事：单只股票当前讨论氛围是偏热还是偏冷，以及全市场处在恐惧还是贪婪阶段。先看整体温度，再决定是否继续做个股下钻。
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={fetchStockSentiment}
                disabled={isPending}
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                {isPending ? '分析中...' : '查询个股情绪'}
              </button>
              <button type="button" onClick={() => loadSampleSentiment('600519')} className={HERO_SECONDARY_BUTTON_CLS}>
                示例：600519
              </button>
              <button type="button" onClick={() => fearGreedQ.refetch()} className={HERO_SECONDARY_BUTTON_CLS}>
                刷新恐贪指数
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <div className="rounded-[24px] border border-white/45 bg-white/38 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前标的</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">{focusCode}</div>
                <div className="mt-1 text-xs text-text-secondary">用来判断单只股票当前的预期温度</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/30 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.48)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">个股分数</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {stockScore != null ? fmtNum(stockScore, 1) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">{stockSentiment || '等待返回情绪标签'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/26 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">市场温度</div>
                <div className="mt-3 text-2xl font-semibold text-text-primary">
                  {fearGreedIndex != null ? fmtNum(fearGreedIndex, 0) : '-'}
                </div>
                <div className="mt-1 text-xs text-text-secondary">{fearGreedLevel || '等待刷新'}</div>
              </div>
              <div className="rounded-[24px] border border-white/45 bg-white/24 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)]">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">联动建议</div>
                <div className="mt-3 text-sm font-semibold leading-6 text-text-primary">
                  {stockScore == null
                    ? '先锁定个股'
                    : stockScore >= 70
                      ? '优先核对估值与风险'
                      : stockScore <= 30
                        ? '优先核对基本面'
                        : '优先核对技术与资金流'}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-3">
            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">当前焦点</div>
              <div className="mt-3 text-base font-semibold text-text-primary">{focusCode}</div>
              {stockCode && stockSentimentQ.data ? (
                <div className="mt-3 flex items-center gap-2">
                  <StockLink code={stockCode} name={stockCode} />
                  <WatchlistButton code={stockCode} name="" />
                  {stockSentiment ? (
                    <Badge
                      variant={
                        stockSentiment === 'positive' ? 'success' : stockSentiment === 'negative' ? 'danger' : 'neutral'
                      }
                    >
                      {stockSentiment}
                    </Badge>
                  ) : null}
                </div>
              ) : null}
              <div className="mt-4 space-y-3">
                <div className={NOTE_CARD_CLS}>
                  个股分数：
                  <span className="font-medium text-text-primary">
                    {stockScore != null ? fmtNum(stockScore, 1) : '-'}
                  </span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  恐贪指数：
                  <span className="font-medium text-text-primary">
                    {fearGreedIndex != null ? fmtNum(fearGreedIndex, 0) : '-'}
                  </span>
                </div>
                <div className={NOTE_CARD_CLS}>
                  当前结论：
                  <span className="font-medium text-text-primary"> {sentimentSummary?.title ?? '先完成查询'}</span>
                </div>
              </div>
            </div>

            <div className={SIDE_PANEL_CLS}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">关联跳转</div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link href="/watchlist" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  自选股
                </Link>
                <Link href="/technical" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  技术分析
                </Link>
                <Link href="/fund-flow" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  资金流向
                </Link>
                <Link href="/valuation" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                  估值分析
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {stockSentimentQ.error || fearGreedQ.error ? (
        <ErrorState text={stockSentimentQ.error || fearGreedQ.error!} />
      ) : null}

      <KpiGrid cols={4} className="mb-4">
        <KpiCard title="个股情绪分数" value={stockScore != null ? fmtNum(stockScore, 1) : '-'} />
        <KpiCard title="个股情绪标签" value={stockSentiment || '-'} />
        <KpiCard title="恐贪指数" value={fearGreedIndex != null ? fmtNum(fearGreedIndex, 0) : '-'} />
        <KpiCard title="市场状态" value={fearGreedLevel || '-'} />
      </KpiGrid>

      <div className="panel-soft rounded-[28px] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="eyebrow">Sentiment Setup</div>
            <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">个股情绪查询</h2>
            <p className="mb-0 mt-2 text-sm leading-7 text-text-secondary">
              适合快速判断一只股票当前舆情和市场预期偏乐观还是偏谨慎，再决定是否继续看资金流或估值。
            </p>
          </div>
        </div>

        <SectionCard className="mt-4 p-4 sm:p-5">
          <div className="grid gap-4 xl:grid-cols-[260px_auto] xl:items-end">
            <StockCodeInput
              id="sentiment-stock-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={isPending}
                onClick={fetchStockSentiment}
                className={HERO_PRIMARY_BUTTON_CLS}
              >
                {isPending ? '分析中...' : '查询'}
              </button>
              <button type="button" onClick={() => loadSampleSentiment('600519')} className={CHIP_BUTTON_CLS}>
                600519
              </button>
              <button type="button" onClick={() => loadSampleSentiment('300750')} className={CHIP_BUTTON_CLS}>
                300750
              </button>
            </div>
          </div>
        </SectionCard>
      </div>

      <section className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Stock Sentiment</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">个股情绪</h2>
            </div>
            {sentimentSummary ? (
              <div className="metric-tile rounded-[22px] px-4 py-3 text-sm text-text-secondary">
                <span className="font-medium text-text-primary">{sentimentSummary.title}</span>
              </div>
            ) : null}
          </div>

          <div className="mt-3 min-h-[470px]">
            {showStockSkeleton ? (
              <div className="space-y-4">
                <Skeleton height={76} />
                <Skeleton height={250} />
                <Skeleton height={180} />
              </div>
            ) : stockScore != null ? (
              <>
                {sentimentSummary ? (
                  <div className="metric-tile rounded-[22px] p-4">
                    <div className="text-sm font-medium text-text-primary">{sentimentSummary.title}</div>
                    <p className="mb-0 mt-1 text-sm text-text-secondary">{sentimentSummary.description}</p>
                    {resultActionLinks.length > 0 ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {resultActionLinks.map((link) => (
                          <Link
                            key={link.href}
                            href={link.href}
                            className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}
                          >
                            {link.label}
                          </Link>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
                <div className="my-4">
                  <GaugeChart
                    value={stockScore}
                    min={0}
                    max={100}
                    title={`情绪分数 ${fmtNum(stockScore, 1)}`}
                    height={250}
                  />
                </div>
                {stockComponents.length > 0 ? (
                  <BarChart
                    items={stockComponents}
                    horizontal
                    height={Math.max(160, stockComponents.length * 50)}
                    yAxisName="分数"
                  />
                ) : null}
              </>
            ) : !stockSentimentQ.data ? (
              <EmptyState
                text="输入股票代码后查看个股情绪分数"
                hint="推荐先从关注名单中的个股开始，确认市场讨论与预期是偏热还是偏冷。"
                action={
                  <>
                    <button type="button" onClick={() => loadSampleSentiment('600519')} className={CHIP_BUTTON_CLS}>
                      示例：600519
                    </button>
                    <Link href="/watchlist" className={`${CHIP_BUTTON_CLS} no-underline text-inherit`}>
                      查看自选股
                    </Link>
                  </>
                }
              />
            ) : (
              <EmptyState
                text="当前没有可展示的个股情绪结果"
                hint="可以换一只股票后重试，或稍后刷新等待情绪数据更新。"
              />
            )}
          </div>
        </div>

        <div className="panel-soft rounded-[28px] p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="eyebrow">Market Mood</div>
              <h2 className="mb-0 mt-2 text-xl font-semibold text-text-primary">恐贪指数</h2>
            </div>
            <button type="button" className={HERO_SECONDARY_BUTTON_CLS} onClick={() => fearGreedQ.refetch()}>
              刷新
            </button>
          </div>

          <div className="min-h-[470px]">
            {showFearGreedSkeleton ? (
              <div className="space-y-4">
                <Skeleton height={280} />
                <Skeleton height={180} />
              </div>
            ) : fearGreedIndex != null ? (
              <>
                <div className="my-4">
                  <GaugeChart
                    value={fearGreedIndex}
                    min={0}
                    max={100}
                    title={`${fearGreedLevel} (${fearGreedIndex})`}
                    height={280}
                    zones={[
                      { start: 0, end: 25, color: COLORS.success },
                      { start: 25, end: 50, color: COLORS.warning },
                      { start: 50, end: 75, color: '#f97316' },
                      { start: 75, end: 100, color: COLORS.danger },
                    ]}
                  />
                </div>
                {fearGreedComponents.length > 0 ? (
                  <BarChart
                    items={fearGreedComponents}
                    horizontal
                    height={Math.max(160, fearGreedComponents.length * 50)}
                    yAxisName="分数"
                  />
                ) : null}
              </>
            ) : fearGreedQ.isPending ? (
              <LoadingState text="加载中..." />
            ) : (
              <EmptyState text="当前没有可用的恐贪指数" hint="非交易时段或上游情绪源暂缺时可能为空，建议稍后再刷新。" />
            )}
          </div>
        </div>
      </section>
    </PageContainer>
  );
}
