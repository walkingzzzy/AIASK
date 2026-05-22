import {
  ChevronDown,
  ClipboardList,
  Eye,
  Play,
  Search,
  ShieldCheck,
  XCircle,
  Zap
} from "lucide-react";
import { useMemo, useState } from "react";
import { formatApiError } from "../api";
import { AiaskApi } from "../services/aiaskApi";
import type {
  IntentRecord,
  ToolCatalogItem,
  ToolEnvelope
} from "../types";
import { compact, JsonPanel, StatusBadge } from "./shared";

function contractChips(tool: ToolCatalogItem): string[] {
  const chips: string[] = [];
  if (tool.contract_source) chips.push(`contract ${tool.contract_source}`);
  else if (tool.contract_version) chips.push(`contract ${tool.contract_version}`);
  if (tool.standard_model) chips.push(`model ${tool.standard_model}`);
  const freshness = typeof tool.freshness?.expectation === "string" ? tool.freshness.expectation : undefined;
  if (freshness) chips.push(`freshness ${freshness}`);
  const priority = tool.source_policy?.priority;
  if (Array.isArray(priority) && priority.length) chips.push(`source ${priority.slice(0, 3).join(" > ")}`);
  const gateStatus = typeof tool.quality_gate?.status === "string" ? tool.quality_gate.status : undefined;
  const gateMode = typeof tool.quality_gate?.mode === "string" ? tool.quality_gate.mode : undefined;
  if (gateStatus || gateMode) chips.push(`quality ${[gateStatus, gateMode].filter(Boolean).join(" ")}`);
  if (Array.isArray(tool.provider_choices) && tool.provider_choices.length) chips.push(`providers ${tool.provider_choices.length}`);
  return chips;
}

function contractDetails(tool: ToolCatalogItem): Record<string, unknown> {
  return {
    standard_model: tool.standard_model,
    input_schema: tool.input_schema,
    output_schema: tool.output_schema,
    freshness: tool.freshness,
    source_policy: tool.source_policy,
    provider_choices: tool.provider_choices,
    provider_status: tool.provider_status,
    quality_gate: tool.quality_gate,
    reconciliation: tool.reconciliation,
    form_schema: tool.form_schema,
    examples: tool.examples,
    contract_version: tool.contract_version,
    contract_source: tool.contract_source
  };
}

function hasContractDetails(tool: ToolCatalogItem): boolean {
  return Boolean(
    tool.input_schema ||
      tool.output_schema ||
      tool.examples?.length ||
      tool.source_policy ||
      tool.freshness ||
      tool.standard_model ||
      tool.provider_choices?.length ||
      tool.provider_status ||
      tool.quality_gate ||
      tool.reconciliation ||
      tool.form_schema
  );
}

function contractSearchText(tool: ToolCatalogItem): string {
  const parts = [
    tool.standard_model,
    tool.contract_source,
    tool.contract_version,
    tool.freshness,
    tool.source_policy,
    tool.provider_choices,
    tool.provider_status,
    tool.quality_gate,
    tool.reconciliation,
    tool.form_schema,
    tool.examples
  ];
  return parts
    .map((part) => {
      if (!part) return "";
      if (typeof part === "string") return part;
      try {
        return JSON.stringify(part);
      } catch {
        return "";
      }
    })
    .join(" ");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function formSchemaFor(tool: ToolCatalogItem): Record<string, unknown> | null {
  if (isRecord(tool.form_schema)) return tool.form_schema;
  if (isRecord(tool.input_schema)) return tool.input_schema;
  return null;
}

function formFields(tool: ToolCatalogItem): [string, Record<string, unknown>][] {
  const schema = formSchemaFor(tool);
  const properties = isRecord(schema?.properties) ? schema.properties : {};
  return Object.entries(properties)
    .filter((entry): entry is [string, Record<string, unknown>] => isRecord(entry[1]))
    .slice(0, 8);
}

function exampleArguments(tool: ToolCatalogItem): Record<string, unknown> {
  const formExamples = isRecord(tool.form_schema) && Array.isArray(tool.form_schema.examples) ? tool.form_schema.examples : [];
  const firstFormExample = formExamples.find(isRecord);
  if (firstFormExample) return firstFormExample;
  const firstCatalogExample = Array.isArray(tool.examples) ? tool.examples.find(isRecord) : null;
  const args = isRecord(firstCatalogExample?.arguments) ? firstCatalogExample.arguments : {};
  return { ...args };
}

function fallbackExampleArguments(tool: ToolCatalogItem): Record<string, unknown> {
  const existing = exampleArguments(tool);
  if (Object.keys(existing).length) return existing;
  const name = tool.name;
  if (name === "agent_analyze_stock") return { code: "600519", include_decision: false };
  if (name === "agent_data_validation") return { action: "backend", records: [], expectations: {} };
  if (name === "agent_quant_data_gate") return { codes: ["600519", "000001"], max_stale_days: 5 };
  if (name === "agent_factor_validation") return { codes: ["600519", "000001"], factors: ["momentum"], period: 20, groups: 5 };
  if (name === "agent_backtest_suite") return { codes: ["600519", "000001"], strategy: "ma_cross", benchmark: "000300" };
  if (name === "agent_portfolio_risk") return { codes: ["600519", "000001"], weights: [0.5, 0.5], method: "equal_weight" };
  if (name === "agent_factory_status") return { recent_run_limit: 3 };
  if (name === "agent_factory_runs") return { limit: 5 };
  if (name === "agent_strategy_review_snapshot") return { limit: 10 };
  if (name === "agent_strategy_domain_events") return { limit: 10 };
  if (name === "agent_incubation_factory_status") return {};
  if (name === "agent_memory_search") return { query: "AIASK", limit: 10 };
  if (name === "agent_session_search") return { query: "AIASK", limit: 10 };
  if (name === "agent_tool_catalog") return {};
  if (name === "agent_file_list") return { path: ".", recursive: false, limit: 20 };
  if (name === "agent_file_read") return { path: "README.md", max_bytes: 2000 };
  if (name === "agent_file_search") return { path: ".", query: "AIASK", limit: 20 };
  if (name === "agent_browser_snapshot") return {};
  if (name === "agent_browser_extract") return { selector: "body" };
  if (name === "agent_browser_console") return { limit: 50 };
  if (name === "agent_browser_get_images") return { limit: 10 };
  if (name === "agent_browser_vision") return { prompt: "Describe the current browser page." };
  if (name === "agent_web_search") return { query: "AIASK", limit: 5 };
  if (name === "agent_web_extract") return { url: "https://example.com", max_chars: 2000 };
  if (name === "agent_skill_list") return {};
  if (name === "agent_skill_view") return { name: "aiask-desktop-workbench", max_chars: 2000 };
  if (name === "agent_plugin_list") return {};
  if (name === "agent_mcp_manage") return { action: "servers" };
  if (name === "agent_model_manage") return { action: "status" };
  if (name === "agent_memory_manage") return { action: "status" };
  if (name === "agent_acp_manage") return { action: "status" };
  if (name === "agent_security_scan") return { text: "AIASK_SECRET=redacted" };
  if (name === "agent_gateway_status") return {};
  if (name === "agent_gateway_platforms") return {};
  if (name === "agent_gateway_history") return { limit: 20 };
  if (name === "agent_gateway_pairing") return { action: "status" };
  if (name === "agent_gateway_directory") return { action: "list", limit: 20 };
  if (name === "agent_learning_status") return {};
  if (name === "agent_learning_review") return { limit: 20 };
  if (name === "agent_ha_list_entities") return {};
  if (name === "agent_ha_get_state") return { entity_id: "sensor.aiask" };
  if (name === "agent_ha_list_services") return {};
  if (name === "agent_ha_list_events") return {};
  if (name === "agent_ha_list_registry") return { kind: "entity" };
  if (name === "agent_rl_list_environments") return {};
  if (name === "agent_rl_get_config") return {};
  if (name === "agent_rl_list_runs") return { limit: 20 };
  if (name === "agent_job_list") return {};
  if (name === "agent_todo_list") return {};
  if (name === "agent_todo") return { action: "list" };
  if (name === "agent_subgoal") return { action: "status" };
  return {};
}

function inputTypeFor(schema: Record<string, unknown>): "checkbox" | "number" | "text" {
  const type = schema.type;
  if (type === "boolean") return "checkbox";
  if (type === "number" || type === "integer") return "number";
  return "text";
}

function displayValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function sideEffectLabel(tool: ToolCatalogItem): string {
  const sideEffect = tool.side_effect;
  if (typeof sideEffect === "string") return sideEffect || "unknown";
  if (isRecord(sideEffect) && typeof sideEffect.level === "string") return sideEffect.level || "unknown";
  return "unknown";
}

function isReadOnlyTool(tool: ToolCatalogItem): boolean {
  return sideEffectLabel(tool) === "read_only";
}

function sideEffectTarget(tool: ToolCatalogItem): string {
  const sideEffect = tool.side_effect;
  if (isRecord(sideEffect) && typeof sideEffect.target === "string") return sideEffect.target;
  return "";
}

export function ToolCatalog({
  apiToken = "",
  controlToken = "",
  endpoint = "http://127.0.0.1:8767",
  tools,
  hermesTools
}: {
  apiToken?: string;
  controlToken?: string;
  endpoint?: string;
  tools: ToolCatalogItem[];
  hermesTools: ToolCatalogItem[];
}) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [sideEffect, setSideEffect] = useState("all");
  const [formDrafts, setFormDrafts] = useState<Record<string, Record<string, unknown>>>({});
  const [probeResult, setProbeResult] = useState<Record<string, unknown>>({ status: "no_probe_run" });
  const [probeMessage, setProbeMessage] = useState("NO_PROBE");
  const [busyTool, setBusyTool] = useState("");
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const allTools = useMemo(
    () => [...tools, ...hermesTools.filter((tool) => !tools.some((item) => item.name === tool.name))],
    [hermesTools, tools]
  );
  const financeToolNames = useMemo(() => new Set(tools.map((tool) => tool.name)), [tools]);
  const categories = useMemo(
    () => Array.from(new Set(allTools.map((tool) => tool.category || tool.capability || "tool"))).sort(),
    [allTools]
  );
  const sideEffects = useMemo(
    () => Array.from(new Set(allTools.map(sideEffectLabel))).sort(),
    [allTools]
  );
  const toolStatus = useMemo(
    () => Array.from(new Set(allTools.map((tool) => tool.status || (isReadOnlyTool(tool) ? "ready" : "gated")))).sort(),
    [allTools]
  );
  const visibleTools = useMemo(
    () =>
      allTools.filter((tool) => {
        const toolSideEffect = sideEffectLabel(tool);
        const derivedStatus = tool.status || (toolSideEffect === "read_only" ? "ready" : "gated");
        const haystack = `${tool.name} ${tool.category || ""} ${tool.capability || ""} ${tool.description || ""} ${toolSideEffect} ${derivedStatus} ${contractSearchText(tool)}`.toLowerCase();
        const matchesQuery = haystack.includes(query.toLowerCase());
        const matchesCategory = category === "all" || (tool.category || tool.capability || "tool") === category;
        const matchesStatus = status === "all" || derivedStatus === status;
        const matchesSideEffect = sideEffect === "all" || toolSideEffect === sideEffect;
        return matchesQuery && matchesCategory && matchesStatus && matchesSideEffect;
      }),
    [allTools, category, query, sideEffect, status]
  );

  async function runSafeProbe(tool: ToolCatalogItem, hermesOnly: boolean) {
    const draft = formDrafts[tool.name] || fallbackExampleArguments(tool);
    setBusyTool(tool.name);
    try {
      const result = hermesOnly ? await api.hermesToolCall(tool.name, draft) : await api.readOnlyTool(tool.name, draft);
      setProbeResult({ tool: tool.name, arguments: draft, result });
      setProbeMessage(result.success ? "SAFE_PROBE_COMPLETED" : result.error || "SAFE_PROBE_FAILED");
    } catch (error) {
      setProbeResult({ tool: tool.name, arguments: draft, success: false, error: formatApiError(error) });
      setProbeMessage(formatApiError(error));
    } finally {
      setBusyTool("");
    }
  }

  return (
    <div className="inspector-scroll">
      <div className="panel-heading">
        <div>
          <span>Tools</span>
          <h2>Available actions and safe probes</h2>
        </div>
      </div>
      <div className="notice info compact">
        <ShieldCheck size={14} />
        Read-only tools can be probed from Desktop. Stateful, filesystem, terminal, messaging, and factory actions remain gated or intent-based.
      </div>
      <label className="search-field">
        <Search size={15} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tools" />
      </label>
      <div className="filter-row tool-filter-row">
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="all">all categories</option>
          {categories.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select value={status} onChange={(event) => setStatus(event.target.value)}>
          <option value="all">all status</option>
          {toolStatus.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select value={sideEffect} onChange={(event) => setSideEffect(event.target.value)}>
          <option value="all">all side effects</option>
          {sideEffects.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </div>
      <div className="tool-list">
        {visibleTools.map((tool) => {
          const chips = contractChips(tool);
          const fields = formFields(tool);
          const draft = formDrafts[tool.name] || {};
          const example = fallbackExampleArguments(tool);
          const sideEffect = sideEffectLabel(tool);
          const sideEffectTargetName = sideEffectTarget(tool);
          const readOnlyTool = sideEffect === "read_only";
          const derivedStatus = tool.status || (readOnlyTool ? "ready" : "gated");
          const hermesOnly = !financeToolNames.has(tool.name);
          const canProbe = readOnlyTool && (!hermesOnly || controlToken.trim());
          return (
            <article className="tool-row" key={tool.name}>
              <div className="tool-row-head">
                <div>
                  <strong title={tool.name}>{tool.name}</strong>
                  <span>{tool.category || tool.capability || "tool"} / {derivedStatus}</span>
                </div>
                <StatusBadge status={readOnlyTool ? "implemented" : "gated"} label={sideEffect} />
              </div>
              <p>{tool.description}</p>
              {sideEffectTargetName && <small className="tool-target">target {sideEffectTargetName}</small>}
              {!!chips.length && (
                <section className="tool-contract-meta">
                  {chips.map((chip) => (
                    <span key={`${tool.name}-${chip}`} title={chip}>{compact(chip)}</span>
                  ))}
                </section>
              )}
              {hasContractDetails(tool) && (
                <details className="raw-details tool-contract-details">
                  <summary>
                    Contract
                    <ChevronDown size={14} />
                  </summary>
                  <JsonPanel value={contractDetails(tool)} />
                </details>
              )}
              {readOnlyTool && fields.length > 0 && (
                <details className="raw-details tool-form-details">
                  <summary>
                    Parameters
                    <ChevronDown size={14} />
                  </summary>
                  <div className="tool-form-grid">
                    {fields.map(([name, schema]) => {
                      const type = inputTypeFor(schema);
                      const label = schema.title || schema.description || name;
                      return (
                        <label key={`${tool.name}-${name}`}>
                          <span>{compact(String(label))}</span>
                          <input
                            checked={type === "checkbox" ? Boolean(draft[name]) : undefined}
                            onChange={(event) =>
                              setFormDrafts((current) => ({
                                ...current,
                                [tool.name]: {
                                  ...(current[tool.name] || {}),
                                  [name]: type === "checkbox" ? event.target.checked : event.target.value
                                }
                              }))
                            }
                            placeholder={name}
                            type={type}
                            value={type === "checkbox" ? undefined : displayValue(draft[name])}
                          />
                        </label>
                      );
                    })}
                  </div>
                  <div className="button-row">
                    <button
                      onClick={() =>
                        setFormDrafts((current) => ({
                          ...current,
                          [tool.name]: example
                        }))
                      }
                      title={`Fill example for ${tool.name}`}
                      type="button"
                    >
                      <ClipboardList size={14} />
                      Fill example
                    </button>
                  </div>
                  <JsonPanel value={draft} />
                </details>
              )}
              {readOnlyTool && fields.length === 0 && Object.keys(example).length > 0 && (
                <details className="raw-details tool-form-details">
                  <summary>
                    Parameters
                    <ChevronDown size={14} />
                  </summary>
                  <div className="button-row">
                    <button
                      onClick={() =>
                        setFormDrafts((current) => ({
                          ...current,
                          [tool.name]: example
                        }))
                      }
                      title={`Fill example for ${tool.name}`}
                      type="button"
                    >
                      <ClipboardList size={14} />
                      Fill example
                    </button>
                  </div>
                  <JsonPanel value={draft} />
                </details>
              )}
              <div className="tool-probe-row">
                {readOnlyTool ? (
                  <>
                    <button className="small-button" disabled={!canProbe || busyTool === tool.name} onClick={() => runSafeProbe(tool, hermesOnly)} type="button">
                      <Play size={13} />
                      Run safe probe
                    </button>
                    <span>{hermesOnly ? "Hermes full control token required for this read-only probe." : "Uses read-only Desktop tool facade."}</span>
                  </>
                ) : (
                  <span>Stateful tool. Verify gated state or use a dedicated approval intent panel.</span>
                )}
              </div>
            </article>
          );
        })}
        {!visibleTools.length && <p className="muted">No tools match this filter.</p>}
      </div>
      <details className="raw-details" open>
        <summary>
          Last safe probe result
          <ChevronDown size={14} />
        </summary>
        <p className="status-line">{probeMessage}</p>
        <JsonPanel value={probeResult} />
      </details>
    </div>
  );
}

export function IntentsPanel({
  busy,
  controlToken,
  intentIds,
  intentIdInput,
  intentEnvelope,
  intentMessage,
  currentIntent,
  compactValue,
  onIntentInput,
  onFetchIntent,
  onUpdateIntent
}: {
  busy: boolean;
  controlToken: string;
  intentIds: string[];
  intentIdInput: string;
  intentEnvelope: ToolEnvelope | null;
  intentMessage: string;
  currentIntent: IntentRecord | null;
  compactValue: (value: unknown) => string;
  onIntentInput: (value: string) => void;
  onFetchIntent: (id?: string) => void;
  onUpdateIntent: (action: "confirm" | "deny") => void;
}) {
  return (
    <div className="inspector-scroll">
      <div className="panel-heading">
        <div>
          <span>Review</span>
          <h2>Approvals and intents</h2>
        </div>
      </div>
      <div className="inline-form">
        <input value={intentIdInput} onChange={(event) => onIntentInput(event.target.value)} placeholder="intent_..." />
        <button disabled={busy || !intentIdInput.trim()} onClick={() => onFetchIntent()} title="Load intent" type="button">
          <Eye size={14} />
          Load
        </button>
      </div>

      <div className="thread-list compact">
        {intentIds.map((id) => (
          <button className={id === currentIntent?.intent_id ? "active" : ""} key={id} onClick={() => onFetchIntent(id)} title={`Load ${id}`} type="button">
            <span>{id}</span>
            <strong>{id === currentIntent?.intent_id ? currentIntent.status : "Cached intent"}</strong>
          </button>
        ))}
      </div>

      {currentIntent ? (
        <>
          <div className="kv-grid">
            <span>Status</span>
            <strong>{currentIntent.status}</strong>
            <span>Action</span>
            <strong>{currentIntent.action}</strong>
            <span>Target</span>
            <strong>{currentIntent.target_action || compactValue(currentIntent.params)}</strong>
            <span>Updated</span>
            <strong>{compactValue(currentIntent.updated_at)}</strong>
          </div>
          <div className="button-row">
            <button
              aria-label="Confirm selected intent"
              disabled={busy || !controlToken.trim() || currentIntent.status !== "awaiting_confirmation"}
              onClick={() => onUpdateIntent("confirm")}
              title="Confirm selected intent"
              type="button"
            >
              <Zap size={14} />
              Confirm
            </button>
            <button
              aria-label="Deny selected intent"
              className="danger"
              disabled={busy || !controlToken.trim() || currentIntent.status !== "awaiting_confirmation"}
              onClick={() => onUpdateIntent("deny")}
              title="Deny selected intent"
              type="button"
            >
              <XCircle size={14} />
              Deny
            </button>
          </div>
          <p className="status-line">{intentMessage}</p>
          <details className="raw-details" open>
            <summary>
              Payload
              <ChevronDown size={14} />
            </summary>
            <JsonPanel value={intentEnvelope} />
          </details>
        </>
      ) : (
        <div className="empty-mini">
          <ClipboardList size={24} />
          <span>Select an intent to review.</span>
        </div>
      )}
    </div>
  );
}
