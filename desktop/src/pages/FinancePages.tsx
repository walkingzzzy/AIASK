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

function radarCandidateRowId(item: UnknownRecord, index: number) {
  const explicit = item.id || item.candidate_id || item.row_id || item.event_id;
  if (explicit) return String(explicit);
  return [
    item.symbol || item.code || "unknown",
    item.tier || "tier",
    item.score || "score",
    item.name || "name",
    index
  ]
    .map((value) => String(value).replace(/\s+/g, "-"))
    .join("__");
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

const WRAPPER_KEYS = new Set([
  "object",
  "success",
  "data",
  "error",
  "error_code",
  "meta",
  "source",
  "cached",
  "timestamp",
  "source_chain",
  "quality_flags",
  "fallback_used",
  "degraded",
  "read_only",
  "secrets_redacted"
]);

function unwrapEnvelopeData(payload: unknown): UnknownRecord {
  let current = dataObject(payload, {});
  for (let index = 0; index < 3; index += 1) {
    const nested = current.data;
    if (!nested || typeof nested !== "object" || Array.isArray(nested)) break;
    const nonWrapperKeys = Object.keys(current).filter((key) => !WRAPPER_KEYS.has(key));
    if (nonWrapperKeys.length > 0 && current.success === undefined) break;
    current = nested as UnknownRecord;
  }
  return current;
}

function rowsFrom(record: UnknownRecord, keys: string[]): UnknownRecord[] {
  return firstArray(record, keys);
}

function compactValue(value: unknown, fallback = "-") {
  if (value === true) return "是";
  if (value === false) return "否";
  if (value === undefined || value === null || value === "") return fallback;
  if (Array.isArray(value)) return value.length ? value.join(", ") : fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function countFrom(record: UnknownRecord, keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (Array.isArray(value)) return value.length;
  }
  return fallback;
}

function sideEffectLevel(payload: unknown) {
  const envelope = dataObject(payload, {});
  const meta = dataObject(envelope.meta, {});
  const sideEffect = dataObject(meta.side_effect || envelope.side_effect, {});
  return valueOf(sideEffect, ["level"], valueOf(envelope, ["side_effect"], "read_only"));
}

function SummaryFields({ items }: { items: { label: string; value: unknown; tone?: "muted" | "strong" }[] }) {
  return (
    <div className="form-grid factory-summary-grid">
      {items.map((item) => (
        <div className="field factory-summary-field" key={item.label}>
          <span>{item.label}</span>
          <strong className={item.tone === "muted" ? "muted-value" : undefined}>{compactValue(item.value)}</strong>
        </div>
      ))}
    </div>
  );
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
    case "strategy-factory":
      return <StrategyFactoryPage {...props} />;
    case "factor-factory":
      return <FactorFactoryPage {...props} />;
    case "incubation":
      return <IncubationFactoryPage {...props} />;
    case "factory-events":
      return <FactoryEventsPage {...props} />;
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
              <span>服务地址 / 路径</span>
              <input data-testid="stock-source-base-url" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} />
            </label>
            <label className="field">
              <span>API 密钥</span>
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
      description="总览数据库、数据新鲜度、缺失项和同步预案；实际执行仍由后端审批意图和控制权限约束。"
      metrics={[
        metric("Database", valueOf(dataObject(statusData.database, {}), ["status"]), statusTone(dataObject(statusData.database, {}).status)),
        metric("Freshness", freshness.status || "-", statusTone(freshness.status)),
        metric("Missing", missing.length, missing.length ? "warning" : "success"),
        metric("Stale", stale.length, stale.length ? "warning" : "success")
      ]}
    >
      <div className="grid-2">
        <ResourcePanel title="数据状态" resource={status}>
          {(data) => <JsonPanel data={data} title="数据状态内容" />}
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
      title="金融研究"
      description="按数据、雷达、市场、量化、四工厂和经理台组织金融工作面；工厂能力通过 Agent 安全 facade 和受控意图开放。"
      metrics={[
        metric("数据状态", valueOf(dataObject(data.database, {}), ["status"]), statusTone(dataObject(data.database, {}).status)),
        metric("雷达候选", radarData.candidate_count || "-", "success"),
        metric("经理台", managerData.ready ? "ready" : "degraded", managerData.ready ? "success" : "warning"),
        metric("券商", brokerData.read_only ? "只读" : "阻止", brokerData.read_only ? "info" : "warning")
      ]}
    >
      <div className="grid-3">
        <LinkCard to="/finance" title="总览" detail="承接金融研究总览、当前会话上下文与关键就绪状态。" tone="info" />
        <LinkCard to="/stock-data-sources" title="数据" detail="数据源、同步计划、数据新鲜度和缺失项。" tone="success" />
        <LinkCard to="/stock-radar" title="雷达" detail="候选股、摘要、受控动作与推送意图。" tone="warning" />
        <LinkCard to="/market-temperature" title="温度" detail="市场广度、行业冷热和缓存就绪状态。" />
        <LinkCard to="/quant-research" title="量化" detail="研究模板、研究运行、报告与证据。" />
        <LinkCard to="/strategy-factory" title="策略工厂" detail="状态、运行、领域事件和交易预测只读证据。" tone="info" />
        <LinkCard to="/factor-factory" title="因子工厂" detail="因子挖掘状态、活跃池、引擎健康和 dry-run 意图。" tone="success" />
        <LinkCard to="/incubation" title="孵化工厂" detail="孵化 runner、编排器、观察通道和 dry-run 意图。" tone="warning" />
        <LinkCard to="/factory-events" title="工厂事件" detail="事件列表、任务预览、血缘、主题暴露和 outbox。" tone="gated" />
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
            title="金融研究上下文"
          />
        </Panel>
        <Panel title="产品边界">
          <p>四工厂页面只调用只读安全工具或创建受控 dry-run 意图；交易、提交、审批通过和外部投递仍由后端门禁约束。</p>
          <JsonPanel data={{ broker: broker.data, manager: manager.data }} title="券商与管理器就绪状态" />
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

  const candidateRows: Array<UnknownRecord & { __row_id: string }> = firstArray(dataObject(candidates.data, {}), ["candidates", "data"]).map(
    (item, index) => ({
      ...item,
      __row_id: radarCandidateRowId(item, index)
    })
  );
  const poolRows = list(pools.data);
  const selectedCandidateRows = candidateRows.filter((item) => selectedCandidateIds.has(String(item.__row_id || "")));
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
      title="股票雷达"
      description="承接股票发现、候选池、摘要、风险说明和受控动作意图。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="运行 / 推送雷达意图" />}
      metrics={[
        metric("最新运行", statusData.latest_run_id || "-", "info"),
        metric("候选数", candidateRows.length || statusData.candidate_count || 0, "success"),
        metric("摘要", digestData.digest ? "已生成" : "暂无", digestData.digest ? "success" : "warning"),
        metric("投递", digestData.delivery_intent_required ? "需要审批" : "只读预览", digestData.delivery_intent_required ? "gated" : "success")
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
          {candidates.loading ? <SharedEmptyState title="加载中..." detail="正在加载雷达候选。" /> : null}
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
              getRowId={(item) => String(item.__row_id || item.symbol || item.code || "")}
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
                    <option value="">选择股票池</option>
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
                    加入股票池
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
                      data-testid={`stock-radar-candidate-${String(item.__row_id || item.symbol || "")}`}
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
                <StatusBadge tone={Number(selectedCandidate.score ?? 0) >= 80 ? "success" : "warning"}>分数 {valueOf(selectedCandidate, ["score"], "-")}</StatusBadge>
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
          {digest.loading ? <SharedEmptyState title="加载中..." detail="正在加载雷达摘要。" /> : null}
          {digest.error ? <SharedErrorState error={digest.error} onRetry={() => void digest.reload()} /> : null}
          {!digest.loading && !digest.error ? (
            digestData.digest ? <p data-testid="stock-radar-digest">{String(digestData.digest)}</p> : <EmptyState title="暂无摘要" detail="当前没有可展示的摘要。" />
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
          {actionResult ? <JsonPanel data={actionResult} title="雷达动作结果" /> : null}
        </Panel>

        <Panel title="筛选说明">
          <p>当前页面会把 `tier`、`symbol`、`min_score`、`limit` 直接透传到雷达候选接口，不再无条件全量拉取。</p>
          <JsonPanel data={{ filters: query, status: status.data }} title="雷达查询依据" />
        </Panel>
      </div>

      <JsonPanel data={{ status: status.data, candidates: candidates.data, digest: digest.data }} title="股票雷达原始依据" />
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
      title="市场温度"
      description="通过 `agent_market_temperature_*` 只读工具展示市场广度、行业冷热、缓存新鲜度与诊断信息。"
      metrics={[
        metric("温度", market.temperature || "-", statusTone(market.state)),
        metric("状态", market.state || "-", statusTone(market.state)),
        metric("样本", market.sample_count || "-", "info"),
        metric("缓存", readinessData.status || readinessData.ready || "-", statusTone(readinessData.status || readinessData.ready))
      ]}
    >
      <Panel
        title="热力图"
        action={
          <label className="field" style={{ minWidth: 140 }}>
            <span>历史窗口</span>
            <select data-testid="market-history-window" value={historyWindow} onChange={(event) => setHistoryWindow(event.target.value)}>
              <option value="3">3 天</option>
              <option value="7">7 天</option>
              <option value="14">14 天</option>
              <option value="30">30 天</option>
            </select>
          </label>
        }
      >
        <div data-testid="market-heatmap-panel">
          {heatmapLoading ? <SharedEmptyState title="加载中..." detail="正在加载市场温度快照和历史记录。" /> : null}
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
            <EmptyState title="暂无热力图数据" detail="所选历史窗口内没有可展示的市场温度行业数据。" />
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

      <Panel title="快照历史">
        <DataTable
          items={historyItems}
          columns={[
            { key: "as_of", header: "日期" },
            { key: "market_temperature", header: "温度" },
            { key: "market_state", header: "状态" },
            { key: "quality_status", header: "质量" }
          ]}
          empty="暂无缓存历史"
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
      title="量化研究"
      description="由研究模板、参数、研究运行与报告构成量化分区，保持预演和证据链清晰可见。"
      metrics={[
        metric("模板", rows.length, "success"),
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
              加载报告
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

function StrategyFactoryPage({ api }: PageProps) {
  const status = useAsyncResource(() => api.strategyFactoryStatus(), [api]);
  const runs = useAsyncResource(() => api.strategyFactoryRuns(10), [api]);
  const events = useAsyncResource(() => api.strategyDomainEvents(20), [api]);
  const formalDiagnostics = useAsyncResource(() => api.strategyFactoryFormalDiagnostics(15), [api]);
  const predictionStatus = useAsyncResource(() => api.tradePredictionStatus({ limit: 100 }), [api]);
  const predictionOutcomes = useAsyncResource(() => api.tradePredictionOutcomes({ limit: 20 }), [api]);
  const predictionMatrix = useAsyncResource(() => api.tradePredictionMatrix({ dimensions: "family", limit: 100 }), [api]);

  const statusData = unwrapEnvelopeData(status.data);
  const runData = unwrapEnvelopeData(runs.data);
  const eventData = unwrapEnvelopeData(events.data);
  const formalDiagData = unwrapEnvelopeData(formalDiagnostics.data);
  const predictionData = unwrapEnvelopeData(predictionStatus.data);
  const outcomeData = unwrapEnvelopeData(predictionOutcomes.data);
  const matrixData = unwrapEnvelopeData(predictionMatrix.data);
  const formalDiag = dataObject(formalDiagData, {});
  const hardHist = dataObject(formalDiag.hard_gate_histogram, {});
  const exitFunnel = dataObject(formalDiag.exit_funnel, {});
  const exitGap = dataObject(formalDiag.exit_gap, {});
  const blockerRows = Array.isArray(formalDiag.top_blockers)
    ? formalDiag.top_blockers.map((item: any, index: number) => ({ id: `fb-${index}`, code: item?.code, count: item?.count }))
    : [];
  const evidenceGapRows = Array.isArray(formalDiag.evidence_gaps)
    ? formalDiag.evidence_gaps.map((item: any, index: number) => ({
        id: `eg-${index}`,
        code: item?.code,
        count: item?.count,
        coverage: item?.coverage
      }))
    : [];
  const exitGapSampleRows = Array.isArray(exitGap.sample_strategies)
    ? exitGap.sample_strategies.map((item: any, index: number) => ({
        id: `egs-${index}`,
        strategy_id: String(item?.strategy_id || "").slice(0, 12),
        status: item?.status || item?.incubating || "-",
        exit_signal_count: item?.exit_signal_count,
        open_positions: item?.open_positions
      }))
    : [];
  const nextActionRows = Array.isArray(formalDiag.next_actions)
    ? formalDiag.next_actions.map((item: any, index: number) => ({
        id: `na-${index}`,
        code: item?.code,
        detail: item?.detail
      }))
    : [];
  const runRows = rowsFrom(runData, ["runs", "items", "data"]);
  const eventRows = rowsFrom(eventData, ["events", "items", "data"]);
  const outcomeRows = rowsFrom(outcomeData, ["outcomes", "items", "data"]);
  const matrixRows = rowsFrom(matrixData, ["rows", "matrix", "items", "data"]);

  async function refreshAll() {
    await Promise.all([
      status.reload(),
      runs.reload(),
      events.reload(),
      formalDiagnostics.reload(),
      predictionStatus.reload(),
      predictionOutcomes.reload(),
      predictionMatrix.reload()
    ]);
  }

  return (
    <PageShell
      title="策略工厂"
      description="通过 Agent 安全工具读取策略工厂调度、Formal 阻塞、证据链、Exit 漏斗与 exit gap 调查；不提供实盘交易或直接生命周期推进。"
      actions={
        <Button data-testid="strategy-factory-refresh" icon={<RefreshCw size={16} />} onClick={() => void refreshAll()}>
          刷新工厂证据
        </Button>
      }
      metrics={[
        metric("运行时", statusData.runtime_enabled ? "启用" : "未启用", statusData.runtime_enabled ? "success" : "warning"),
        metric("事件模式", statusData.event_runtime_mode || statusData.schedule_mode || "-", statusTone(statusData.event_runtime_mode || statusData.schedule_mode)),
        metric("今日运行", statusData.daily_run_count ?? "-", "info"),
        metric("交易预测", predictionData.prediction_count ?? countFrom(predictionData, ["predictions", "items"], 0), "success")
      ]}
    >
            <div className="grid-3">
        <Panel title="Formal / Evidence">
          {formalDiagnostics.loading ? <SharedEmptyState title="loading..." detail="factory formal diagnostics" /> : null}
          {formalDiagnostics.error ? <SharedErrorState error={formalDiagnostics.error} onRetry={() => void formalDiagnostics.reload()} /> : null}
          {!formalDiagnostics.loading && !formalDiagnostics.error ? (
            <SummaryFields
              items={[
                { label: "formal_count", value: formalDiag.formal_count },
                { label: "observe_count", value: formalDiag.observe_count },
                { label: "signal_id_coverage", value: formalDiag.signal_id_coverage },
                { label: "orders_with_signal_id", value: formalDiag.orders_with_signal_id },
                { label: "orders_total", value: formalDiag.orders_total },
                { label: "trades_total", value: formalDiag.trades_total }
              ]}
            />
          ) : null}
        </Panel>
        <Panel title="Exit funnel">
          {!formalDiagnostics.loading && !formalDiagnostics.error ? (
            <SummaryFields
              items={[
                { label: "open_positions", value: exitFunnel.open_positions },
                { label: "with_exit_signal", value: exitFunnel.with_exit_signal },
                { label: "with_exit_order", value: exitFunnel.with_exit_order },
                { label: "closed", value: exitFunnel.closed },
                { label: "exit_order_conversion", value: exitFunnel.exit_order_conversion }
              ]}
            />
          ) : null}
        </Panel>
        <Panel title="Hard gate histogram">
          {!formalDiagnostics.loading && !formalDiagnostics.error ? (
            <SummaryFields
              items={[
                { label: "missing", value: hardHist.missing },
                { label: "bootstrap_pending", value: hardHist.bootstrap_pending },
                { label: "insufficient_samples", value: hardHist.insufficient_samples },
                { label: "failed_metrics", value: hardHist.failed_metrics },
                { label: "bootstrap_ready", value: hardHist.bootstrap_ready },
                { label: "passed", value: hardHist.passed }
              ]}
            />
          ) : null}
        </Panel>
      </div>

      <Panel title="Top formal blockers">
        <DataTable
          items={blockerRows}
          columns={[
            { key: "code", header: "blocker" },
            { key: "count", header: "count" }
          ]}
        />
      </Panel>

      <div className="grid-3">
        <Panel title="Evidence gaps">
          <DataTable
            items={evidenceGapRows}
            columns={[
              { key: "code", header: "gap" },
              { key: "count", header: "count" },
              { key: "coverage", header: "coverage" }
            ]}
          />
        </Panel>
        <Panel title="Exit gap investigation">
          {!formalDiagnostics.loading && !formalDiagnostics.error ? (
            <SummaryFields
              items={[
                { label: "exit_signals", value: exitGap.exit_signals },
                { label: "no_exit_order_strategies", value: exitGap.strategies_with_exit_signal_no_order },
                { label: "in_execution_universe", value: exitGap.exit_signals_in_execution_universe },
                { label: "execution_universe_size", value: exitGap.execution_universe_size },
                {
                  label: "likely_causes",
                  value: Array.isArray(exitGap.likely_causes) ? (exitGap.likely_causes as unknown[]).join(", ") : exitGap.likely_causes
                }
              ]}
            />
          ) : null}
          <DataTable
            items={exitGapSampleRows}
            columns={[
              { key: "strategy_id", header: "strategy" },
              { key: "status", header: "status" },
              { key: "exit_signal_count", header: "exit_sigs" },
              { key: "open_positions", header: "open" }
            ]}
          />
        </Panel>
        <Panel title="Recommended next actions">
          <DataTable
            items={nextActionRows}
            columns={[
              { key: "code", header: "action" },
              { key: "detail", header: "detail" }
            ]}
          />
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="工厂状态">
          {status.loading ? <SharedEmptyState title="加载中..." detail="正在读取策略工厂状态。" /> : null}
          {status.error ? <SharedErrorState error={status.error} onRetry={() => void status.reload()} /> : null}
          {!status.loading && !status.error ? (
            <SummaryFields
              items={[
                { label: "运行时启用", value: statusData.runtime_enabled },
                { label: "调度模式", value: statusData.schedule_mode },
                { label: "事件模式", value: statusData.event_runtime_mode },
                { label: "执行模式", value: statusData.execution_mode },
                { label: "循环次数", value: statusData.cycle_count },
                { label: "只读级别", value: sideEffectLevel(status.data) }
              ]}
            />
          ) : null}
        </Panel>

        <Panel title="交易预测只读诊断">
          {predictionStatus.loading ? <SharedEmptyState title="加载中..." detail="正在读取交易预测状态。" /> : null}
          {predictionStatus.error ? <SharedErrorState error={predictionStatus.error} onRetry={() => void predictionStatus.reload()} /> : null}
          {!predictionStatus.loading && !predictionStatus.error ? (
            <SummaryFields
              items={[
                { label: "预测数", value: predictionData.prediction_count },
                { label: "结果数", value: predictionData.outcome_count },
                { label: "待评估", value: predictionData.pending_count },
                { label: "已评估", value: predictionData.evaluated_count },
                { label: "状态", value: predictionData.status },
                { label: "已配置", value: predictionData.configured }
              ]}
            />
          ) : null}
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="最近运行">
          <DataTable
            items={runRows}
            columns={[
              { key: "id", header: "运行 ID", render: (item) => valueOf(item, ["id", "run_id"], "-") },
              { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
              { key: "execution_mode", header: "模式", render: (item) => valueOf(item, ["execution_mode", "mode"], "-") },
              { key: "accepted", header: "通过", render: (item) => valueOf(item, ["accepted", "accepted_count"], "-") }
            ]}
            empty="暂无策略工厂运行"
            mobileCard={(item) => ({
              title: valueOf(item, ["id", "run_id"], "运行"),
              subtitle: valueOf(item, ["status"], "未知状态"),
              details: [
                { label: "模式", value: valueOf(item, ["execution_mode", "mode"], "-") },
                { label: "通过", value: valueOf(item, ["accepted", "accepted_count"], "-") }
              ]
            })}
          />
        </Panel>

        <Panel title="领域事件">
          <DataTable
            items={eventRows}
            columns={[
              { key: "id", header: "事件", render: (item) => valueOf(item, ["id", "event_id"], "-") },
              { key: "event_type", header: "类型", render: (item) => valueOf(item, ["event_type", "type"], "-") },
              { key: "strategy_id", header: "策略", render: (item) => valueOf(item, ["strategy_id"], "-") },
              { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
            ]}
            empty="暂无领域事件"
            mobileCard={(item) => ({
              title: valueOf(item, ["event_type", "type"], "事件"),
              subtitle: valueOf(item, ["id", "event_id"], "-"),
              details: [
                { label: "策略", value: valueOf(item, ["strategy_id"], "-") },
                { label: "状态", value: valueOf(item, ["status"], "-") }
              ]
            })}
          />
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="预测结果样本">
          <DataTable
            items={outcomeRows}
            columns={[
              { key: "prediction_id", header: "预测", render: (item) => valueOf(item, ["prediction_id", "id"], "-") },
              { key: "stock_code", header: "股票", render: (item) => valueOf(item, ["stock_code", "symbol"], "-") },
              { key: "score", header: "评分", render: (item) => valueOf(item, ["score", "prediction_score"], "-") },
              { key: "data_quality_status", header: "质量", render: (item) => valueOf(item, ["data_quality_status", "quality_status"], "-") }
            ]}
            empty="暂无预测结果"
          />
        </Panel>
        <Panel title="预测贡献矩阵">
          <DataTable
            items={matrixRows}
            columns={[
              { key: "family", header: "维度", render: (item) => valueOf(item, ["family", "stage", "regime", "dimension"], "-") },
              { key: "prediction_count", header: "样本", render: (item) => valueOf(item, ["prediction_count", "count", "sample_n"], "-") },
              { key: "hit_rate", header: "命中率", render: (item) => valueOf(item, ["hit_rate", "rate"], "-") },
              { key: "contribution", header: "贡献", render: (item) => valueOf(item, ["contribution", "weight"], "-") }
            ]}
            empty="暂无预测矩阵"
          />
        </Panel>
      </div>

      <JsonPanel
        data={{
          status: status.data,
          runs: runs.data,
          events: events.data,
          trade_prediction_status: predictionStatus.data,
          trade_prediction_outcomes: predictionOutcomes.data,
          trade_prediction_matrix: predictionMatrix.data
        }}
        title="策略工厂只读证据"
      />
    </PageShell>
  );
}

function FactorFactoryPage({ api, controlAvailable }: PageProps) {
  const status = useAsyncResource(() => api.factorFactoryStatus(20), [api]);
  const [previewAction, setPreviewAction] = useState<null | "run_once" | "maintenance">(null);
  const [intentResult, setIntentResult] = useState<unknown>(null);
  const statusData = dataObject(status.data, {});
  const factory = dataObject(statusData.factory, {});
  const poolHealth = dataObject(statusData.pool_health, {});
  const engineHealth = dataObject(statusData.engine_health, {});
  const activeFactors = rowsFrom(statusData, ["active_factors", "factors", "data"]);
  const engineRows = rowsFrom(engineHealth, ["engines", "items", "data"]);

  async function createFactorIntent(action: "run_once" | "maintenance") {
    const result = await api.createIntent({
      title: action === "run_once" ? "因子工厂 dry-run 运行" : "因子工厂维护预演",
      action: action === "run_once" ? "factor_factory.run_once" : "factor_factory.maintenance",
      params: { dry_run: true, limit: 20, source: "desktop_factory_page" },
      rationale: "Desktop 因子工厂受控预演"
    });
    setIntentResult(result);
    setPreviewAction(null);
  }

  return (
    <PageShell
      title="因子工厂"
      description="读取因子挖掘工厂状态、引擎健康、活跃因子池；运行和维护只通过 ActionIntent dry-run 预演。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建因子工厂意图" />}
      actions={
        <Button data-testid="factor-factory-refresh" icon={<RefreshCw size={16} />} onClick={() => void status.reload()}>
          刷新状态
        </Button>
      }
      metrics={[
        metric("状态", statusData.status || "-", statusTone(statusData.status)),
        metric("已配置", statusData.configured ? "是" : "否", statusData.configured ? "success" : "warning"),
        metric("活跃因子", activeFactors.length, "success"),
        metric("池大小", factory.pool_size ?? poolHealth.active_promoted_count ?? "-", "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="工厂摘要">
          {status.loading ? <SharedEmptyState title="加载中..." detail="正在读取因子工厂状态。" /> : null}
          {status.error ? <SharedErrorState error={status.error} onRetry={() => void status.reload()} /> : null}
          {!status.loading && !status.error ? (
            <SummaryFields
              items={[
                { label: "初始化", value: factory.initialized },
                { label: "运行次数", value: factory.run_count },
                { label: "最近运行", value: factory.last_run_at },
                { label: "DB 池", value: factory.pool_loaded_from_db },
                { label: "可研究因子", value: poolHealth.research_consumable_count },
                { label: "证据不足", value: poolHealth.evidence_insufficient_count }
              ]}
            />
          ) : null}
        </Panel>

        <Panel title="受控动作">
          <p>这里不会直接启动长循环；按钮只创建后端 ActionIntent，参数固定为 dry-run/预演。</p>
          <div className="page-actions">
            <Button
              data-testid="factor-factory-run-intent"
              icon={<ShieldAlert size={16} />}
              disabled={!controlAvailable}
              onClick={() => setPreviewAction("run_once")}
            >
              创建运行意图
            </Button>
            <Button
              data-testid="factor-factory-maintenance-intent"
              icon={<ShieldAlert size={16} />}
              disabled={!controlAvailable}
              onClick={() => setPreviewAction("maintenance")}
            >
              创建维护意图
            </Button>
          </div>
          {previewAction ? (
            <DryRunPreview
              title="因子工厂意图预览"
              changes={[
                { label: "动作", after: previewAction === "run_once" ? "factor_factory.run_once" : "factor_factory.maintenance" },
                { label: "模式", after: "dry-run / 预演" },
                { label: "限制", after: "limit=20，不进入调度长循环" }
              ]}
              onCancel={() => setPreviewAction(null)}
              onConfirm={() => void createFactorIntent(previewAction)}
            />
          ) : null}
          {intentResult ? <JsonPanel data={intentResult} title="因子工厂意图结果" /> : null}
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="活跃因子池">
          <DataTable
            items={activeFactors}
            columns={[
              { key: "id", header: "因子", render: (item) => valueOf(item, ["name", "id", "factor_id"], "-") },
              { key: "family", header: "族群", render: (item) => valueOf(item, ["family", "factor_family"], "-") },
              { key: "engine", header: "引擎", render: (item) => valueOf(item, ["engine", "source"], "-") },
              { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
              { key: "ic", header: "IC", render: (item) => valueOf(item, ["ic", "recent_ic", "ic_mean"], "-") }
            ]}
            empty="暂无活跃因子"
            mobileCard={(item) => ({
              title: valueOf(item, ["name", "id", "factor_id"], "因子"),
              subtitle: valueOf(item, ["family", "factor_family"], "-"),
              details: [
                { label: "引擎", value: valueOf(item, ["engine", "source"], "-") },
                { label: "状态", value: valueOf(item, ["status"], "-") },
                { label: "IC", value: valueOf(item, ["ic", "recent_ic", "ic_mean"], "-") }
              ]
            })}
          />
        </Panel>

        <Panel title="引擎健康">
          <DataTable
            items={engineRows}
            columns={[
              { key: "name", header: "引擎", render: (item) => valueOf(item, ["name", "engine"], "-") },
              { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> },
              { key: "candidates", header: "候选", render: (item) => valueOf(item, ["candidates", "candidate_count"], "-") },
              { key: "accepted", header: "入池", render: (item) => valueOf(item, ["accepted", "accepted_count"], "-") }
            ]}
            empty="暂无引擎健康记录"
          />
        </Panel>
      </div>

      <JsonPanel data={status.data} title="因子工厂状态证据" />
    </PageShell>
  );
}

function IncubationFactoryPage({ api, controlAvailable }: PageProps) {
  const status = useAsyncResource(() => api.incubationFactoryStatus(), [api]);
  const formalDiagnostics = useAsyncResource(() => api.strategyFactoryFormalDiagnostics(15), [api]);
  const intents = useAsyncResource(() => api.intents(), [api]);
  const [previewAction, setPreviewAction] = useState<null | "dry_run" | "run_once" | "maintenance">(null);
  const [intentResult, setIntentResult] = useState<unknown>(null);
  const [intentBusy, setIntentBusy] = useState(false);
  const statusData = unwrapEnvelopeData(status.data);
  const lanes = dataObject(statusData.lanes, {});
  const lastRun = dataObject(statusData.last_run, {});
  const formalDiag = dataObject(unwrapEnvelopeData(formalDiagnostics.data), {});
  const exitFunnel = dataObject(formalDiag.exit_funnel, {});
  const exitGap = dataObject(formalDiag.exit_gap, {});
  const intentRows = list(intents.data)
    .filter((item) => String(item.action || item.target_tool || "").includes("incubation_factory"))
    .slice(0, 20)
    .map((item, index) => ({
      id: String(item.intent_id || item.id || `inc-intent-${index}`),
      action: String(item.action || item.target_action || "-"),
      status: String(item.status || "-"),
      updated_at: String(item.updated_at || item.created_at || "-"),
      error: String(item.error || "")
    }));

  async function refreshAll() {
    await Promise.all([status.reload(), formalDiagnostics.reload(), intents.reload()]);
  }

  async function createIncubationIntent(action: "dry_run" | "run_once" | "maintenance") {
    setIntentBusy(true);
    try {
      const actionToken =
        action === "dry_run"
          ? "incubation_factory.dry_run"
          : action === "run_once"
            ? "incubation_factory.run_once"
            : "incubation_factory.maintenance";
      const title =
        action === "dry_run"
          ? "孵化工厂 dry-run 观察"
          : action === "run_once"
            ? "孵化工厂 run_once（需确认）"
            : "孵化工厂维护预演";
      const result = await api.createIntent({
        title,
        action: actionToken,
        params: {
          dry_run: action !== "run_once",
          source: "desktop_incubation_page",
          _timeout_seconds: action === "run_once" ? 600 : 300
        },
        rationale:
          action === "run_once"
            ? "Desktop 孵化工厂真实 run_once；需 control token 确认后执行，不进入实盘"
            : "Desktop 孵化工厂受控预演"
      });
      setIntentResult(result);
      setPreviewAction(null);
      await intents.reload();
    } finally {
      setIntentBusy(false);
    }
  }

  async function confirmIntent(intentId: string) {
    if (!intentId) return;
    setIntentBusy(true);
    try {
      const result = await api.intentConfirm(intentId);
      setIntentResult(result);
      await refreshAll();
    } finally {
      setIntentBusy(false);
    }
  }

  async function denyIntent(intentId: string) {
    if (!intentId) return;
    setIntentBusy(true);
    try {
      const result = await api.intentDeny(intentId, "denied from incubation factory page");
      setIntentResult(result);
      await intents.reload();
    } finally {
      setIntentBusy(false);
    }
  }

  const previewActionLabel =
    previewAction === "run_once"
      ? "incubation_factory.run_once"
      : previewAction === "maintenance"
        ? "incubation_factory.maintenance"
        : "incubation_factory.dry_run";

  return (
    <PageShell
      title="孵化工厂"
      description="读取 runner 状态与 Formal/Exit 诊断；dry-run 默认，run_once 需 control token + Intent 确认；结果可在意图审计表回放。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建孵化工厂意图" />}
      actions={
        <Button data-testid="incubation-factory-refresh" icon={<RefreshCw size={16} />} onClick={() => void refreshAll()}>
          刷新状态
        </Button>
      }
      metrics={[
        metric("可用", statusData.available ? "是" : "否", statusData.available ? "success" : "warning"),
        metric("编排器", statusData.orchestrator_ready ? "就绪" : "未就绪", statusData.orchestrator_ready ? "success" : "warning"),
        metric("Formal", formalDiag.formal_count ?? "-", "info"),
        metric("Open pos", exitFunnel.open_positions ?? "-", Number(exitFunnel.open_positions) > 0 ? "warning" : "success")
      ]}
    >
      <div className="grid-3">
        <Panel title="孵化状态">
          {status.loading ? <SharedEmptyState title="加载中..." detail="正在读取孵化工厂状态。" /> : null}
          {status.error ? <SharedErrorState error={status.error} onRetry={() => void status.reload()} /> : null}
          {!status.loading && !status.error ? (
            <SummaryFields
              items={[
                { label: "可用", value: statusData.available },
                { label: "Runtime", value: statusData.runtime_type },
                { label: "编排器就绪", value: statusData.orchestrator_ready },
                { label: "状态", value: statusData.status },
                { label: "最近运行", value: valueOf(lastRun, ["status", "id"], "-") },
                { label: "错误数", value: statusData.error_count }
              ]}
            />
          ) : null}
        </Panel>

        <Panel title="Exit / Evidence 摘要">
          {formalDiagnostics.loading ? <SharedEmptyState title="loading..." detail="factory formal diagnostics" /> : null}
          {formalDiagnostics.error ? (
            <SharedErrorState error={formalDiagnostics.error} onRetry={() => void formalDiagnostics.reload()} />
          ) : null}
          {!formalDiagnostics.loading && !formalDiagnostics.error ? (
            <SummaryFields
              items={[
                { label: "formal_count", value: formalDiag.formal_count },
                { label: "observe_count", value: formalDiag.observe_count },
                { label: "signal_id_coverage", value: formalDiag.signal_id_coverage },
                { label: "open_positions", value: exitFunnel.open_positions },
                { label: "with_exit_signal", value: exitFunnel.with_exit_signal },
                { label: "closed", value: exitFunnel.closed },
                { label: "exit_gap.no_order", value: exitGap.strategies_with_exit_signal_no_order }
              ]}
            />
          ) : null}
        </Panel>

        <Panel title="观察通道 / 受控动作">
          <SummaryFields
            items={[
              { label: "诊断观察", value: lanes.diagnostic },
              { label: "纸面观察", value: lanes.paper },
              { label: "待复核", value: lanes.ready_for_review },
              { label: "实盘边界", value: "不在此页开放" }
            ]}
          />
          <div className="page-actions">
            <Button
              data-testid="incubation-dry-run-intent"
              icon={<ShieldAlert size={16} />}
              disabled={!controlAvailable || intentBusy}
              onClick={() => setPreviewAction("dry_run")}
            >
              创建 dry-run 意图
            </Button>
            <Button
              data-testid="incubation-run-once-intent"
              icon={<Play size={16} />}
              disabled={!controlAvailable || intentBusy}
              onClick={() => setPreviewAction("run_once")}
            >
              创建 run_once 意图
            </Button>
            <Button
              data-testid="incubation-maintenance-intent"
              icon={<ShieldAlert size={16} />}
              disabled={!controlAvailable || intentBusy}
              onClick={() => setPreviewAction("maintenance")}
            >
              创建维护意图
            </Button>
          </div>
          {previewAction ? (
            <DryRunPreview
              title="孵化工厂意图预览"
              busy={intentBusy}
              changes={[
                { label: "动作", after: previewActionLabel },
                {
                  label: "模式",
                  after: previewAction === "run_once" ? "真实 run_once（paper/observe，非实盘）" : "dry-run / 预演"
                },
                {
                  label: "门禁",
                  after: previewAction === "run_once" ? "control token + Intent confirm 后执行" : "创建意图后需在审计表确认/拒绝"
                },
                { label: "边界", after: "不触发实盘交易，不绕过 hard gate" }
              ]}
              onCancel={() => setPreviewAction(null)}
              onConfirm={() => void createIncubationIntent(previewAction)}
            />
          ) : null}
          {intentResult ? <JsonPanel data={intentResult} title="孵化工厂意图结果" /> : null}
        </Panel>
      </div>

      <Panel title="Intent / Audit 回放（incubation_factory）">
        <DataTable
          items={intentRows}
          columns={[
            { key: "id", header: "intent_id" },
            { key: "action", header: "action" },
            {
              key: "status",
              header: "status",
              render: (item) => <StatusLight status={inferStatusFromData(item)} label={String(item.status || "-")} />
            },
            { key: "updated_at", header: "updated" },
            {
              key: "ops",
              header: "ops",
              render: (item) => {
                const pending = /awaiting|pending/i.test(String(item.status || ""));
                if (!pending || !controlAvailable) return <span className="muted-value">{String(item.error || "-")}</span>;
                return (
                  <div className="page-actions">
                    <Button
                      data-testid={`incubation-intent-confirm-${item.id}`}
                      tone="success"
                      disabled={intentBusy}
                      onClick={() => void confirmIntent(String(item.id))}
                    >
                      确认
                    </Button>
                    <Button
                      data-testid={`incubation-intent-deny-${item.id}`}
                      tone="danger"
                      disabled={intentBusy}
                      onClick={() => void denyIntent(String(item.id))}
                    >
                      拒绝
                    </Button>
                  </div>
                );
              }
            }
          ]}
        />
      </Panel>

      <JsonPanel data={status.data} title="孵化工厂状态证据" />
    </PageShell>
  );
}

function FactoryEventsPage({ api, controlAvailable }: PageProps) {
  const eventList = useAsyncResource(() => api.factoryEventList({ limit: 20 }), [api]);
  const outbox = useAsyncResource(() => api.factoryEventOutboxStatus({ limit: 20 }), [api]);
  const exposure = useAsyncResource(() => api.factoryThemeExposureStatus({ limit: 20 }), [api]);
  const [eventId, setEventId] = useState("evt_mock_001");
  const [theme, setTheme] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [previewIntent, setPreviewIntent] = useState(false);
  const eventData = unwrapEnvelopeData(eventList.data);
  const outboxData = unwrapEnvelopeData(outbox.data);
  const exposureData = unwrapEnvelopeData(exposure.data);
  const eventRows = rowsFrom(eventData, ["events", "items", "data"]);
  const exposureRows = rowsFrom(exposureData, ["themes", "items", "data"]);

  async function refreshAll() {
    await Promise.all([eventList.reload(), outbox.reload(), exposure.reload()]);
  }

  async function previewTasks() {
    setResult(await api.factoryEventPreviewTasks(eventId, 20));
  }

  async function loadLineage() {
    setResult(await api.factoryEventLineage({ event_id: eventId, limit: 20 }));
  }

  async function refreshTheme() {
    setResult(await api.factoryThemeExposureStatus({ theme: theme || undefined, limit: 20 }));
    await exposure.reload();
  }

  async function createEventIntent() {
    const eventTheme = theme || "desktop_probe";
    setResult(
      await api.createIntent({
        title: "工厂事件 bootstrap dry-run",
        action: "strategy_manager.factory_event_bootstrap",
        params: {
          dry_run: true,
          source: "desktop_factory_events",
          event_type: "desktop_probe",
          theme: eventTheme,
          payload: { theme: eventTheme, reason: "desktop controlled preview" }
        },
        rationale: "Desktop 工厂事件受控预演"
      })
    );
    setPreviewIntent(false);
  }

  return (
    <PageShell
      title="工厂事件"
      description="通过 Agent 只读 facade 查看工厂事件列表、任务预览、血缘、主题暴露和 outbox；事件写入只创建受控 dry-run 意图。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="创建工厂事件意图" />}
      actions={
        <Button data-testid="factory-events-refresh" icon={<RefreshCw size={16} />} onClick={() => void refreshAll()}>
          刷新事件证据
        </Button>
      }
      metrics={[
        metric("事件数", eventRows.length || eventData.count || 0, "info"),
        metric("Outbox", outboxData.status || "-", statusTone(outboxData.status)),
        metric("待发送", outboxData.pending_count ?? outboxData.pending ?? "-", "warning"),
        metric("主题", exposureRows.length || exposureData.count || 0, "success")
      ]}
    >
      <div className="grid-2">
        <Panel title="事件列表">
          {eventList.loading ? <SharedEmptyState title="加载中..." detail="正在读取工厂事件列表。" /> : null}
          {eventList.error ? <SharedErrorState error={eventList.error} onRetry={() => void eventList.reload()} /> : null}
          {!eventList.loading && !eventList.error ? (
            <DataTable
              items={eventRows}
              columns={[
                {
                  key: "event_id",
                  header: "事件",
                  render: (item) => (
                    <button
                      type="button"
                      className="table-link-button"
                      data-testid={`factory-event-${valueOf(item, ["event_id", "id"], "unknown")}`}
                      onClick={() => setEventId(valueOf(item, ["event_id", "id"], ""))}
                    >
                      {valueOf(item, ["event_id", "id"], "-")}
                    </button>
                  )
                },
                { key: "event_type", header: "类型", render: (item) => valueOf(item, ["event_type", "type"], "-") },
                { key: "source", header: "来源", render: (item) => valueOf(item, ["source"], "-") },
                { key: "status", header: "状态", render: (item) => <StatusLight status={inferStatusFromData(item)} label={valueOf(item, ["status"])} /> }
              ]}
              empty="暂无工厂事件"
              mobileCard={(item) => ({
                title: valueOf(item, ["event_id", "id"], "事件"),
                subtitle: valueOf(item, ["event_type", "type"], "-"),
                details: [
                  { label: "来源", value: valueOf(item, ["source"], "-") },
                  { label: "状态", value: valueOf(item, ["status"], "-") }
                ]
              })}
            />
          ) : null}
        </Panel>

        <Panel title="事件只读操作">
          <div className="form-grid">
            <label className="field">
              <span>事件 ID</span>
              <input data-testid="factory-event-id" value={eventId} onChange={(event) => setEventId(event.target.value)} />
            </label>
            <label className="field">
              <span>主题</span>
              <input data-testid="factory-event-theme" value={theme} onChange={(event) => setTheme(event.target.value)} placeholder="可选" />
            </label>
          </div>
          <div className="page-actions">
            <Button data-testid="factory-event-preview-tasks" icon={<Search size={16} />} disabled={!eventId} onClick={() => void previewTasks()}>
              预览任务
            </Button>
            <Button data-testid="factory-event-lineage" icon={<Search size={16} />} disabled={!eventId} onClick={() => void loadLineage()}>
              查看血缘
            </Button>
            <Button data-testid="factory-theme-refresh" icon={<RefreshCw size={16} />} onClick={() => void refreshTheme()}>
              查询主题暴露
            </Button>
            <Button data-testid="factory-event-intent" icon={<ShieldAlert size={16} />} disabled={!controlAvailable} onClick={() => setPreviewIntent(true)}>
              创建事件意图
            </Button>
          </div>
          {previewIntent ? (
            <DryRunPreview
              title="工厂事件意图预览"
              changes={[
                { label: "动作", after: "strategy_manager.factory_event_bootstrap" },
                { label: "模式", after: "dry-run / 预演" },
                { label: "主题", after: theme || "desktop_probe" }
              ]}
              onCancel={() => setPreviewIntent(false)}
              onConfirm={() => void createEventIntent()}
            />
          ) : null}
          {result ? <JsonPanel data={result} title="事件操作结果" /> : null}
        </Panel>
      </div>

      <div className="grid-2">
        <Panel title="主题暴露">
          <DataTable
            items={exposureRows}
            columns={[
              { key: "theme", header: "主题", render: (item) => valueOf(item, ["theme", "name"], "-") },
              { key: "exposure", header: "暴露", render: (item) => valueOf(item, ["exposure", "weight"], "-") },
              { key: "strategy_count", header: "策略数", render: (item) => valueOf(item, ["strategy_count", "count"], "-") },
              { key: "risk", header: "风险", render: (item) => valueOf(item, ["risk", "risk_level"], "-") }
            ]}
            empty="暂无主题暴露"
          />
        </Panel>
        <Panel title="Outbox 状态">
          <SummaryFields
            items={[
              { label: "状态", value: outboxData.status },
              { label: "待发送", value: outboxData.pending_count ?? outboxData.pending },
              { label: "失败", value: outboxData.failed_count ?? outboxData.failed },
              { label: "最近 drain", value: outboxData.last_drain_at },
              { label: "dry-run", value: outboxData.dry_run_supported },
              { label: "只读级别", value: sideEffectLevel(outbox.data) }
            ]}
          />
        </Panel>
      </div>

      <JsonPanel data={{ events: eventList.data, outbox: outbox.data, exposure: exposure.data, result }} title="工厂事件证据" />
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
      title="金融管理与券商只读"
      description="统一承接 manager catalog、status、只读 query、受控 intent 与 broker 只读信息，不暴露交易按钮。"
      badge={<GatedNotice controlAvailable={controlAvailable} action="受控金融意图" />}
      metrics={[
        metric("管理器", statusData.ready ? "就绪" : "降级", statusData.ready ? "success" : "warning"),
        metric("券商", brokerData.read_only ? "只读" : "阻止", brokerData.read_only ? "info" : "warning"),
        metric("实盘交易", brokerData.live_trading_enabled ? "已启用" : "未启用", brokerData.live_trading_enabled ? "danger" : "success"),
        metric("目录", list(catalog.data).length, "info")
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
              券商分析预演
            </Button>
            <Button data-testid="broker-analytics-latest" disabled={!controlAvailable} onClick={() => void loadBrokerAnalytics()}>
              最新券商分析
            </Button>
          </div>

          {previewAction ? (
            <DryRunPreview
              title={previewAction === "intent" ? "金融意图预览" : "券商分析预演"}
              changes={[
                { label: "动作", after: previewAction === "intent" ? "portfolio_manager.create" : "broker.analytics.run" },
                { label: "模式", after: "只读 / 预演" },
                { label: "说明", after: query }
              ]}
              onCancel={() => setPreviewAction(null)}
              onConfirm={() => void (previewAction === "intent" ? createIntent() : runBrokerAnalytics())}
            />
          ) : null}
        </Panel>

        <Panel title="目录">
          <DataTable items={list(catalog.data)} columns={[{ key: "name", header: "能力" }, { key: "side_effect", header: "副作用" }]} />
        </Panel>
      </div>

      <Panel title="我的实际情况">
        <div className="grid-2">
          <div>
            <h3 style={{ marginBottom: 12 }}>账户</h3>
            <DataTable items={accountRows} columns={[{ key: "provider", header: "供应方" }, { key: "account_id", header: "账户" }, { key: "read_only", header: "只读" }]} />
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
