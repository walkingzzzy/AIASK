import { BarChart3, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, MetricCard, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type {
  FinancialManagerAction,
  FinancialManagerCatalog,
  FinancialManagerIntentResult,
  FinancialManagerQueryResult
} from "../../types";
import { actionKey, modeLabel, safeJsonParse, seedParams, statusDescription } from "./financialManagerUi";

export interface FinancialCapabilityDefinition {
  capability_id: string;
  action_id: string;
  label: string;
  description?: string;
}

export interface FinancialCapabilityWorkspaceProps {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  userId?: string;
  eyebrow: string;
  title: string;
  description: string;
  actions: FinancialCapabilityDefinition[];
}

function definitionKey(definition: FinancialCapabilityDefinition) {
  return `${definition.capability_id}::${definition.action_id}`;
}

function displayActions(catalog: FinancialManagerCatalog | null, definitions: FinancialCapabilityDefinition[]) {
  const byKey = new Map((catalog?.actions || []).map((action) => [actionKey(action), action]));
  return definitions.map((definition) => ({
    definition,
    action: byKey.get(definitionKey(definition)) || null
  }));
}

export function FinancialCapabilityWorkspace({
  endpoint,
  apiToken,
  controlToken,
  userId,
  eyebrow,
  title,
  description,
  actions: definitions
}: FinancialCapabilityWorkspaceProps) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [catalog, setCatalog] = useState<FinancialManagerCatalog | null>(null);
  const [selectedKey, setSelectedKey] = useState(definitionKey(definitions[0]));
  const [paramsText, setParamsText] = useState("{}");
  const [rationale, setRationale] = useState(`${title} Desktop review`);
  const [result, setResult] = useState<FinancialManagerQueryResult | FinancialManagerIntentResult | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => displayActions(catalog, definitions), [catalog, definitions]);
  const selectedRow = rows.find((row) => definitionKey(row.definition) === selectedKey) || rows[0];
  const selectedAction = selectedRow?.action || null;
  const readyCount = rows.filter((row) => row.action?.status === "ready" || row.action?.status === "intent_ready").length;
  const missingCount = rows.filter((row) => !row.action || String(row.action.status || "").startsWith("missing")).length;
  const blockedCount = rows.filter((row) => row.action?.mode === "blocked" || row.action?.status === "blocked").length;

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.financialManagerCatalog();
      setCatalog(payload);
      const firstAvailable = definitions
        .map((definition) => payload.actions.find((action) => actionKey(action) === definitionKey(definition)))
        .find(Boolean);
      const nextSelected = firstAvailable || selectedAction;
      if (nextSelected) {
        setSelectedKey(actionKey(nextSelected));
        setParamsText(seedParams(nextSelected));
      }
      setMessage("FINANCIAL_CAPABILITY_READY");
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

  function selectAction(action: FinancialManagerAction | null, fallback: FinancialCapabilityDefinition) {
    setSelectedKey(action ? actionKey(action) : definitionKey(fallback));
    setParamsText(seedParams(action));
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
          ? await api.financialManagerIntent({ ...payload, rationale, user_id: userId })
          : await api.financialManagerQuery(payload);
      setResult(response);
      setMessage(response.success ? "FINANCIAL_ACTION_OK" : response.error_code || response.error || "FINANCIAL_ACTION_FAILED");
    } catch (error) {
      setMessage(error instanceof SyntaxError ? "FINANCIAL_PARAMS_JSON_INVALID" : formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>{eyebrow}</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <div className="button-row">
          <StatusBadge status={message.startsWith("AIASK_") ? message : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="diagnostics-summary wide">
            <MetricCard label="动作" value={rows.length} status="ready" />
            <MetricCard label="可用" value={readyCount} status={readyCount ? "ready" : "not_loaded"} />
            <MetricCard label="缺失" value={missingCount} status={missingCount ? "partial" : "ready"} />
            <MetricCard label="禁用" value={blockedCount} status={blockedCount ? "blocked" : "ready"} />
          </div>

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>能力动作</span>
                  <h3>后端 catalog 映射</h3>
                </div>
                <BarChart3 size={18} />
              </div>
              <div className="financial-action-list">
                {rows.map((row) => {
                  const key = row.action ? actionKey(row.action) : definitionKey(row.definition);
                  return (
                    <button className={selectedKey === key ? "active" : ""} key={key} onClick={() => selectAction(row.action, row.definition)} type="button">
                      <div>
                        <strong>{row.action?.label || row.definition.label}</strong>
                        <span>{row.definition.capability_id} / {row.definition.action_id}</span>
                      </div>
                      <StatusBadge status={row.action?.status || "missing_catalog"} label={modeLabel(row.action?.mode)} />
                    </button>
                  );
                })}
              </div>
            </div>

            <form className="financial-action-runner" onSubmit={submit}>
              <div className="section-header">
                <div>
                  <span>{selectedAction ? `${selectedAction.capability_id}.${selectedAction.action_id}` : "catalog missing"}</span>
                  <h3>{selectedAction?.label || selectedRow?.definition.label || "未选择"}</h3>
                </div>
                <StatusBadge status={selectedAction?.status || "missing_catalog"} />
              </div>
              <p className="muted">{selectedRow?.definition.description || statusDescription(selectedAction)}</p>
              <div className={`notice ${selectedAction?.available === false || !selectedAction ? "warn" : "info"} compact`}>
                <ShieldCheck size={14} />
                {statusDescription(selectedAction)}
              </div>
              <textarea aria-label={`${title} params`} value={paramsText} onChange={(event) => setParamsText(event.target.value)} rows={8} />
              {selectedAction?.mode === "stateful_intent" && (
                <input aria-label={`${title} rationale`} value={rationale} onChange={(event) => setRationale(event.target.value)} />
              )}
              <button className="primary-button" disabled={busy || !selectedAction || selectedAction.mode === "blocked"} type="submit">
                <Play size={15} />
                {selectedAction?.mode === "stateful_intent" ? "创建意图" : "运行查询"}
              </button>
            </form>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{message}</span>
                <h3>结果与原始数据</h3>
              </div>
              <StatusBadge status={result?.success ? "ready" : result ? "failed" : "not_loaded"} />
            </div>
            <JsonPanel value={result || { status: message, selected: selectedAction ? compact(selectedAction) : selectedRow?.definition }} />
          </section>
        </div>
      </div>
    </section>
  );
}
