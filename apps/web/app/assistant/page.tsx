'use client';

import { useState } from 'react';
import { PageContainer, StockCodeInput, DataTable } from '@/components/ui';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { EmptyState, ErrorState, LoadingState } from '@/components/status-state';
import { extractArray } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import DecisionCard from '@/components/decision-card';

export default function AssistantPage() {
  const { code, setCode, codeError, validate, trimmedCode } = useStockCode();
  const { trigger, data: rawData, isPending, error, reset } = useApiMutation<unknown>();
  const [actionLabel, setActionLabel] = useState('');
  const [sellBuyPrice, setSellBuyPrice] = useState('');
  const [sellHoldingDays, setSellHoldingDays] = useState('');
  const [industryKeyword, setIndustryKeyword] = useState('');
  const [dailyReportDate, setDailyReportDate] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  // Extract card data from response
  const result = rawData != null
    ? (rawData as Record<string, unknown>).card ?? rawData
    : null;

  function callAssistant(endpoint: string, label: string) {
    setFormError(null);
    reset();
    setActionLabel(label);
    const body: Record<string, unknown> = {};

    const requiresStockCode = endpoint === '/assistant/should-buy'
      || endpoint === '/assistant/should-sell'
      || endpoint === '/assistant/diagnosis';

    if (requiresStockCode) {
      if (!validate()) return;
      body.code = trimmedCode;
    }

    if (endpoint === '/assistant/should-sell') {
      const buyPrice = Number(sellBuyPrice);
      if (!sellBuyPrice.trim() || !Number.isFinite(buyPrice) || buyPrice <= 0) {
        setFormError('卖出风险提示需要填写有效的买入价');
        return;
      }
      body.buyPrice = buyPrice;

      if (sellHoldingDays.trim()) {
        const holdingDays = Number(sellHoldingDays);
        if (!Number.isFinite(holdingDays) || holdingDays < 0) {
          setFormError('持有天数需要填写为非负数');
          return;
        }
        body.holdingDays = holdingDays;
      }
    }

    if (endpoint === '/assistant/industry-chain') {
      if (industryKeyword.trim()) {
        body.keyword = industryKeyword.trim();
      }
    }

    if (endpoint === '/assistant/daily-report' && dailyReportDate.trim()) {
      body.date = dailyReportDate.trim();
    }

    trigger(endpoint, { method: 'POST' }, body);
  }

  return (
    <PageContainer className="pb-20 md:pb-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-primary flex items-center gap-2">
          🧠 AI 深度诊断报告生成器 (Diagnostic AI)
        </h1>
        <p className="text-muted-foreground mt-2">与随问随答的 Chat 不同，这里专注于针对特定标的的深度、主动性结构化诊断报告生成。</p>
      </div>

      <div className="bg-surface border border-glass-border rounded-xl p-5 mb-6 shadow-sm">
        <h2 className="text-sm font-semibold mb-3 text-text-muted uppercase tracking-wider">选择分析标的与报告类型</h2>
        <div className="flex flex-col md:flex-row gap-4 items-center">
          <div className="w-full md:w-64">
            <StockCodeInput
              id="assistant-stock-code"
              label="股票代码"
              value={code}
              onChange={setCode}
              error={codeError}
              placeholder="输入股票代码 (如 600519)"
            />
          </div>
          <div className="flex gap-2 flex-wrap">
            <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/should-buy', '买入逻辑分析')}
              className="px-4 py-2 rounded-md bg-danger/10 text-danger hover:bg-danger/20 transition-colors text-sm font-medium border border-danger/20 disabled:opacity-50">
              买入逻辑分析
            </button>
            <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/should-sell', '卖出风险提示')}
              className="px-4 py-2 rounded-md bg-success/10 text-success hover:bg-success/20 transition-colors text-sm font-medium border border-success/20 disabled:opacity-50">
              卖出风险提示
            </button>
            <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/diagnosis', '全方位综合体检')}
              className="px-4 py-2 rounded-md bg-primary/10 text-primary hover:bg-primary/20 transition-colors text-sm font-medium border border-primary/20 disabled:opacity-50">
              全方位体检
            </button>
            <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/industry-chain', '产业链价值穿透')}
              className="px-4 py-2 rounded-md bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 transition-colors text-sm font-medium border border-purple-500/20 disabled:opacity-50">
              产业链穿透
            </button>
            <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/daily-report', '盘后复盘简报')}
              className="px-4 py-2 rounded-md bg-orange-500/10 text-orange-600 dark:text-orange-400 hover:bg-orange-500/20 transition-colors text-sm font-medium border border-orange-500/20 disabled:opacity-50">
              盘后复盘简报
            </button>
          </div>
        </div>
        <div className="mt-4 flex flex-col gap-2 md:max-w-[420px]">
          <div className="text-xs font-medium text-text-muted uppercase tracking-wider">卖出分析参数</div>
          <div className="flex gap-2 flex-wrap">
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>买入价</span>
              <input
                id="assistant-buy-price"
                value={sellBuyPrice}
                onChange={(e) => { setSellBuyPrice(e.target.value); setFormError(null); }}
                placeholder="卖出分析必填"
                className="w-full md:w-[200px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
                inputMode="decimal"
              />
            </label>
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>持有天数</span>
              <input
                id="assistant-holding-days"
                value={sellHoldingDays}
                onChange={(e) => { setSellHoldingDays(e.target.value); setFormError(null); }}
                placeholder="可选"
                className="w-full md:w-[180px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
                inputMode="numeric"
              />
            </label>
          </div>
          <p className="text-xs text-text-muted">“卖出风险提示”会连同买入价和持有天数一起提交，避免出现成功返回但内容为空的假通过。</p>
        </div>
        <div className="mt-4 grid gap-2 md:max-w-[520px]">
          <div className="text-xs font-medium text-text-muted uppercase tracking-wider">非个股分析参数</div>
          <div className="flex gap-2 flex-wrap">
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>产业链关键词</span>
              <input
                id="assistant-industry-keyword"
                value={industryKeyword}
                onChange={(e) => { setIndustryKeyword(e.target.value); setFormError(null); }}
                placeholder="产业链穿透可选"
                className="w-full md:w-[240px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
              />
            </label>
            <label className="grid gap-1 text-xs text-text-secondary">
              <span>复盘日期</span>
              <input
                id="assistant-daily-report-date"
                type="date"
                value={dailyReportDate}
                onChange={(e) => { setDailyReportDate(e.target.value); setFormError(null); }}
                className="w-full md:w-[200px] border border-glass-border bg-surface px-3 py-2 rounded-md text-sm"
              />
            </label>
          </div>
          <p className="text-xs text-text-muted">“产业链穿透”和“盘后复盘简报”不再强制要求股票代码，可按关键词或日期独立生成。</p>
        </div>
      </div>

      {isPending ? (
        <div className="p-12 border-2 border-dashed border-muted rounded-xl bg-surface-alt/30 flex justify-center items-center">
          <LoadingState text={`报告生成引擎运转中：正在提取 ${actionLabel} 的多维度底层数据...`} />
        </div>
      ) : null}

      {formError || error ? <ErrorState text={formError || error!} hint="请检查标的代码和分析参数后重试" /> : null}

      {!isPending && !result && !error && !formError ? (
        <div className="p-16 border-2 border-dashed border-muted rounded-xl bg-surface-alt/10 flex flex-col items-center text-center">
          <EmptyState text="等待指令：请输入股票代码并选择需要生成的结构化诊断报告类型" />
        </div>
      ) : null}
      {result ? (
        <>
          <DecisionCard data={result as Record<string, unknown>} />
          <details className="mt-3">
            <summary className="cursor-pointer text-text-muted">查看详细数据</summary>
            {(() => {
              const rows = extractArray(result);
              return rows.length
                ? <DataTable rows={rows} maxHeight={300} onExport={() => exportCSV(rows, 'assistant-result')} />
                : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(result, null, 2)}</pre>;
            })()}
          </details>
        </>
      ) : null}
      <div className="mt-6 rounded-xl border border-glass-border bg-surface/80 px-4 py-3 text-center text-xs text-text-muted">
        本分析结果仅供参考，不构成投资建议。投资有风险，入市需谨慎。
      </div>
    </PageContainer>
  );
}
