import { AlertTriangle, BarChart3, BriefcaseBusiness, Landmark, Play, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  FinancialManagerAction,
  FinancialManagerCatalog,
  FinancialManagerIntentResult,
  FinancialManagerQueryResult,
  FinancialManagerStatus
} from "../../types";
import { actionKey, groupLabel, modeLabel, safeJsonParse, statusDescription } from "./financialManagerUi";

export function FinancialManagerWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
}) {
  const client = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [catalog, setCatalog] = useState<FinancialManagerCatalog | null>(null);
  const [status, setStatus] = useState<FinancialManagerStatus | null>(null);
  const [activeGroup, setActiveGroup] = useState("overview");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [modeFilter, setModeFilter] = useState("all");
  const [selectedKey, setSelectedKey] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [rationale, setRationale] = useState("Financial Manager Desktop review");
  const [result, setResult] = useState<FinancialManagerQueryResult | FinancialManagerIntentResult | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  const groups = catalog?.groups || [];
  const actions = catalog?.actions || [];
  const selectedAction = actions.find((item) => actionKey(item) === selectedKey) || null;
  const statusOptions = Array.from(new Set(actions.map((item) => item.status || "unknown"))).sort();
  const modeOptions = Array.from(new Set(actions.map((item) => item.mode || "unknown"))).sort();
  const unmappedGroups = ["decision", "fundamental", "macro", "alerts", "limit-up"]
    .map((id) => groups.find((group) => group.id === id))
    .filter(Boolean);
  const visibleActions = (activeGroup === "overview" ? actions : actions.filter((item) => item.group === activeGroup))
    .filter((item) => {
      const haystack = `${item.label} ${item.capability_id} ${item.action_id} ${item.group} ${item.tool || ""} ${item.mcp_tool || ""} ${item.intent_action || ""}`.toLowerCase();
      const matchesQuery = !query.trim() || haystack.includes(query.trim().toLowerCase());
      const matchesStatus = statusFilter === "all" || (item.status || "unknown") === statusFilter;
      const matchesMode = modeFilter === "all" || (item.mode || "unknown") === modeFilter;
      return matchesQuery && matchesStatus && matchesMode;
    })
    .slice(0, activeGroup === "overview" && !query.trim() && statusFilter === "all" && modeFilter === "all" ? 12 : undefined);

  async function refresh() {
    setBusy(true);
    try {
      const [nextCatalog, nextStatus] = await Promise.all([client.financialManagerCatalog(), client.financialManagerStatus()]);
      setCatalog(nextCatalog);
      setStatus(nextStatus);
      const nextAction = nextCatalog.actions.find((item) => item.mode === "read_only" && item.available) || nextCatalog.actions[0];
      if (nextAction && !selectedKey) {
        setSelectedKey(actionKey(nextAction));
        setParamsText(JSON.stringify(nextAction.default_params || {}, null, 2));
      }
      setMessage("FINANCIAL_MANAGER_READY");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint, apiToken, controlToken]);

  function selectAction(action: FinancialManagerAction) {
    setSelectedKey(actionKey(action));
    setParamsText(JSON.stringify(action.default_params || {}, null, 2));
    setResult(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedAction) return;
    setBusy(true);
    try {
      const params = safeJsonParse(paramsText);
      const payload = {
        capability_id: selectedAction.capability_id,
        action_id: selectedAction.action_id,
        params
      };
      const response =
        selectedAction.mode === "stateful_intent"
          ? await client.financialManagerIntent({ ...payload, rationale, user_id: userId })
          : await client.financialManagerQuery(payload);
      setResult(response);
      setMessage(response.success ? "FINANCIAL_ACTION_OK" : response.error_code || response.error || "FINANCIAL_ACTION_FAILED");
      if (selectedAction.mode === "stateful_intent") await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="capabilities-workspace financial-manager-workspace">
      <header className="capabilities-header">
        <div>
          <span>Financial Manager</span>
          <h1>金融经理台</h1>
          <p>组合、风控、研究、量化、纸上交易和券商只读连接统一进入 Agent 安全网关。</p>
        </div>
        <div className="button-row">
          <StatusBadge status={status?.status || message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="diagnostics-summary wide">
            <MetricCard label="Ready" value={catalog?.summary?.ready ?? 0} status="ready" />
            <MetricCard label="Intent" value={catalog?.summary?.intent_ready ?? 0} status="partial" />
            <MetricCard label="Blocked" value={catalog?.summary?.blocked ?? 0} status="blocked" />
            <MetricCard label="Live Trading" value={status?.broker?.live_trading_enabled ? "enabled" : "disabled"} status="not_required" />
          </div>

          <section className="capability-section compact-section">
            <div className="section-header">
              <div>
                <span>{actions.length} 个后端动作</span>
                <h3>搜索与状态过滤</h3>
              </div>
              <Search size={18} />
            </div>
            <label className="search-field">
              <Search size={15} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索能力、工具、action 或 group" />
            </label>
            <div className="filter-row tool-filter-row">
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">全部状态</option>
                {statusOptions.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
              <select value={modeFilter} onChange={(event) => setModeFilter(event.target.value)}>
                <option value="all">全部模式</option>
                {modeOptions.map((item) => <option key={item} value={item}>{modeLabel(item)}</option>)}
              </select>
            </div>
            {!!unmappedGroups.length && (
              <div className="notice info compact">
                <ShieldCheck size={14} />
                这些后端能力已有专门入口，也仍可在这里动态运行：{unmappedGroups.map((group) => group?.label || group?.id).join("、")}。
              </div>
            )}
          </section>

          <div className="financial-manager-grid">
            <aside className="financial-manager-side">
              <button className={activeGroup === "overview" ? "active" : ""} onClick={() => setActiveGroup("overview")} type="button">
                <Landmark size={16} />
                总览
              </button>
              {groups
                .filter((group) => group.id !== "overview")
                .map((group) => (
                  <button className={activeGroup === group.id ? "active" : ""} key={group.id} onClick={() => setActiveGroup(group.id)} type="button">
                    <BriefcaseBusiness size={16} />
                    {groupLabel(group, group.id)}
                  </button>
                ))}
            </aside>

            <section className="financial-manager-main">
              {activeGroup === "overview" && (
                <div className="capability-section">
                  <div className="section-header">
                    <div>
                      <span>安全边界</span>
                      <h3>只读查询 + ActionIntent</h3>
                    </div>
                    <ShieldCheck size={18} />
                  </div>
                  <div className="notice warn">
                    <AlertTriangle size={14} />
                    真实 live 下单和撤单在 V1 中固定禁用；券商区域只展示账户、持仓、订单、成交等只读查询。
                  </div>
                  <JsonPanel value={{ safety: catalog?.safety, broker: status?.broker, mcp: status?.mcp }} />
                </div>
              )}

              <div className="financial-action-list">
                {visibleActions.map((action) => (
                  <button className={selectedKey === actionKey(action) ? "active" : ""} key={actionKey(action)} onClick={() => selectAction(action)} type="button">
                    <div>
                      <strong>{action.label}</strong>
                      <span>{action.capability_id} / {action.action_id}</span>
                    </div>
                    <StatusBadge status={action.status || action.mode} label={modeLabel(action.mode)} />
                  </button>
                ))}
              </div>

              <form className="financial-action-runner" onSubmit={submit}>
                <div className="section-header">
                <div>
                  <span>{selectedAction ? `${selectedAction.capability_id}.${selectedAction.action_id}` : "未选择"}</span>
                  <h3>{selectedAction?.label || "选择一个动作"}</h3>
                </div>
                <StatusBadge status={selectedAction?.status || "not_loaded"} />
              </div>
                <div className={`notice ${selectedAction?.available === false || selectedAction?.mode === "blocked" ? "warn" : "info"} compact`}>
                  <ShieldCheck size={14} />
                  {statusDescription(selectedAction)}
                </div>
                <textarea aria-label="financial action params" value={paramsText} onChange={(event) => setParamsText(event.target.value)} rows={8} />
                {selectedAction?.mode === "stateful_intent" && (
                  <input aria-label="financial action rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />
                )}
                <button className="primary-button" disabled={busy || !selectedAction || selectedAction.mode === "blocked"} type="submit">
                  {selectedAction?.mode === "stateful_intent" ? <ShieldCheck size={15} /> : <Play size={15} />}
                  {selectedAction?.mode === "stateful_intent" ? "创建意图" : "运行查询"}
                </button>
                {selectedAction?.mode === "blocked" && <p className="muted">{selectedAction.blocked_reason || "该动作在当前版本禁用。"}</p>}
              </form>

              <section className="capability-section">
                <div className="section-header">
                  <div>
                    <span>{message}</span>
                    <h3>结果</h3>
                  </div>
                  <BarChart3 size={18} />
                </div>
                <JsonPanel value={result || { status: message, selected: selectedAction ? compact(selectedAction) : null }} />
              </section>
            </section>
          </div>
        </div>
      </div>
    </section>
  );
}
