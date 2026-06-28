import { Play, RefreshCw, Save, Search, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { ActiveFilters, FilterBar, type FilterConfig, type FilterValues } from "../components/FilterComponents";
import { DraggableDataTable } from "../components/DraggableDataTable";
import { DryRunPreview } from "../components/IntentComponents";
import { MarketHeatmap, type HeatmapData } from "../components/FinancialChart";
import { EmptyState as SharedEmptyState, ErrorState as SharedErrorState, FilterEmptyState, MockDataNotice } from "../components/StateComponents";
import { StatusLight, inferStatusFromData } from "../components/StatusLight";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, DataTable, EmptyState, GatedNotice, JsonPanel, LinkCard, PageShell, Panel, ResourcePanel, StatusBadge } from "../components/ui";
import type { ApiProblem, UnknownRecord } from "../types";
import { dataObject, firstArray, list, metric, type PageProps, statusTone, valueOf } from "./pageUtils";

type RadarFilters = {
  tier: string;
  symbol: string;
  min_score: string;
  limit: string;
};

type PairLikeRecord = Record<string, unknown>;

function normalizeRadarFilters(filters: RadarFilters) {
  return {
    tier: filters.tier || undefined,
    symbol: filters.symbol || undefined,
    min_score: filters.min_score ? Number(filters.min_score) : undefined,
    limit: filters.limit ? Number(filters.limit) : undefined
  };
}

function summarizeError(error: ApiProblem | null) {
  if (!error) return null;
  return error.detail || error.title;
}

function brokerRows(payload: unknown, key: "accounts" | "positions" | "orders") {
  const envelope = dataObject(payload, {});
  const rows = firstArray(envelope, [key, "data"]);
  return rows;
}

function analyticsRecord(payload: unknown) {
  const envelope = dataObject(payload, {});
  const data = dataObject(envelope.data, envelope);
  return dataObject<UnknownRecord>(data.analytics, {});
}

function candidateDetailFields(candidate: PairLikeRecord) {
  return [
    { label: "代码", value: valueOf(candidate, ["symbol"], "-") },
    { label: "名称", value: valueOf(candidate, ["name"], "-") },
    { label: "层级", value: valueOf(candidate, ["tier"], "-") },
    { label: "分数", value: valueOf(candidate, ["score"], "-") },
    { label: "原因", value: valueOf(candidate, ["reason", "thesis", "summary"], "-") },
    { label: "风险", value: valueOf(candidate, ["risk", "risk_note"], "-") }
  ];
}

export function FinancePages(props: PageProps) {
  switch (props.view) {
    case "stock-data-sources":
      return <StockDataSourcesPage {...props} />;
    case "data-sync":
      return <DataSyncPage {...props} />;
    case "finance-lab":
      return <FinanceLabPage {...props} />;
    case "stock-radar":
      return <StockRadarPage {...props} />;
    case "market-temperature":
      return <MarketTemperaturePage {...props} />;
    case "quant-research":
      return <QuantResearchPage {...props} />;
    case "financial-manager":
      return <FinancialManagerPage {...props} />;
    default:
      return null;
  }
}

function StockDataSourcesPage({ api, controlAvailable, settings }: PageProps) {
  const sources = useAsyncResource(() => api.stockDataSources(), [api]);
  const [form, setForm] = useState({ provider: "akshare", enabled: true, api_key: "", base_url: "" });
  const [result, setResult] = useState<unknown>(null);

  async function testSource() {
    setResult(await api.stockDataSourceTest(form));
  }

  async function saveSource() {
    setResult(await api.stockDataSourceSave(form));
    await sources.reload();
  }

  const rows = list(sources.data);
  return (
    <PageShell
      title="股票数据源配置与测试"
      description="统一管理 AKShare、Tushare、TDX、TQCenter 等数据源，只展示配置状态与脱敏结果。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="保存 / 测试数据源" />}
      metrics={[
        metric("数据源", rows.length, "info"),
        metric("Ready", rows.filter((item) => statusTone(item.status) === "success").length, "success"),
        metric("Missing", rows.filter((item) => statusTone(item.status) === "warning").length, "warning"),
        metric("模式", settings?.mode || "mock", settings?.mode === "mock" ? "warning" : "info")
      ]}
    >
      {settings?.mode === "mock" ? <MockDataNotice /> : null}
      <div className="grid-2">
        <Panel title="数据源列表">
          <DataTable
            items={rows}
            columns={[
              { key: "name", header: "来源" },
              { key: "configured", header: "已配置" },
              {
                key: "status",
                header: "状态",
                render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} />
              },
              { key: "secrets_redacted", header: "已脱敏" }
            ]}
          />
        </Panel>

        <Panel title="配置表单">
          <div className="form-grid">
            <label className="field">
              <span>Source</span>
              <select data-testid="stock-source-provider" value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })}>
                <option value="akshare">AKShare</option>
                <option value="tushare">Tushare</option>
                <option value="tdx">TDX</option>
                <option value="tqcenter">TQCenter</option>
              </select>
            </label>
            <label className="field">
              <span>Base URL / Path</span>
              <input data-testid="stock-source-base-url" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} />
            </label>
            <label className="field">
              <span>API Key</span>
              <input data-testid="stock-source-api-key" type="password" value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} />
            </label>
            <label className="field">
              <span>Enabled</span>
              <select value={String(form.enabled)} onChange={(event) => setForm({ ...form, enabled: event.target.value === "true" })}>
                <option value="true">enabled</option>
                <option value="false">disabled</option>
              </select>
            </label>
          </div>

          <div className="page-actions">
            <Button data-testid="stock-source-test" icon={<Play size={16} />} disabled={!controlAvailable} onClick={() => void testSource()}>
              测试
            </Button>
            <Button data-testid="stock-source-save" icon={<Save size={16} />} disabled={!controlAvailable} onClick={() => void saveSource()}>
              保存
            </Button>
          </div>
        </Panel>
      </div>

      <JsonPanel data={{ sources: sources.data, last_result: result }} title="数据源证据" />
    </PageShell>
  );
}

function DataSyncPage({ api }: PageProps) {
  const status = useAsyncResource(() => api.dataStatus(), [api]);
  const [codes, setCodes] = useState("600519,300750,000858");
  const [plan, setPlan] = useState<unknown>(null);
  const statusData = dataObject(status.data, {});
  const freshness = dataObject(statusData.freshness, {});
  const missing = Array.isArray(statusData.missing) ? statusData.missing : [];
  const stale = Array.isArray(statusData.stale) ? statusData.stale : [];

  async function createPlan() {
    setPlan(await api.dataSyncPlan({ codes, task_type: "preflight", dry_run: true }));
  }

  return (
    <PageShell
      title="数据状态与同步计划"
      description="总览数据库、freshness、缺失项与 dry-run 同步计划；实际执行仍由后端 intent 和 control token 约束。"
      metrics={[
        metric("Database", valueOf(dataObject(statusData.database, {}), ["status"]), statusTone(dataObject(statusData.database, {}).status)),
        metric("Freshness", freshness.status || "-", statusTone(freshness.status)),
        metric("Missing", missing.length, missing.length ? "warning" : "success"),
        metric("Stale", stale.length, stale.length ? "warning" : "success")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="数据状态" resource={status}>
          {(data) => <JsonPanel data={data} title="Data status payload" />}
        </ResourcePanel>

        <Panel title="同步计划">
          <label className="field">
            <span>股票代码</span>
            <textarea data-testid="data-sync-codes" value={codes} onChange={(event) => setCodes(event.target.value)} />
            <small>这里只生成计划，不直接写入数据；实际执行仍需后端的 intent / control 门禁。</small>
          </label>
          <Button data-testid="data-sync-plan" icon={<RefreshCw size={16} />} onClick={() => void createPlan()}>
            生成同步计划
          </Button>
          {plan ? <JsonPanel data={plan} title="同步计划结果" /> : null}
        </Panel>
      </div>

      <Panel title="缺失与过期项">
        <DataTable
          items={[...missing.map((name) => ({ name, status: "missing" })), ...stale.map((name) => ({ name, status: "stale" }))]}
          columns={[
            { key: "name", header: "对象" },
            {
              key: "status",
              header: "状态",
              render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} />
            }
          ]}
        />
      </Panel>
    </PageShell>
  );
}

function FinanceLabPage({ api, workbench }: PageProps) {
  const dataStatus = useAsyncResource(() => api.dataStatus(), [api]);
  const radar = useAsyncResource(() => api.stockRadarStatus(), [api]);
  const broker = useAsyncResource(() => api.brokerReadiness(), [api]);
  const manager = useAsyncResource(() => api.financialManagerStatus(), [api]);
  const data = dataObject(dataStatus.data, {});
  const radarData = dataObject(radar.data, {});
  const brokerData = dataObject(broker.data, {});
  const managerData = dataObject(manager.data, {});

  return (
    <PageShell
      title="Finance Lab"
      description="按总览、数据、雷达、温度、量化、经理台六个分区组织金融工作面，并保持更高级能力只作为内部能力承接。"
      metrics={[
        metric("数据状态", valueOf(dataObject(data.database, {}), ["status"]), statusTone(dataObject(data.database, {}).status)),
        metric("雷达候选", radarData.candidate_count || "-", "success"),
        metric("经理台", managerData.ready ? "ready" : "degraded", managerData.ready ? "success" : "warning"),
        metric("券商", brokerData.read_only ? "read-only" : "blocked", brokerData.read_only ? "info" : "warning")
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/finance" title="总览" detail="承接金融研究总览、当前线程上下文与关键 readiness。" tone="info" />
        <LinkCard to="/stock-data-sources" title="数据" detail="数据源、同步计划、freshness 和缺失项。" tone="success" />
        <LinkCard to="/stock-radar" title="雷达" detail="候选股、摘要、受控动作与推送意图。" tone="warning" />
        <LinkCard to="/market-temperature" title="温度" detail="市场广度、行业冷热和缓存 readiness。" />
        <LinkCard to="/quant-research" title="量化" detail="Preset、研究运行、报告与证据。" />
        <LinkCard to="/financial-manager" title="经理台" detail="只读查询、受控意图与券商只读信息。" tone="gated" />
      </div>

      <div className="grid-2">
        <Panel title="当前上下文">
          <JsonPanel
            data={{
              current_thread: workbench?.currentThread,
              current_run: workbench?.currentRun,
              data_status: dataStatus.data,
              radar: radar.data
            }}
            title="Finance lab context"
          />
        </Panel>
        <Panel title="产品边界">
          <p>更高级的工厂能力继续隐藏为内部能力入口，仅保留承接关系，不作为直接产品主入口。</p>
          <JsonPanel data={{ broker: broker.data, manager: manager.data }} title="Broker / Manager readiness" />
        </Panel>
      </div>
    </PageShell>
  );
}

function StockRadarPage({ api, controlAvailable }: PageProps) {
  const [filters, setFilters] = useState<RadarFilters>({ tier: "", symbol: "", min_score: "", limit: "20" });
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set());
  const [targetPoolId, setTargetPoolId] = useState("");
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [actionError, setActionError] = useState<string>("");
  const query = useMemo(() => normalizeRadarFilters(filters), [filters]);
  const status = useAsyncResource(() => api.stockRadarStatus({ limit: query.limit }), [api, query.limit]);
  const candidates = useAsyncResource(() => api.stockRadarCandidates(query), [api, query.tier, query.symbol, query.min_score, query.limit]);
  const pools = useAsyncResource(() => api.userStockPools(), [api]);
  const latestRunId = String(dataObject(status.data, {}).latest_run_id || "");
  const digest = useAsyncResource(
    () =>
      api.stockRadarDigest({
        run_id: latestRunId || undefined,
        channels: "local,preview",
        limit: query.limit
      }),
    [api, latestRunId, query.limit]
  );

  const candidateRows = firstArray(dataObject(candidates.data, {}), ["candidates", "data"]);
  const poolRows = list(pools.data);
  const selectedCandidateRows = candidateRows.filter((item) => selectedCandidateIds.has(String(item.symbol || item.code || "")));
  const statusData = dataObject(status.data, {});
  const digestData = dataObject(digest.data, {});
  const selectedCandidate =
    candidateRows.find((item) => String(item.symbol || "") === selectedSymbol) ||
    candidateRows[0] ||
    null;
  const filterConfigs: FilterConfig[] = [
    {
      id: "tier",
      label: "层级",
      type: "select",
      options: [
        { value: "A", label: "A" },
        { value: "B", label: "B" },
        { value: "C", label: "C" }
      ]
    },
    {
      id: "symbol",
      label: "股票 / 关键词",
      type: "search",
      placeholder: "输入代码或名称"
    },
    {
      id: "min_score",
      label: "最低分数",
      type: "select",
      options: [
        { value: "60", label: "60+" },
        { value: "70", label: "70+" },
        { value: "80", label: "80+" }
      ]
    },
    {
      id: "limit",
      label: "数量上限",
      type: "select",
      options: [
        { value: "10", label: "10" },
        { value: "20", label: "20" },
        { value: "50", label: "50" }
      ]
    }
  ];

  function toFilterValues(): FilterValues {
    return filters;
  }

  function clearFilters() {
    setFilters({ tier: "", symbol: "", min_score: "", limit: "20" });
  }

  async function createRadarIntent(action: "run" | "deliver") {
    setActionError("");
    setActionResult(null);
    try {
      const result = await api.createIntent({
        action: action === "run" ? "stock_radar.run_once" : "stock_radar.push_digest",
        params: {
          run_id: statusData.latest_run_id,
          channels: action === "deliver" ? ["local"] : undefined,
          dry_run: true
        },
        rationale: `Desktop stock radar ${action} intent`
      });
      setActionResult(result);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    }
  }

  async function addSelectedToPool() {
    if (!targetPoolId || !selectedCandidateRows.length) return;
    setActionError("");
    const results = [];
    for (const candidate of selectedCandidateRows) {
      const code = String(candidate.symbol || candidate.code || "");
      if (!code) continue;
      try {
        const result = await api.stockPoolAddStock(targetPoolId, {
          code,
          name: String(candidate.name || code),
          tags: ["radar"],
          note: `Radar tier=${String(candidate.tier || "-")} score=${String(candidate.score || "-")}`
        });
        results.push({ code, success: true, result });
      } catch (error) {
        results.push({ code, success: false, error: error instanceof Error ? error.message : String(error) });
      }
    }
    setActionResult({ object: "stock_radar.batch_add_to_pool", pool_id: targetPoolId, results });
    setSelectedCandidateIds(new Set());
    await pools.reload();
  }

  const hasActiveFilters = Boolean(filters.tier || filters.symbol || filters.min_score || filters.limit !== "20");
  const candidateError = candidates.error || status.error;
  const noCandidates = !candidateError && !candidates.loading && candidateRows.length === 0;

  return (
    <PageShell
      title="Stock Radar"
      description="承接股票发现、候选池、摘要、风险说明和受控动作意图。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="运行 / 推送雷达意图" />}
      metrics={[
        metric("最新运行", statusData.latest_run_id || "-", "info"),
        metric("候选数", candidateRows.length || statusData.candidate_count || 0, "success"),
        metric("摘要", digestData.digest ? "ready" : "empty", digestData.digest ? "success" : "warning"),
        metric("投递", digestData.delivery_intent_required ? "intent" : "read-only", digestData.delivery_intent_required ? "gated" : "success")
      ]}
    >
      <FilterBar
        filters={filterConfigs}
        values={toFilterValues()}
        onChange={(nextValues) =>
          setFilters({
            tier: String(nextValues.tier || ""),
            symbol: String(nextValues.symbol || ""),
            min_score: String(nextValues.min_score || ""),
            limit: String(nextValues.limit || "20")
          })
        }
        onClear={clearFilters}
      />
      <ActiveFilters
        filters={filterConfigs}
        values={toFilterValues()}
        onRemove={(id) => setFilters((current) => ({ ...current, [id]: id === "limit" ? "20" : "" }))}
        onClear={clearFilters}
      />

      <div className="grid-2">
        <Panel title="候选股">
          {candidates.loading ? <SharedEmptyState title="Loading..." detail="正在加载雷达候选。" /> : null}
          {candidateError ? <SharedErrorState error={candidateError} onRetry={() => void candidates.reload()} /> : null}
          {noCandidates ? (
            hasActiveFilters ? (
              <FilterEmptyState onClear={clearFilters} />
            ) : (
              <EmptyState title="暂无候选股" detail="当前没有可展示的雷达候选，请稍后刷新或调整数据条件。" />
            )
          ) : null}
          {!candidates.loading && !candidateError && candidateRows.length ? (
            <DraggableDataTable
              items={candidateRows}
              getRowId={(item) => String(item.symbol || item.code || "")}
              selectedIds={selectedCandidateIds}
              onSelectionChange={setSelectedCandidateIds}
              batchActions={
                <>
                  <select
                    data-testid="stock-radar-target-pool"
                    value={targetPoolId}
                    onChange={(event) => setTargetPoolId(event.target.value)}
                    disabled={!controlAvailable}
                  >
                    <option value="">Select pool</option>
                    {poolRows.map((pool) => (
                      <option key={String(pool.id || "")} value={String(pool.id || "")}>
                        {valueOf(pool, ["name"], String(pool.id || ""))}
                      </option>
                    ))}
                  </select>
                  <Button
                    data-testid="stock-radar-add-selected"
                    tone="success"
                    icon={<Save size={14} />}
                    disabled={!controlAvailable || !targetPoolId || !selectedCandidateRows.length}
                    onClick={() => void addSelectedToPool()}
                  >
                    Add to pool
                  </Button>
                </>
              }
              columns={[
                {
                  key: "symbol",
                  header: "代码",
                  render: (item) => (
                    <button
                      type="button"
                      className="table-link-button"
                      data-testid={`stock-radar-candidate-${String(item.symbol || "")}`}
                      onClick={() => setSelectedSymbol(String(item.symbol || ""))}
                    >
                      {String(item.symbol || "-")}
                    </button>
                  )
                },
                { key: "name", header: "名称" },
                { key: "tier", header: "层级" },
                { key: "score", header: "分数" },
                { key: "risk", header: "风险" }
              ]}
            />
          ) : null}
        </Panel>

        <Panel title="候选详情" className="stock-radar-detail">
          {selectedCandidate ? (
            <div data-testid="stock-radar-detail">
              <div className="page-actions" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <div>
                  <strong>{valueOf(selectedCandidate, ["name"], valueOf(selectedCandidate, ["symbol"], "-"))}</strong>
                  <div style={{ color: "var(--text-muted)", fontSize: 13 }}>{valueOf(selectedCandidate, ["symbol"], "-")}</div>
                </div>
                <StatusBadge tone={Number(selectedCandidate.score ?? 0) >= 80 ? "success" : "warning"}>Score {valueOf(selectedCandidate, ["score"], "-")}</StatusBadge>
              </div>
              <div className="form-grid">
                {candidateDetailFields(selectedCandidate).map((field) => (
                  <div className="field" key={field.label}>
                    <span>{field.label}</span>
                    <strong>{field.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState title="未选择候选" detail="点击左侧候选项查看详情。" />
          )}
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="摘要与动作">
          {digest.loading ? <SharedEmptyState title="Loading..." detail="正在加载雷达摘要。" /> : null}
          {digest.error ? <SharedErrorState error={digest.error} onRetry={() => void digest.reload()} /> : null}
          {!digest.loading && !digest.error ? (
            digestData.digest ? <p data-testid="stock-radar-digest">{String(digestData.digest)}</p> : <EmptyState title="暂无摘要" detail="当前没有可展示的 digest。" />
          ) : null}
          <div className="page-actions">
            <Button data-testid="stock-radar-run-intent" icon={<Play size={16} />} disabled={!controlAvailable} onClick={() => void createRadarIntent("run")}>
              创建运行意图
            </Button>
            <Button data-testid="stock-radar-deliver-intent" icon={<ShieldAlert size={16} />} disabled={!controlAvailable} onClick={() => void createRadarIntent("deliver")}>
              创建推送意图
            </Button>
          </div>
          {actionError ? <p role="alert">{actionError}</p> : null}
          {actionResult ? <JsonPanel data={actionResult} title="Radar intent result" /> : null}
        </Panel>

        <Panel title="筛选说明">
          <p>当前页面会把 `tier`、`symbol`、`min_score`、`limit` 直接透传到雷达候选接口，不再无条件全量拉取。</p>
          <JsonPanel data={{ filters: query, status: status.data }} title="Radar query evidence" />
        </Panel>
      </div>

      <JsonPanel data={{ status: status.data, candidates: candidates.data, digest: digest.data }} title="Stock radar evidence" />
    </PageShell>
  );
}

function MarketTemperaturePage({ api }: PageProps) {
  const snapshot = useAsyncResource(() => api.marketTemperatureSnapshot(), [api]);
  const readiness = useAsyncResource(() => api.marketTemperatureReadiness(), [api]);
  const [historyWindow, setHistoryWindow] = useState("7");
  const parsedHistoryWindow = [3, 7, 14, 30].includes(Number(historyWindow)) ? Number(historyWindow) : 7;
  const history = useAsyncResource(() => api.marketTemperatureHistory(parsedHistoryWindow, true), [api, parsedHistoryWindow]);
  const snapshotEnvelope = dataObject(snapshot.data, {});
  const readinessEnvelope = dataObject(readiness.data, {});
  const historyEnvelope = dataObject(history.data, {});
  const snapshotData = dataObject(snapshotEnvelope.data, snapshotEnvelope);
  const readinessData = dataObject(readinessEnvelope.data, readinessEnvelope);
  const market = dataObject(snapshotData.market, {});
  const hot = firstArray(snapshotData, ["hot_industries"]);
  const cold = firstArray(snapshotData, ["cold_industries"]);
  const historyData = dataObject(historyEnvelope.data, historyEnvelope);
  const historyItems = firstArray(historyData, ["items"]);
  const heatmapLoading = snapshot.loading || history.loading;
  const heatmapError = snapshot.error || history.error;

  const heatmapData = useMemo<HeatmapData[]>(() => {
    const primary = [...hot, ...cold];
    if (primary.length) {
      return primary.map((item, index) => ({
        industry: valueOf(item, ["name", "industry", "code"], `Sector ${index + 1}`),
        temperature: Number(item.temperature ?? 0),
        stocks: Math.max(1, Number(item.stock_count ?? item.stocks ?? Math.round(Number(item.breadth ?? 0.3) * 20))),
        avgChange: Number(item.change ?? item.avg_change ?? ((Number(item.breadth ?? 0.5) - 0.5) * 10))
      }));
    }
    const latestHistory = dataObject(historyItems[0]?.snapshot, {});
    const industries = firstArray(latestHistory, ["industries"]);
    return industries.map((item, index) => ({
      industry: valueOf(item, ["name", "industry", "code"], `Sector ${index + 1}`),
      temperature: Number(item.temperature ?? 0),
      stocks: Math.max(1, Number(item.stock_count ?? 1)),
      avgChange: Number(item.change ?? item.avg_change ?? 0)
    }));
  }, [cold, historyItems, hot]);

  return (
    <PageShell
      title="Market Temperature"
      description="通过 `agent_market_temperature_*` 只读工具展示市场广度、行业冷热、缓存新鲜度与诊断信息。"
      metrics={[
        metric("温度", market.temperature || "-", statusTone(market.state)),
        metric("状态", market.state || "-", statusTone(market.state)),
        metric("样本", market.sample_count || "-", "info"),
        metric("缓存", readinessData.status || readinessData.ready || "-", statusTone(readinessData.status || readinessData.ready))
      ]}
    >
      <Panel
        title="Heatmap"
        action={
          <label className="field" style={{ minWidth: 140 }}>
            <span>History window</span>
            <select data-testid="market-history-window" value={historyWindow} onChange={(event) => setHistoryWindow(event.target.value)}>
              <option value="3">3 days</option>
              <option value="7">7 days</option>
              <option value="14">14 days</option>
              <option value="30">30 days</option>
            </select>
          </label>
        }
      >
        <div data-testid="market-heatmap-panel">
          {heatmapLoading ? <SharedEmptyState title="Loading..." detail="Loading market temperature snapshot and history." /> : null}
          {heatmapError ? (
            <SharedErrorState
              error={heatmapError}
              onRetry={() => {
                void snapshot.reload();
                void history.reload();
              }}
            />
          ) : null}
          {!heatmapLoading && !heatmapError && heatmapData.length ? (
            <div data-testid="market-heatmap-ready">
              <MarketHeatmap data={heatmapData} />
            </div>
          ) : null}
          {!heatmapLoading && !heatmapError && !heatmapData.length ? (
            <EmptyState title="No heatmap data" detail="No market temperature industries are available for the selected history window." />
          ) : null}
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title="热门行业">
          <DataTable items={hot} columns={[{ key: "industry", header: "行业" }, { key: "temperature", header: "温度" }, { key: "breadth", header: "广度" }]} />
        </Panel>
        <Panel title="低温行业">
          <DataTable items={cold} columns={[{ key: "industry", header: "行业" }, { key: "temperature", header: "温度" }, { key: "breadth", header: "广度" }]} />
        </Panel>
      </div>

      <Panel title="Snapshot history">
        <DataTable
          items={historyItems}
          columns={[
            { key: "as_of", header: "Date" },
            { key: "market_temperature", header: "Temperature" },
            { key: "market_state", header: "State" },
            { key: "quality_status", header: "Quality" }
          ]}
          empty="No cached history"
        />
      </Panel>

      <JsonPanel data={{ snapshot: snapshot.data, readiness: readiness.data, history: history.data }} title="Market temperature evidence" />
    </PageShell>
  );
}

function QuantResearchPage({ api }: PageProps) {
  const presets = useAsyncResource(() => api.quantPresets(), [api]);
  const [preset, setPreset] = useState("momentum_research");
  const [symbol, setSymbol] = useState("600519");
  const [run, setRun] = useState<unknown>(null);
  const [report, setReport] = useState<unknown>(null);
  const rows = list(presets.data);

  async function createRun() {
    const result = await api.quantRun({ preset, universe: [symbol], dry_run: true, source: "desktop_v1" });
    setRun(result);
    setReport(null);
  }

  async function loadReport() {
    const runData = dataObject(run, {});
    const inner = dataObject(runData.data || runData, {});
    const research = dataObject(inner.research, {});
    const researchId = String(research.research_id || research.id || inner.id || inner.research_id || runData.id || "");
    if (!researchId) return;
    setReport(await api.quantReport(researchId));
  }

  const runData = dataObject(run, {});
  const runInner = dataObject(runData.data || runData, {});
  return (
    <PageShell
      title="Quant Research"
      description="由 preset、参数、研究运行与报告构成量化分区，保持 dry-run 与证据链清晰可见。"
      metrics={[
        metric("Presets", rows.length, "success"),
        metric("当前 preset", preset, "info"),
        metric("运行状态", runInner.status || "未运行", statusTone(runInner.status)),
        metric("报告", run ? "ready" : "pending", run ? "success" : "warning")
      ]}
    >
      <div className="grid-2">
        <Panel title="研究参数">
          <div className="form-grid">
            <label className="field">
              <span>Preset</span>
              <select data-testid="quant-preset" value={preset} onChange={(event) => setPreset(event.target.value)}>
                {rows.map((item) => (
                  <option value={String(item.id || item.name)} key={String(item.id || item.name)}>
                    {String(item.name || item.id)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Symbol</span>
              <input data-testid="quant-symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
            </label>
          </div>
          <div className="page-actions">
            <Button data-testid="quant-create-run" icon={<Play size={16} />} onClick={() => void createRun()}>
              创建研究运行
            </Button>
            <Button data-testid="quant-load-report" disabled={!run} onClick={() => void loadReport()}>
              Load report
            </Button>
          </div>
        </Panel>

        <Panel title="Preset 列表">
          <DataTable items={rows} columns={[{ key: "name", header: "名称" }, { key: "risk", header: "风险" }, { key: "default_universe", header: "默认范围" }]} />
        </Panel>
      </div>

      {run ? <JsonPanel data={{ run, report }} title="研究报告 / 运行证据" /> : null}
    </PageShell>
  );
}

function FinancialManagerPage({ api, controlAvailable }: PageProps) {
  const catalog = useAsyncResource(() => api.financialManagerCatalog(), [api]);
  const status = useAsyncResource(() => api.financialManagerStatus(), [api]);
  const broker = useAsyncResource(() => api.brokerReadiness(), [api]);
  const accounts = useAsyncResource(() => api.brokerAccounts(), [api]);
  const positions = useAsyncResource(() => api.brokerPositions(), [api]);
  const orders = useAsyncResource(() => api.brokerOrders(), [api]);
  const analytics = useAsyncResource(() => api.brokerAnalyticsLatest(), [api]);
  const [query, setQuery] = useState("请复核当前组合风险，只返回只读分析。");
  const [result, setResult] = useState<unknown>(null);
  const [previewAction, setPreviewAction] = useState<null | "intent" | "broker-run">(null);
  const statusData = dataObject(status.data, {});
  const brokerData = dataObject(broker.data, {});
  const accountRows = brokerRows(accounts.data, "accounts");
  const positionRows = brokerRows(positions.data, "positions");
  const orderRows = brokerRows(orders.data, "orders");
  const analyticsData = analyticsRecord(analytics.data);

  async function runQuery() {
    setResult(
      await api.financialManagerQuery({
        capability_id: "portfolio",
        action_id: "risk",
        params: { codes: ["600519", "000001"], weights: [0.6, 0.4], query },
        read_only: true
      })
    );
  }

  async function createIntent() {
    setResult(
      await api.financialManagerIntent({
        capability_id: "portfolio",
        action_id: "create",
        params: { name: "Desktop V1 dry-run book" },
        rationale: query
      })
    );
    setPreviewAction(null);
  }

  async function runBrokerAnalytics() {
    setResult(await api.brokerAnalyticsRun({ dry_run: true, source: "desktop_v1", read_only: true }));
    setPreviewAction(null);
    await analytics.reload();
  }

  async function loadBrokerAnalytics() {
    setResult(await api.brokerAnalyticsLatest());
    await analytics.reload();
  }

  return (
    <PageShell
      title="Financial Manager / Broker 只读"
      description="统一承接 manager catalog、status、只读 query、受控 intent 与 broker 只读信息，不暴露交易按钮。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="受控金融意图" />}
      metrics={[
        metric("Manager", statusData.ready ? "ready" : "degraded", statusData.ready ? "success" : "warning"),
        metric("Broker", brokerData.read_only ? "read-only" : "blocked", brokerData.read_only ? "info" : "warning"),
        metric("Live Trading", brokerData.live_trading_enabled ? "enabled" : "disabled", brokerData.live_trading_enabled ? "danger" : "success"),
        metric("Catalog", list(catalog.data).length, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="只读查询">
          <label className="field">
            <span>查询</span>
            <textarea data-testid="financial-query" value={query} onChange={(event) => setQuery(event.target.value)} />
          </label>
          <div className="page-actions">
            <Button data-testid="financial-run-query" icon={<Search size={16} />} onClick={() => void runQuery()}>
              运行只读查询
            </Button>
            <Button data-testid="financial-create-intent" icon={<ShieldAlert size={16} />} disabled={!controlAvailable} onClick={() => setPreviewAction("intent")}>
              创建受控意图
            </Button>
            <Button data-testid="broker-analytics-run" disabled={!controlAvailable} onClick={() => setPreviewAction("broker-run")}>
              Broker analytics dry-run
            </Button>
            <Button data-testid="broker-analytics-latest" disabled={!controlAvailable} onClick={() => void loadBrokerAnalytics()}>
              Latest broker analytics
            </Button>
          </div>

          {previewAction ? (
            <DryRunPreview
              title={previewAction === "intent" ? "金融意图预览" : "Broker analytics dry-run 预览"}
              changes={[
                { label: "动作", after: previewAction === "intent" ? "portfolio_manager.create" : "broker.analytics.run" },
                { label: "模式", after: "read-only / dry-run" },
                { label: "说明", after: query }
              ]}
              onCancel={() => setPreviewAction(null)}
              onConfirm={() => void (previewAction === "intent" ? createIntent() : runBrokerAnalytics())}
            />
          ) : null}
        </Panel>

        <Panel title="Catalog">
          <DataTable items={list(catalog.data)} columns={[{ key: "name", header: "能力" }, { key: "side_effect", header: "副作用" }]} />
        </Panel>
      </div>

      <Panel title="我的实际情况">
        <div className="grid-2">
          <div>
            <h3 style={{ marginBottom: 12 }}>账户</h3>
            <DataTable items={accountRows} columns={[{ key: "provider", header: "Provider" }, { key: "account_id", header: "账户" }, { key: "read_only", header: "只读" }]} />
          </div>
          <div>
            <h3 style={{ marginBottom: 12 }}>最新分析</h3>
            {Object.keys(analyticsData).length ? (
              <div className="form-grid">
                <div className="field">
                  <span>总资产</span>
                  <strong>{valueOf(analyticsData, ["total_asset"], "-")}</strong>
                </div>
                <div className="field">
                  <span>现金占比</span>
                  <strong>{valueOf(analyticsData, ["cash_ratio"], "-")}</strong>
                </div>
                <div className="field">
                  <span>持仓数</span>
                  <strong>{valueOf(analyticsData, ["position_count"], "-")}</strong>
                </div>
                <div className="field">
                  <span>订单数</span>
                  <strong>{valueOf(analyticsData, ["order_count"], "-")}</strong>
                </div>
              </div>
            ) : (
              <EmptyState title="暂无分析结果" detail="点击上方按钮加载或生成最新券商分析。" />
            )}
          </div>
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title="持仓">
          <DataTable items={positionRows} columns={[{ key: "symbol", header: "代码" }, { key: "quantity", header: "数量" }, { key: "market_value", header: "市值" }]} />
        </Panel>
        <Panel title="订单只读">
          <DataTable items={orderRows} columns={[{ key: "id", header: "订单" }, { key: "symbol", header: "代码" }, { key: "status", header: "状态" }]} />
        </Panel>
      </div>

      <JsonPanel data={{ status: status.data, broker: broker.data, analytics: analytics.data, result }} title="Financial manager evidence" />
    </PageShell>
  );
}
