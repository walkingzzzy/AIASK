import { AlertTriangle, BarChart3, BriefcaseBusiness, Landmark, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  FinancialManagerAction,
  FinancialManagerCatalog,
  FinancialManagerGroup,
  FinancialManagerIntentResult,
  FinancialManagerQueryResult,
  FinancialManagerStatus
} from "../../types";

function safeJsonParse(value: string): Record<string, unknown> {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
}

function actionKey(action: FinancialManagerAction): string {
  return `${action.capability_id}::${action.action_id}`;
}

function modeLabel(mode?: string) {
  if (mode === "read_only") return "只读";
  if (mode === "stateful_intent") return "意图";
  if (mode === "blocked") return "禁用";
  return mode || "unknown";
}

function groupLabel(group: FinancialManagerGroup | undefined, fallback: string) {
  return group?.label || fallback.replace(/-/g, " ");
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function actionAvailability(action?: FinancialManagerAction | null): Record<string, unknown> | null {
  return objectRecord(action?.availability);
}

function resultAvailability(result?: FinancialManagerQueryResult | FinancialManagerIntentResult | null): Record<string, unknown> | null {
  const data = objectRecord(result?.data);
  return objectRecord(data?.availability);
}

function availabilityExplanation(reason?: unknown): string {
  const code = String(reason || "");
  if (code === "agent_tool_ready" || code === "agent_mcp_wrapped_tool_ready") return "可运行";
  if (code === "mcp_tool_discovered_but_agent_registry_not_refreshed") return "MCP 工具已发现，但 Agent 工具注册表尚未刷新";
  if (code === "no_financial_mcp_server_registered") return "未发现已注册的金融 MCP server";
  if (code === "mcp_tool_not_discovered") return "金融 MCP server 未提供目标工具";
  if (code === "agent_tool_missing" || code === "action_intent_tool_missing") return "Agent 工具注册表缺少目标工具";
  if (code === "action_intent_ready") return "需要通过 ActionIntent 审批路径执行";
  if (code === "blocked") return "高风险动作已阻断";
  return code || "可用性状态";
}

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
  const [selectedKey, setSelectedKey] = useState("");
  const [paramsText, setParamsText] = useState("{}");
  const [rationale, setRationale] = useState("Financial Manager Desktop review");
  const [result, setResult] = useState<FinancialManagerQueryResult | FinancialManagerIntentResult | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  const groups = catalog?.groups || [];
  const actions = catalog?.actions || [];
  const selectedAction = actions.find((item) => actionKey(item) === selectedKey) || null;
  const visibleActions = activeGroup === "overview" ? actions.slice(0, 8) : actions.filter((item) => item.group === activeGroup);
  const selectedAvailability = actionAvailability(selectedAction);
  const resultAvailabilityDetail = resultAvailability(result);

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
                <textarea aria-label="financial action params" value={paramsText} onChange={(event) => setParamsText(event.target.value)} rows={8} />
                {selectedAvailability && (
                  <div className="notice">
                    <strong>{availabilityExplanation(selectedAvailability.reason_code)} ({String(selectedAvailability.reason_code || selectedAction?.status || "availability")})</strong>
                    <span>{compact(selectedAvailability)}</span>
                  </div>
                )}
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
                {resultAvailabilityDetail && (
                  <div className="notice warn">
                    <strong>{availabilityExplanation(resultAvailabilityDetail.reason_code)} ({String(resultAvailabilityDetail.reason_code || result?.error_code || "availability")})</strong>
                    <span>{compact(resultAvailabilityDetail)}</span>
                  </div>
                )}
                <JsonPanel value={result || { status: message, selected: selectedAction ? compact(selectedAction) : null }} />
              </section>
            </section>
          </div>
        </div>
      </div>
    </section>
  );
}
