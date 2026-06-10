import { Eye, Play, PlugZap, RefreshCw, ServerCog, TestTubeDiagonal } from "lucide-react";
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

type McpSmokeStepStatus = "idle" | "running" | "ready" | "blocked" | "failed";

type McpSmokeStep = {
  id: "resource" | "prompt";
  label: string;
  endpoint: string;
  target: string;
  status: McpSmokeStepStatus;
  detail: string;
  result?: unknown;
};

function mcpItemField(value: unknown, field: string): string {
  const record = asRecord(value);
  return String(record[field] || "").trim();
}

function mcpResultStatus(result: unknown): McpSmokeStepStatus {
  const record = asRecord(result);
  if (record.success === true) return "ready";
  const errorCode = String(record.error_code || "").toUpperCase();
  if (errorCode.includes("AUTH") || errorCode.includes("DISCOVERY") || errorCode.includes("UNAVAILABLE")) return "blocked";
  return "failed";
}

function mcpResultDetail(result: unknown): string {
  const record = asRecord(result);
  const data = asRecord(record.data);
  const nestedResult = asRecord(data.result);
  return String(nestedResult.text || data.prompt || data.status || record.error_code || record.error || record.object || "ready");
}

function connectorMessageLabel(status: string): string {
  if (status === "CONNECTORS_NOT_LOADED") return "连接器尚未加载";
  if (status === "CONNECTORS_LOADED") return "连接器已加载";
  if (status === "CONNECTOR_DETAIL_LOADED") return "连接器详情已加载";
  if (status === "CONNECTOR_TESTED") return "连接器测试完成";
  return status;
}

function smokeMessageLabel(status: string): string {
  if (status === "MCP_SMOKE_NOT_RUN") return "只读冒烟测试未运行";
  if (status === "MCP_SMOKE_RUNNING") return "只读冒烟测试运行中";
  if (status === "MCP_SMOKE_DONE") return "只读冒烟测试已完成";
  return status;
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
  const [smokeSteps, setSmokeSteps] = useState<McpSmokeStep[]>([]);
  const [smokeMessage, setSmokeMessage] = useState("MCP_SMOKE_NOT_RUN");
  const [smokeBusy, setSmokeBusy] = useState(false);

  const mcp = payload?.mcp;
  const firstServerName = String(mcp?.servers?.[0]?.name || "");
  const firstResourceUri = mcpItemField(mcp?.resources?.[0], "uri");
  const firstPromptName = mcpItemField(mcp?.prompts?.[0], "name");
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

  function initialSmokeSteps(): McpSmokeStep[] {
    return [
      {
        id: "resource",
        label: "读取 MCP 资源",
        endpoint: "/v1/mcp/resources/read",
        target: firstResourceUri || "未发现资源",
        status: "idle",
        detail: firstResourceUri ? "等待运行" : "无可用资源",
      },
      {
        id: "prompt",
        label: "获取 MCP 提示词",
        endpoint: "/v1/mcp/prompts/get",
        target: firstPromptName || "未发现提示词",
        status: "idle",
        detail: firstPromptName ? "等待运行" : "无可用提示词",
      },
    ];
  }

  async function runMcpReadOnlySmoke() {
    const selectedServer = firstServerName;
    const nextSteps = initialSmokeSteps();
    setSmokeSteps(nextSteps);
    setSmokeBusy(true);
    setSmokeMessage("MCP_SMOKE_RUNNING");
    try {
      for (const step of nextSteps) {
        if (!selectedServer || (step.id === "resource" && !firstResourceUri) || (step.id === "prompt" && !firstPromptName)) {
          setSmokeSteps((current) => current.map((item) => (item.id === step.id ? { ...item, status: "blocked", detail: "缺少可调用目标" } : item)));
          continue;
        }
        setSmokeSteps((current) => current.map((item) => (item.id === step.id ? { ...item, status: "running", detail: "调用 Agent HTTP" } : item)));
        try {
          const result = step.id === "resource"
            ? await api.mcpResourceRead(firstResourceUri, selectedServer)
            : await api.mcpPromptGet(firstPromptName, {}, selectedServer);
          setSmokeSteps((current) =>
            current.map((item) => (item.id === step.id ? { ...item, status: mcpResultStatus(result), detail: mcpResultDetail(result), result } : item))
          );
        } catch (error) {
          setSmokeSteps((current) =>
            current.map((item) => (item.id === step.id ? { ...item, status: "failed", detail: formatApiError(error) } : item))
          );
        }
      }
      setSmokeMessage("MCP_SMOKE_DONE");
    } finally {
      setSmokeBusy(false);
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
          <h1>MCP / 连接器</h1>
        </div>
        <div className="header-actions">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message || "ready"} />
          <StatusBadge
            status={connectorMessage.startsWith("AIASK_") ? "gated" : "ready"}
            label={connectorMessageLabel(connectorMessage)}
            technicalLabel={connectorMessage}
          />
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
              <span>MCP + 连接器</span>
              <h2>服务器、工具、资源、提示词、OAuth 与连接器管理</h2>
              <p>桌面端只读取 Agent 聚合状态并调用 Agent HTTP 管理接口，不直接连接 MCP server 或 manager。</p>
            </div>
            <PlugZap size={22} />
          </div>

          {!controlToken.trim() && (
            <GatedState
              reason={localizeBlockedReason("control token required") || "MCP 和连接器管理需要控制令牌。"}
              status="gated"
              title="连接器管理受限"
            />
          )}

          <div className="diagnostics-summary wide">
            <MetricCard label="MCP 状态" value={mcpStatus} status={mcpStatus} />
            <MetricCard label="服务器" value={mcp?.servers.length ?? 0} status={mcp?.servers.length ? "ready" : "not_loaded"} />
            <MetricCard label="工具" value={mcpToolCount} status={mcpToolCount ? "ready" : "not_loaded"} />
            <MetricCard label="资源" value={mcpResourceCount} status={mcpResourceCount ? "ready" : "not_loaded"} />
            <MetricCard label="提示词" value={mcpPromptCount} status={mcpPromptCount ? "ready" : "not_loaded"} />
            <MetricCard label="OAuth" value={oauthCount} status={oauthCount ? "ready" : "not_loaded"} />
            <MetricCard label="连接器" value={summaryNumbers.total} status={summaryNumbers.total ? "ready" : "not_loaded"} />
            <MetricCard label="已连接" value={summaryNumbers.connected} status={summaryNumbers.connected ? "ready" : "unconfigured"} />
          </div>

          {missingAuth.length ? (
            <GatedState
              reason={`MCP 授权缺失：${missingAuth.join(", ")}`}
              status="unconfigured"
              title="MCP 授权未配置"
            />
          ) : null}

          <section className="capability-section mcp-smoke-panel">
            <div className="section-header">
              <div>
                <span>{smokeMessageLabel(smokeMessage)}</span>
                <h3>MCP 只读调用冒烟测试</h3>
              </div>
              <button
                className="small-button"
                disabled={busy || connectorBusy || smokeBusy || !controlToken.trim() || !firstServerName}
                onClick={runMcpReadOnlySmoke}
                type="button"
              >
                <Play size={14} />
                运行 MCP 只读冒烟测试
              </button>
            </div>
            <div className="mcp-smoke-steps">
              {(smokeSteps.length ? smokeSteps : initialSmokeSteps()).map((step) => (
                <article className={`mcp-smoke-step ${step.status}`} key={step.id}>
                  <div className="mcp-smoke-step-head">
                    <div>
                      <strong>{step.label}</strong>
                      <span>{step.endpoint}</span>
                    </div>
                    <StatusBadge status={step.status} />
                  </div>
                  <div className="kv-grid">
                    <span>服务器</span>
                    <strong>{firstServerName || "-"}</strong>
                    <span>目标</span>
                    <strong>{step.target}</strong>
                    <span>结果</span>
                    <strong>{step.detail}</strong>
                  </div>
                  {step.result !== undefined && <RawEvidencePanel title={`${step.label}结果`} value={step.result} />}
                </article>
              ))}
            </div>
          </section>

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcp?.servers.length ?? 0} 个服务器</span>
                  <h3>MCP 服务器</h3>
                </div>
                <ServerCog size={18} />
              </div>
              <div className="data-table">
                <div className="table-head">
                  <span>服务器</span>
                  <span>传输</span>
                  <span>状态</span>
                  <span>详情</span>
                </div>
                {mcp?.servers.map((server) => (
                  <div className="table-row" key={server.name}>
                    <strong>{server.name}</strong>
                    <span>{server.transport || "-"}</span>
                    <span>{server.configured === false ? "unconfigured" : "configured"}</span>
                    <span>{shortText(String(server.domain || server.url || server.detail || "-"), 72)}</span>
                  </div>
                ))}
                {!mcp?.servers.length && <div className="table-empty">暂无 MCP 服务器。</div>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcpToolCount} 个工具</span>
                  <h3>MCP 工具</h3>
                </div>
              </div>
              <div className="mini-list">
                {mcp?.tools.slice(0, 12).map((tool) => (
                  <article key={`${tool.server || "mcp"}:${tool.name}`}>
                    <strong>{tool.wrapped_name || tool.name}</strong>
                    <span>{tool.server || "-"} / {tool.name}</span>
                    <p>{shortText(tool.description || "暂无描述。", 120)}</p>
                  </article>
                ))}
                {!mcp?.tools.length && <p className="muted">暂无 MCP 工具。</p>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcpResourceCount} 个资源</span>
                  <h3>MCP 资源</h3>
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
                {!mcp?.resources.length && <p className="muted">暂无 MCP 资源。</p>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{mcpPromptCount} 个提示词 / {oauthCount} 个 OAuth 状态</span>
                  <h3>提示词 / OAuth</h3>
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
                {!mcp?.prompts.length && !mcp?.oauth.length && <p className="muted">暂无提示词或 OAuth 状态。</p>}
              </div>
            </div>
          </section>

          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>{summaryNumbers.total} 总数 / {summaryNumbers.connected} 已连接 / {summaryNumbers.configured} 已配置</span>
                <h3>连接器摘要</h3>
              </div>
              <StatusBadge
                status={connectorMessage.startsWith("AIASK_") ? "gated" : "ready"}
                label={connectorMessageLabel(connectorMessage)}
                technicalLabel={connectorMessage}
              />
            </div>
            <div className="connector-type-grid">
              {Object.entries(groupedConnectors).map(([type, items]) => (
                <article key={type}>
                  <strong>{type}</strong>
                  <span>{items.filter((item) => item.connected || item.status === "ready").length}/{items.length} 已连接</span>
                </article>
              ))}
              {!connectors.length && <p className="muted">暂无连接器。</p>}
            </div>
          </section>

          <section className="capability-grid two">
            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>{connectors.length} 个连接器</span>
                  <h3>连接器列表</h3>
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
                    {connector.missing_env?.length ? <div className="notice info compact">缺少环境变量：{connector.missing_env.join(", ")}</div> : null}
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
                {!connectors.length && <p className="muted">暂无连接器列表。</p>}
              </div>
            </div>

            <div className="capability-section">
              <div className="section-header">
                <div>
                  <span>详情 / 测试</span>
                  <h3>连接器详情</h3>
                </div>
                <StatusBadge status={selectedConnector ? selectedConnector.status || "ready" : "not_loaded"} />
              </div>
              {selectedConnector ? (
                <div className="kv-grid">
                  <span>名称</span>
                  <strong>{selectedConnector.name}</strong>
                  <span>类型</span>
                  <strong>{selectedConnector.type}</strong>
                  <span>已配置</span>
                  <strong>{String(selectedConnector.configured ?? "unknown")}</strong>
                  <span>已连接</span>
                  <strong>{String(selectedConnector.connected ?? "unknown")}</strong>
                  <span>缺少环境变量</span>
                  <strong>{selectedConnector.missing_env?.join(", ") || "-"}</strong>
                </div>
              ) : (
                <p className="muted">请选择连接器，或先运行一次测试。</p>
              )}
              <RawEvidencePanel title="连接器原始结果" value={{ selectedConnector, connectorResult, connectorSummary }} />
            </div>
          </section>

          <section className="mcp-operations-panel">
            <div className="section-header inline-section-header">
              <div>
                <span>高级 MCP 操作</span>
                <h3>MCP 操作</h3>
              </div>
            </div>
            <McpPanel apiToken={apiToken} controlToken={controlToken} endpoint={endpoint} onRefresh={refresh} payload={payload} />
          </section>
        </div>
      </div>
    </section>
  );
}
