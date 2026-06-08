import { Eye, PlugZap, RefreshCw, ServerCog, TestTubeDiagonal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { GatedState, JsonPanel, MetricCard, RawEvidencePanel, StatusBadge, compact, localizeBlockedReason, shortText } from "../../components/shared";
import { useCapabilityWorkbench } from "../../hooks/useCapabilityWorkbench";
import { AiaskApi } from "../../services/aiaskApi";
import type { CapabilityWorkbenchPayload, ConnectorDetail } from "../../types";
import { McpPanel } from "../mcp/McpPanel";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function connectorRef(connector: ConnectorDetail): string {
  if (connector.id && connector.id.includes(":")) return connector.id.slice(connector.id.indexOf(":") + 1);
  if (connector.id) return connector.id;
  return connector.name;
}

function statusFromPayload(payload: CapabilityWorkbenchPayload | null): string {
  const mcp = payload?.mcp;
  if (!mcp) return "not_loaded";
  if (mcp.gated) return "gated";
  return mcp.discovery_status || mcp.registration_status || "unknown";
}

function connectorsSummaryNumbers(summary: unknown, list: ConnectorDetail[]) {
  const record = asRecord((asRecord(summary).data || summary));
  return {
    total: Number(record.total ?? list.length),
    connected: Number(record.connected ?? list.filter((item) => item.connected || item.status === "ready").length),
    configured: Number(record.configured ?? list.filter((item) => item.configured).length),
  };
}

export function McpConnectorsPage({
  endpoint,
  apiToken,
  controlToken,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const { payload, message, busy, refresh } = useCapabilityWorkbench(endpoint, apiToken, controlToken);
  const [connectorSummary, setConnectorSummary] = useState<unknown>(null);
  const [connectors, setConnectors] = useState<ConnectorDetail[]>([]);
  const [selectedConnector, setSelectedConnector] = useState<ConnectorDetail | null>(null);
  const [connectorResult, setConnectorResult] = useState<unknown>(null);
  const [connectorMessage, setConnectorMessage] = useState("CONNECTORS_NOT_LOADED");
  const [connectorBusy, setConnectorBusy] = useState(false);

  const mcp = payload?.mcp;
  const summaryNumbers = connectorsSummaryNumbers(connectorSummary, connectors);
  const mcpStatus = statusFromPayload(payload);
  const mcpToolCount = mcp?.discovered_counts?.tools ?? mcp?.tools.length ?? 0;
  const mcpResourceCount = mcp?.discovered_counts?.resources ?? mcp?.resources.length ?? 0;
  const mcpPromptCount = mcp?.discovered_counts?.prompts ?? mcp?.prompts.length ?? 0;
  const oauthCount = mcp?.oauth.length ?? 0;
  const missingAuth = mcp?.missing_auth_env_vars || [];
  const groupedConnectors = connectors.reduce<Record<string, ConnectorDetail[]>>((acc, connector) => {
    const key = connector.type || "unknown";
    if (!acc[key]) acc[key] = [];
    acc[key].push(connector);
    return acc;
  }, {});

  async function loadConnectors() {
    setConnectorBusy(true);
    try {
      const [summaryPayload, listPayload] = await Promise.all([
        api.connectorsSummary(),
        api.connectorsList(),
      ]);
      setConnectorSummary(summaryPayload);
      setConnectors(listPayload.data || []);
      setConnectorMessage("CONNECTORS_LOADED");
    } catch (error) {
      setConnectorSummary(null);
      setConnectors([]);
      setConnectorMessage(formatApiError(error));
    } finally {
      setConnectorBusy(false);
    }
  }

  async function refreshAll() {
    await Promise.all([refresh(), loadConnectors()]);
  }

  async function loadConnectorDetail(connector: ConnectorDetail) {
    setConnectorBusy(true);
    try {
      const payload = await api.connectorDetail(connector.type, connectorRef(connector));
      setSelectedConnector(payload.data || connector);
      setConnectorResult(payload);
      setConnectorMessage("CONNECTOR_DETAIL_LOADED");
    } catch (error) {
      setConnectorMessage(formatApiError(error));
    } finally {
      setConnectorBusy(false);
    }
  }

  async function testConnector(connector: ConnectorDetail) {
    setConnectorBusy(true);
    try {
      const payload = await api.connectorTest(connector.type, connectorRef(connector));
      setSelectedConnector(payload.data || connector);
      setConnectorResult(payload);
      setConnectorMessage("CONNECTOR_TESTED");
    } catch (error) {
      setConnectorMessage(formatApiError(error));
    } finally {
      setConnectorBusy(false);
    }
  }

  useEffect(() => {
    refreshAll().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [controlToken, endpoint]);

  return (
    <section className="capabilities-workspace">
      <header className="capabilities-header">
        <div>
          <span>运维与连接</span>
          <h1>MCP / Connectors</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message || "ready"} />
          <StatusBadge status={connectorMessage.startsWith("AIASK_") ? "gated" : "ready"} label={connectorMessage} />
          <button className="small-button" disabled={busy || connectorBusy} onClick={refreshAll} type="button">
            <RefreshCw size={14} className={busy || connectorBusy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="capability-stack">
          <div className="capability-banner">
            <div>
              <span>MCP + Connectors</span>
              <h2>Servers、tools、resources、prompts、OAuth 与连接器管理</h2>
              <p>桌面端只读取 Agent 聚合状态并调用 Agent HTTP 管理接口，不直接连接 MCP server 或 manager。</p>
            </div>
            <PlugZap size={22} />
          </div>

          {!controlToken.trim() && (
            <GatedState
              reason={localizeBlockedReason("control token required") || "MCP 和 connectors 管理需要 Control token。"}
              status="gated"
              title="连接器管理受限"
            />
          )}

          <div className="diagnostics-summary wide">
            <MetricCard label="MCP status" value={mcpStatus} status={mcpStatus} />
            <MetricCard label="Servers" value={mcp?.servers.length ?? 0} status={mcp?.servers.length ? "ready" : "not_loaded"} />
            <MetricCard label="Tools" value={mcpToolCount} status={mcpToolCount ? "ready" : "not_loaded"} />
            <MetricCard label="Resources" value={mcpResourceCount} status={mcpResourceCount ? "ready" : "not_loaded"} />
            <MetricCard label="Prompts" value={mcpPromptCount} status={mcpPromptCount ? "ready" : "not_loaded"} />
            <MetricCard label="OAuth" value={oauthCount} status={oauthCount ? "ready" : "not_loaded"} />
            <MetricCard label="Connectors" value={summaryNumbers.total} status={summaryNumbers.total ? "ready" : "not_loaded"} />
            <MetricCard label="Connected" value={summaryNumbers.connected} status={summaryNumbers.connected ? "ready" : "unconfigured"} />
          </div>

          {missingAuth.length ? (
            <GatedState
              reason={`MCP 授权缺失：${missingAuth.join(", ")}`}
              status="unconfigured"
              title="MCP 授权未配置"
            />
          ) : null}

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcp?.servers.length ?? 0} servers</span>
                  <h3>MCP servers</h3>
                </div>
                <ServerCog size={18} />
              </div>
              <div className="data-table">
                <div className="table-head">
                  <span>server</span>
                  <span>transport</span>
                  <span>status</span>
                  <span>detail</span>
                </div>
                {mcp?.servers.map((server) => (
                  <div className="table-row" key={server.name}>
                    <strong>{server.name}</strong>
                    <span>{server.transport || "-"}</span>
                    <span>{server.configured === false ? "unconfigured" : "configured"}</span>
                    <span>{shortText(String(server.domain || server.url || server.detail || "-"), 72)}</span>
                  </div>
                ))}
                {!mcp?.servers.length && <div className="table-empty">No MCP servers loaded.</div>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcpToolCount} tools</span>
                  <h3>MCP tools</h3>
                </div>
              </div>
              <div className="mini-list">
                {mcp?.tools.slice(0, 12).map((tool) => (
                  <article key={`${tool.server || "mcp"}:${tool.name}`}>
                    <strong>{tool.wrapped_name || tool.name}</strong>
                    <span>{tool.server || "-"} / {tool.name}</span>
                    <p>{shortText(tool.description || "No description.", 120)}</p>
                  </article>
                ))}
                {!mcp?.tools.length && <p className="muted">No MCP tools loaded.</p>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcpResourceCount} resources</span>
                  <h3>MCP resources</h3>
                </div>
              </div>
              <div className="mini-list">
                {mcp?.resources.slice(0, 8).map((resource, index) => {
                  const item = asRecord(resource);
                  return (
                    <article key={`${item.uri || item.name || index}`}>
                      <strong>{compact(item.name || item.uri || `resource-${index + 1}`)}</strong>
                      <span>{compact(item.uri || item.server || "-")}</span>
                    </article>
                  );
                })}
                {!mcp?.resources.length && <p className="muted">No MCP resources loaded.</p>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcpPromptCount} prompts / {oauthCount} oauth</span>
                  <h3>Prompts / OAuth</h3>
                </div>
              </div>
              <div className="mini-list">
                {mcp?.prompts.slice(0, 6).map((prompt, index) => {
                  const item = asRecord(prompt);
                  return (
                    <article key={`${item.name || index}`}>
                      <strong>{compact(item.name || `prompt-${index + 1}`)}</strong>
                      <span>{shortText(String(item.description || item.server || "-"), 96)}</span>
                    </article>
                  );
                })}
                {mcp?.oauth.slice(0, 6).map((oauth, index) => {
                  const item = asRecord(oauth);
                  return (
                    <article key={`oauth:${item.server || item.name || index}`}>
                      <strong>{compact(item.server || item.name || `oauth-${index + 1}`)}</strong>
                      <span>{compact(item.status || item.authenticated || item.error || "unknown")}</span>
                    </article>
                  );
                })}
                {!mcp?.prompts.length && !mcp?.oauth.length && <p className="muted">No prompts or OAuth status loaded.</p>}
              </div>
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{summaryNumbers.total} total / {summaryNumbers.connected} connected / {summaryNumbers.configured} configured</span>
                <h3>Connectors summary</h3>
              </div>
              <StatusBadge status={connectorMessage.startsWith("AIASK_") ? "gated" : "ready"} label={connectorMessage} />
            </div>
            <div className="connector-type-grid">
              {Object.entries(groupedConnectors).map(([type, items]) => (
                <article key={type}>
                  <strong>{type}</strong>
                  <span>{items.filter((item) => item.connected || item.status === "ready").length}/{items.length} connected</span>
                </article>
              ))}
              {!connectors.length && <p className="muted">No connectors loaded.</p>}
            </div>
          </section>

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{connectors.length} connectors</span>
                  <h3>Connector list</h3>
                </div>
              </div>
              <div className="connector-list">
                {connectors.map((connector, index) => (
                  <article className="connector-item" key={`${connector.type}:${connectorRef(connector)}:${index}`}>
                    <div className="connector-header">
                      <strong>{connector.name}</strong>
                      <span className="tag">{connector.type}</span>
                      <StatusBadge status={connector.status || (connector.connected ? "ready" : "unconfigured")} />
                    </div>
                    {connector.category && <p className="muted">{connector.category}</p>}
                    {connector.missing_env?.length ? <div className="notice info compact">missing env: {connector.missing_env.join(", ")}</div> : null}
                    <div className="row-actions">
                      <button className="small-button" disabled={connectorBusy} onClick={() => loadConnectorDetail(connector)} type="button">
                        <Eye size={13} />
                        详情
                      </button>
                      <button className="small-button" disabled={connectorBusy || !controlToken.trim()} onClick={() => testConnector(connector)} type="button">
                        <TestTubeDiagonal size={13} />
                        测试
                      </button>
                    </div>
                  </article>
                ))}
                {!connectors.length && <p className="muted">No connector list loaded.</p>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>detail / test</span>
                  <h3>Connector detail</h3>
                </div>
                <StatusBadge status={selectedConnector ? selectedConnector.status || "ready" : "not_loaded"} />
              </div>
              {selectedConnector ? (
                <div className="kv-grid">
                  <span>Name</span>
                  <strong>{selectedConnector.name}</strong>
                  <span>Type</span>
                  <strong>{selectedConnector.type}</strong>
                  <span>Configured</span>
                  <strong>{String(selectedConnector.configured ?? "unknown")}</strong>
                  <span>Connected</span>
                  <strong>{String(selectedConnector.connected ?? "unknown")}</strong>
                  <span>Missing env</span>
                  <strong>{selectedConnector.missing_env?.join(", ") || "-"}</strong>
                </div>
              ) : (
                <p className="muted">Select a connector or run a test.</p>
              )}
              <RawEvidencePanel title="Connector raw result" value={{ selectedConnector, connectorResult, connectorSummary }} />
            </div>
          </section>

          <section className="mcp-operations-panel">
            <div className="section-header inline-section-header">
              <div>
                <span>advanced MCP operations</span>
                <h3>MCP operations</h3>
              </div>
            </div>
            <McpPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />
          </section>
        </div>
      </div>
    </section>
  );
}
