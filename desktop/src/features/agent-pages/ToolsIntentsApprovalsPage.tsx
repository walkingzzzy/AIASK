import { RefreshCw, ShieldCheck, Wrench, Filter, Search, Info } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { GeneralApprovalsPanel } from "../../components/InspectorPanels";
import { JsonPanel, StatusBadge, compact } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import type { IntentRecord, ToolCatalogItem, ToolEnvelope } from "../../types";
import "./ToolsIntentsApprovalsPage.css";

type ToolFilterType = "all" | "finance_safe" | "full_mode" | "read_only" | "intent" | "approval" | "blocked";
type ToolSortBy = "name" | "category" | "visibility";

function asIntentRecord(value: Record<string, unknown>): IntentRecord | null {
  const intent_id = typeof value.intent_id === "string" ? value.intent_id : "";
  const action = typeof value.action === "string" ? value.action : "";
  const target_tool = typeof value.target_tool === "string" ? value.target_tool : "";
  const target_action = typeof value.target_action === "string" ? value.target_action : "";
  const status = typeof value.status === "string" ? value.status : "";
  if (!intent_id || !action || !target_tool || !target_action || !status) return null;
  return {
    intent_id,
    action,
    target_tool,
    target_action,
    status,
    params: typeof value.params === "object" && value.params && !Array.isArray(value.params) ? (value.params as Record<string, unknown>) : undefined,
    result: value.result,
    error: typeof value.error === "string" ? value.error : null,
    created_at: typeof value.created_at === "string" ? value.created_at : undefined,
    updated_at: typeof value.updated_at === "string" ? value.updated_at : undefined,
    expires_at: typeof value.expires_at === "string" ? value.expires_at : undefined,
  };
}

function interactionLabel(tool: ToolCatalogItem): string {
  if (tool.interaction_mode) return tool.interaction_mode;
  if (typeof tool.side_effect === "string") return tool.side_effect;
  return tool.side_effect?.level || "unknown";
}

function sideEffectLabel(tool: ToolCatalogItem): string {
  return typeof tool.side_effect === "string" ? tool.side_effect : tool.side_effect?.level || "unknown";
}

function visibilityLabel(tool: ToolCatalogItem): string {
  return tool.visibility || "api_safe";
}

function isFinanceSafe(tool: ToolCatalogItem): boolean {
  const visibility = visibilityLabel(tool);
  return visibility === "finance_safe" || visibility === "api_safe";
}

function isFullModeOnly(tool: ToolCatalogItem): boolean {
  return visibilityLabel(tool) === "full_mode_only";
}

function toolTags(tool: ToolCatalogItem): string[] {
  const visibility = visibilityLabel(tool);
  const interaction = interactionLabel(tool);
  const sideEffect = sideEffectLabel(tool);
  const tags = [isFinanceSafe(tool) ? "finance_safe" : visibility, interaction];
  if (isFullModeOnly(tool)) tags.push("full_mode_only");
  if (sideEffect === "read_only") tags.push("read_only");
  if (tool.confirmation_required && !tags.includes("approval")) tags.push("approval");
  if (tool.blocked_reason || interaction === "blocked") tags.push("blocked");
  return [...new Set(tags.filter(Boolean))];
}

export function ToolsIntentsApprovalsPage({
  endpoint,
  apiToken,
  controlToken,
  tools,
  hermesTools,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  tools: ToolCatalogItem[];
  hermesTools: ToolCatalogItem[];
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [intents, setIntents] = useState<IntentRecord[]>([]);
  const [currentIntent, setCurrentIntent] = useState<IntentRecord | null>(null);
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  // 工具过滤和搜索状态
  const [toolSearchQuery, setToolSearchQuery] = useState("");
  const [toolFilterType, setToolFilterType] = useState<ToolFilterType>("all");
  const [toolSortBy, setToolSortBy] = useState<ToolSortBy>("name");
  const [selectedTool, setSelectedTool] = useState<ToolCatalogItem | null>(null);

  async function refresh() {
    setBusy(true);
    try {
      const payload = await api.intentsList(undefined, 80);
      const nextIntents = (payload.data || [])
        .map((item) => asIntentRecord(item as Record<string, unknown>))
        .filter((item): item is IntentRecord => Boolean(item));
      setIntents(nextIntents);
      setMessage("INTENTS_LOADED");
      if (!currentIntent && nextIntents[0]?.intent_id) {
        await loadIntent(nextIntents[0].intent_id);
      }
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadIntent(intentId: string) {
    setBusy(true);
    try {
      const envelope = await api.getIntent(intentId);
      setIntentEnvelope(envelope);
      const intent = ((envelope.data as { intent?: IntentRecord } | undefined)?.intent || null) as IntentRecord | null;
      setCurrentIntent(intent);
      setMessage("INTENT_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function decideIntent(action: "confirm" | "deny") {
    if (!currentIntent) return;
    setBusy(true);
    try {
      const envelope =
        action === "confirm"
          ? await api.confirmIntent(currentIntent.intent_id)
          : await api.denyIntent(currentIntent.intent_id, "desktop_denied");
      setIntentEnvelope(envelope);
      setMessage(action === "confirm" ? "INTENT_CONFIRMED" : "INTENT_DENIED");
      await refresh();
      await loadIntent(currentIntent.intent_id);
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

  // 工具过滤和排序逻辑
  const filteredAndSortedTools = useMemo(() => {
    let filtered = [...tools];

    // 搜索过滤
    if (toolSearchQuery.trim()) {
      const query = toolSearchQuery.toLowerCase();
      filtered = filtered.filter(
        (tool) =>
          tool.name.toLowerCase().includes(query) ||
          tool.description?.toLowerCase().includes(query) ||
          tool.category?.toLowerCase().includes(query)
      );
    }

    // 类型过滤
    switch (toolFilterType) {
      case "finance_safe":
        filtered = filtered.filter(isFinanceSafe);
        break;
      case "full_mode":
        filtered = filtered.filter(isFullModeOnly);
        break;
      case "read_only":
        filtered = filtered.filter((tool) => sideEffectLabel(tool) === "read_only" || interactionLabel(tool) === "read_only");
        break;
      case "intent":
        filtered = filtered.filter((tool) => interactionLabel(tool) === "intent");
        break;
      case "approval":
        filtered = filtered.filter((tool) => interactionLabel(tool) === "approval" || tool.confirmation_required === true);
        break;
      case "blocked":
        filtered = filtered.filter((tool) => interactionLabel(tool) === "blocked" || Boolean(tool.blocked_reason));
        break;
      default:
        break;
    }

    // 排序
    filtered.sort((a, b) => {
      switch (toolSortBy) {
        case "name":
          return a.name.localeCompare(b.name);
        case "category":
          return (a.category || "").localeCompare(b.category || "");
        case "visibility":
          return (a.visibility || "").localeCompare(b.visibility || "");
        default:
          return 0;
      }
    });

    return filtered;
  }, [tools, toolSearchQuery, toolFilterType, toolSortBy]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>Agent</span>
          <h1>Tools / Intents / Approvals</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message} label={message} />
          <button className="small-button" disabled={busy} onClick={() => refresh()} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{filteredAndSortedTools.length} / {tools.length} 个工具</span>
                <h3>工具目录</h3>
              </div>
              <Wrench size={18} />
            </div>

            {/* 工具搜索和筛选工具栏 */}
            <div className="tools-filter-toolbar">
              <div className="tools-search-box">
                <Search size={14} />
                <input
                  type="text"
                  placeholder="搜索工具名称、描述、分类..."
                  value={toolSearchQuery}
                  onChange={(e) => setToolSearchQuery(e.target.value)}
                />
              </div>

              <div className="tools-filter-row">
                <Filter size={14} />
                <select value={toolFilterType} onChange={(e) => setToolFilterType(e.target.value as ToolFilterType)}>
                  <option value="all">所有工具</option>
                  <option value="finance_safe">金融安全</option>
                  <option value="full_mode">仅 full mode</option>
                  <option value="read_only">只读</option>
                  <option value="intent">Intent</option>
                  <option value="approval">Approval</option>
                  <option value="blocked">Blocked</option>
                </select>

                <span>排序：</span>
                <select value={toolSortBy} onChange={(e) => setToolSortBy(e.target.value as ToolSortBy)}>
                  <option value="name">名称</option>
                  <option value="category">分类</option>
                  <option value="visibility">可见性</option>
                </select>
              </div>
            </div>

            <div className="data-table">
              <div className="table-head">
                <span>工具</span>
                <span>visibility</span>
                <span>safety / interaction</span>
                <span>操作</span>
              </div>
              {filteredAndSortedTools.slice(0, 20).map((tool) => (
                <div className="table-row" key={tool.name}>
                  <strong>{tool.name}</strong>
                  <span>{visibilityLabel(tool)}</span>
                  <span className="tool-chip-row">
                    {toolTags(tool).map((tag) => (
                      <StatusBadge key={tag} status={tag} label={tag} />
                    ))}
                  </span>
                  <button
                    className="small-button"
                    onClick={() => setSelectedTool(tool)}
                    type="button"
                  >
                    <Info size={13} />
                    详情
                  </button>
                </div>
              ))}
            </div>

            {/* 工具详情面板 */}
            {selectedTool && (
              <div className="tool-detail-panel">
                <div className="tool-detail-header">
                  <div>
                    <h4>{selectedTool.name}</h4>
                    <div className="tool-detail-badges">
                      {toolTags(selectedTool).map((tag) => (
                        <span className={`tool-detail-badge ${tag === "blocked" ? "danger" : tag === "approval" ? "warning" : ""}`} key={tag}>
                          {tag}
                        </span>
                      ))}
                      {selectedTool.category && (
                        <span className="tool-detail-badge">{selectedTool.category}</span>
                      )}
                    </div>
                  </div>
                  <button className="small-button" onClick={() => setSelectedTool(null)} type="button">
                    关闭
                  </button>
                </div>

                {selectedTool.description && (
                  <div className="tool-detail-section">
                    <h5>描述</h5>
                    <p>{selectedTool.description}</p>
                  </div>
                )}

                {selectedTool.parameters && (
                  <div className="tool-detail-section">
                    <h5>参数</h5>
                    <div className="tool-params-list">
                      {Object.entries(selectedTool.parameters).map(([key, value]) => (
                        <div className="tool-param-item" key={key}>
                          <strong>{key}</strong>
                          <span>{typeof value === "object" ? JSON.stringify(value) : String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {selectedTool.blocked_reason && (
                  <div className="tool-usage-hint">
                    <strong>限制原因：</strong> {selectedTool.blocked_reason}
                  </div>
                )}
              </div>
            )}

            <p className="muted">
              `/v1/tools` 是唯一工具目录。Hermes full 工具只作为契约对照数据读取，当前共 {hermesTools.length} 个。
            </p>
          </section>

          <section className="capability-grid two">
            <section className="capability-section">
              <div className="section-header">
                <div>
                  <span>{intents.length} 条</span>
                  <h3>Intents</h3>
                </div>
                <ShieldCheck size={18} />
              </div>
              <div className="mini-list">
                {intents.map((intent) => (
                  <button
                    className={currentIntent?.intent_id === intent.intent_id ? "active" : ""}
                    key={intent.intent_id}
                    onClick={() => loadIntent(intent.intent_id)}
                    type="button"
                  >
                    <strong>{intent.action}</strong>
                    <span>{intent.intent_id}</span>
                    <span>{intent.status}</span>
                  </button>
                ))}
                {!intents.length && <p className="muted">暂无意图记录。</p>}
              </div>
              {currentIntent && (
                <>
                  <div className="button-row">
                    <button
                      className="small-button"
                      disabled={busy || !controlToken.trim() || currentIntent.status !== "awaiting_confirmation"}
                      onClick={() => decideIntent("confirm")}
                      type="button"
                    >
                      确认
                    </button>
                    <button
                      className="small-button danger"
                      disabled={busy || !controlToken.trim() || currentIntent.status !== "awaiting_confirmation"}
                      onClick={() => decideIntent("deny")}
                      type="button"
                    >
                      拒绝
                    </button>
                  </div>
                  <details className="raw-details">
                    <summary>当前 Intent</summary>
                    <JsonPanel value={intentEnvelope || currentIntent} />
                  </details>
                </>
              )}
            </section>

            <GeneralApprovalsPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} />
          </section>

          <details className="raw-details">
            <summary>最近数据快照</summary>
            <JsonPanel value={{ intents, currentIntent, message: compact(message) }} />
          </details>
        </div>
      </div>
    </section>
  );
}
