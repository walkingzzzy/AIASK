'use client';

import { useMemo, useState } from 'react';
import { PageContainer, SectionCard, StockCodeInput, DataTable, Badge } from '@/components/ui';
import { ProgressBar } from '@/components/ui';
import { LineChart } from '@/components/charts';
import { useApiQuery } from '@/hooks/use-api-query';
import { useApiMutation } from '@/hooks/use-api-mutation';
import { useStockCode } from '@/hooks/use-stock-code';
import { LoadingState, ErrorState } from '@/components/status-state';
import { extractArray, extractObject } from '@/lib/data-utils';
import { exportCSV } from '@/lib/export';
import { StockLink } from '@/components/stock-link';

export default function TdxPage() {
  const [formError, setFormError] = useState<string | null>(null);

  const { code: indCode, setCode: setIndCode, codeError: indCodeError, validate: indValidate, trimmedCode: indTrimmed } = useStockCode('600519');
  const [indName, setIndName] = useState('MACD');
  const indMut = useApiMutation<unknown>();

  const [formula, setFormula] = useState('');
  const screenMut = useApiMutation<unknown>();

  const [pushMsg, setPushMsg] = useState('');
  const [pushCode, setPushCode] = useState('');
  const [warnPrice, setWarnPrice] = useState('');
  const pushMut = useApiMutation<unknown>();
  const warnMut = useApiMutation<unknown>();

  const [wlName, setWlName] = useState('');
  const [wlCodes, setWlCodes] = useState('');
  const wlMut = useApiMutation<unknown>();

  const { code: sigCode, setCode: setSigCode, codeError: sigCodeError, validate: sigValidate, trimmedCode: sigTrimmed } = useStockCode('600519');
  const [sigPath, setSigPath] = useState<string | null>(null);
  const sigQ = useApiQuery<unknown>(sigPath);

  const loading = indMut.isPending || screenMut.isPending || pushMut.isPending || warnMut.isPending || wlMut.isPending || sigQ.isFetching;
  const error = formError || indMut.error || screenMut.error || pushMut.error || warnMut.error || wlMut.error || sigQ.error;

  const indValues = useMemo(() => extractArray(indMut.data, 'values', 'indicators', 'data') as Record<string, unknown>[], [indMut.data]);
  const indHasDate = indValues.length > 0 && ('date' in indValues[0] || 'time' in indValues[0]);
  const indNumericKeys = useMemo(() => {
    if (!indValues.length) return [] as string[];
    const first = indValues[0];
    return Object.keys(first).filter(k => k !== 'date' && k !== 'time' && typeof first[k] === 'number');
  }, [indValues]);
  const screenStocks = useMemo(() => extractArray(screenMut.data, 'stocks', 'results', 'data') as Record<string, unknown>[], [screenMut.data]);
  const sigSignals = useMemo(() => extractArray(sigQ.data, 'signals', 'data') as Record<string, unknown>[], [sigQ.data]);
  const pushResult = pushMut.data ? extractObject(pushMut.data) as Record<string, unknown> | null : null;
  const warnResult = warnMut.data ? extractObject(warnMut.data) as Record<string, unknown> | null : null;
  const wlResult = wlMut.data ? extractObject(wlMut.data) as Record<string, unknown> | null : null;

  function clearAndRun(fn: () => void) { setFormError(null); fn(); }

  function normalizeActionResult(result: Record<string, unknown> | null, fallbackLabel: string) {
    if (!result) return null;
    const success = result.success !== false && String(result.status ?? '').toLowerCase() !== 'error';
    const message = typeof result.message === 'string' ? result.message.trim() : '';
    return {
      ok: success,
      label: success ? fallbackLabel : '执行失败',
      message,
      diagnostics: result.diagnostics && typeof result.diagnostics === 'object'
        ? result.diagnostics as Record<string, unknown>
        : null,
    };
  }

  const pushStatus = normalizeActionResult(pushResult, '已发送');
  const warnStatus = normalizeActionResult(warnResult, '预警已发送');
  const watchlistStatus = normalizeActionResult(wlResult, '创建成功');

  return (
    <PageContainer>
      <h1>TDX 集成</h1>
      {loading ? <LoadingState text="处理中..." /> : null}
      {error ? <ErrorState text={error} hint="请稍后重试" /> : null}

      <SectionCard>
        <h3 className="mt-0">指标计算</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <StockCodeInput value={indCode} onChange={setIndCode} error={indCodeError} placeholder="股票代码" />
          <input value={indName} onChange={(e) => setIndName(e.target.value)} placeholder="指标名称，如 MACD" className="w-40" />
          <button type="button" disabled={loading} onClick={() => clearAndRun(() => {
            if (!indValidate()) return;
            indMut.trigger('/tdx/calculate-indicator', { method: 'POST' }, { code: indTrimmed, indicator: indName.trim() });
          })}>计算</button>
        </div>
        {indValues.length > 0 && indHasDate && indNumericKeys.length > 0 && (
          <LineChart
            categories={indValues.map(v => String(v.date ?? v.time ?? ''))}
            series={indNumericKeys.map(key => ({ name: key, data: indValues.map(v => Number(v[key]) || 0) }))}
            height={300}
          />
        )}
        {indValues.length > 0 ? (
          <DataTable rows={indValues} pageSize={20} onExport={() => exportCSV(indValues, `indicator-${indName}`)} />
        ) : indMut.data ? (
          <DataTable rows={[extractObject(indMut.data) as Record<string, unknown>].filter(Boolean)} />
        ) : null}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">选股器</h3>
        <textarea value={formula} onChange={(e) => setFormula(e.target.value)} placeholder="输入筛选公式" rows={3} className="w-full resize-y" />
        <button type="button" disabled={loading} className="mt-1.5" onClick={() => {
          if (!formula.trim()) { setFormError('请输入筛选公式'); return; }
          clearAndRun(() => screenMut.trigger('/tdx/screen-stocks', { method: 'POST' }, { formula: formula.trim() }));
        }}>筛选</button>
        {screenStocks.length > 0 && (
          <DataTable
            rows={screenStocks}
            columns={[
              { key: 'code', label: '代码', width: 100, render: (v: unknown, row: Record<string, unknown>) => <StockLink code={String(v)} name={String(row.name ?? '')} /> },
              { key: 'name', label: '名称', width: 120 },
              { key: 'matchScore', label: '匹配度', render: (v: unknown) => <ProgressBar value={Number(v) || 0} max={100} />, width: 200 },
            ]}
            onExport={() => exportCSV(screenStocks, 'screen-results')}
          />
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">推送消息</h3>
        <textarea value={pushMsg} onChange={(e) => setPushMsg(e.target.value)} placeholder="消息内容 / 预警原因" rows={2} className="w-full resize-y" />
        <div className="flex gap-2 flex-wrap items-center mt-1.5">
          <input value={pushCode} onChange={(e) => setPushCode(e.target.value)} maxLength={6} placeholder="股票代码（预警必填）" className="w-[160px]" />
          <input value={warnPrice} onChange={(e) => setWarnPrice(e.target.value)} inputMode="decimal" placeholder="预警价格（预警必填）" className="w-[180px]" />
          <button type="button" disabled={loading} onClick={() => {
            if (!pushMsg.trim()) { setFormError('请输入推送消息'); return; }
            const body: Record<string, unknown> = { message: pushMsg.trim() };
            if (pushCode.trim()) body.stock_code = pushCode.trim();
            clearAndRun(() => pushMut.trigger('/tdx/push-message', { method: 'POST' }, body));
          }}>发送</button>
          <button type="button" disabled={loading} onClick={() => {
            if (!pushMsg.trim()) { setFormError('请输入预警消息'); return; }
            if (!/^\d{6}$/.test(pushCode.trim())) { setFormError('发送预警需要填写 6 位股票代码'); return; }
            const price = Number(warnPrice);
            if (!Number.isFinite(price) || price <= 0) { setFormError('发送预警需要填写有效价格'); return; }
            const body: Record<string, unknown> = { message: pushMsg.trim(), stock_code: pushCode.trim(), price };
            clearAndRun(() => warnMut.trigger('/tdx/push-warn', { method: 'POST' }, body));
          }}>发送预警</button>
        </div>
        {pushStatus && (
          <div className="mt-2 flex items-center gap-2">
            <Badge variant={pushStatus.ok ? 'success' : 'danger'}>{pushStatus.label}</Badge>
            {pushStatus.message ? <span className="text-sm text-text-secondary">{pushStatus.message}</span> : null}
          </div>
        )}
        {warnStatus && (
          <div className="mt-2 flex items-center gap-2">
            <Badge variant={warnStatus.ok ? 'warning' : 'danger'}>{warnStatus.label}</Badge>
            {warnStatus.message ? <span className="text-sm text-text-secondary">{warnStatus.message}</span> : null}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">自选股创建</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <input value={wlName} onChange={(e) => setWlName(e.target.value)} placeholder="自选股名称" className="w-40" />
          <input value={wlCodes} onChange={(e) => setWlCodes(e.target.value)} placeholder="股票代码，逗号分隔" className="w-60" />
          <button type="button" disabled={loading} onClick={() => {
            if (!wlName.trim() || !wlCodes.trim()) { setFormError('名称和股票代码不能为空'); return; }
            clearAndRun(() => wlMut.trigger('/tdx/create-watchlist', { method: 'POST' }, {
              name: wlName.trim(), stock_codes: wlCodes.split(',').map((s) => s.trim()),
            }));
          }}>创建</button>
        </div>
        {watchlistStatus && (
          <div className="mt-2 flex items-center gap-2">
            <Badge variant={watchlistStatus.ok ? 'success' : 'danger'}>{watchlistStatus.label}</Badge>
            {watchlistStatus.message ? <span className="text-sm text-text-secondary">{watchlistStatus.message}</span> : null}
          </div>
        )}
      </SectionCard>

      <SectionCard>
        <h3 className="mt-0">专家信号</h3>
        <div className="flex gap-2 flex-wrap items-center">
          <StockCodeInput value={sigCode} onChange={setSigCode} error={sigCodeError} placeholder="股票代码" />
          <button type="button" disabled={loading} onClick={() => clearAndRun(() => {
            if (!sigValidate()) return;
            const newPath = `/tdx/expert-signals?code=${encodeURIComponent(sigTrimmed)}`;
            if (newPath === sigPath) sigQ.refetch();
            else setSigPath(newPath);
          })}>查询</button>
        </div>
        {sigSignals.length > 0 && (
          <DataTable
            rows={sigSignals}
            columns={[
              { key: 'name', label: '名称' },
              { key: 'type', label: '类型', render: (v: unknown) => <Badge variant="info">{String(v)}</Badge> },
              { key: 'value', label: '数值', align: 'right' as const },
              {
                key: 'direction', label: '方向',
                render: (v: unknown) => {
                  const d = String(v);
                  if (d === 'up') return <Badge variant="danger">买入</Badge>;
                  if (d === 'down') return <Badge variant="success">卖出</Badge>;
                  return <Badge variant="neutral">{d}</Badge>;
                },
              },
            ]}
            onExport={() => exportCSV(sigSignals, 'expert-signals')}
          />
        )}
      </SectionCard>
    </PageContainer>
  );
}
