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

  // Extract card data from response
  const result = rawData != null
    ? (rawData as Record<string, unknown>).card ?? rawData
    : null;

  function callAssistant(endpoint: string, label: string) {
    if (!validate()) return;
    reset();
    setActionLabel(label);
    trigger(endpoint, { method: 'POST' }, { code: trimmedCode });
  }

  return (
    <PageContainer>
      <h1>智能助手</h1>
      <div className="flex gap-2.5 flex-wrap items-center">
        <StockCodeInput value={code} onChange={setCode} error={codeError} placeholder="股票代码，如 600519" />
        <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/should-buy', '能不能买')}>
          能不能买?
        </button>
        <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/should-sell', '要不要卖')}>
          要不要卖?
        </button>
        <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/diagnosis', '综合诊断')}>
          综合诊断
        </button>
        <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/industry-chain', '产业链分析')}>
          产业链
        </button>
        <button type="button" disabled={isPending} onClick={() => callAssistant('/assistant/daily-report', '每日报告')}>
          每日报告
        </button>
      </div>
      {isPending ? <LoadingState text={`正在分析：${actionLabel}...`} /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}
      {!isPending && !result && !error ? <EmptyState text="输入股票代码，点击按钮获取分析结果" /> : null}
      {result ? (
        <>
          <DecisionCard data={result as Record<string, unknown>} />
          <details className="mt-3">
            <summary className="cursor-pointer text-gray-500">查看详细数据</summary>
            {(() => {
              const rows = extractArray(result);
              return rows.length
                ? <DataTable rows={rows} maxHeight={300} onExport={() => exportCSV(rows, 'assistant-result')} />
                : <pre className="mt-2 text-xs bg-surface-alt p-2 rounded overflow-auto max-h-[300px]">{JSON.stringify(result, null, 2)}</pre>;
            })()}
          </details>
        </>
      ) : null}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-100 px-4 py-2.5 text-center text-xs text-gray-500 border-t border-gray-200">
        本分析结果仅供参考，不构成投资建议。投资有风险，入市需谨慎。
      </div>
    </PageContainer>
  );
}
