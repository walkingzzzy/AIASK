import { Cable, CheckCircle2, Circle, RefreshCw, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

interface Connector {
  id: string;
  name: string;
  type: string;
  category: string;
  enabled: boolean;
  configured: boolean;
  connected: boolean;
  status: string;
  description?: string;
  icon?: string;
  env_keys?: string[];
  missing_env?: string[];
  metadata?: Record<string, unknown>;
}

interface ConnectorsSummary {
  total: number;
  connected: number;
  configured: number;
  by_type: Record<string, { count: number; connected: number }>;
  connectors: Connector[];
}

interface ConnectorsPanelProps {
  apiToken?: string;
  controlToken?: string;
  endpoint?: string;
}

function connectorStatusIcon(status: string) {
  if (status === "ready" || status === "connected") return <CheckCircle2 size={14} className="text-green" />;
  if (status === "disconnected" || status === "disabled") return <Circle size={14} className="text-muted" />;
  if (status === "error" || status === "failed") return <XCircle size={14} className="text-red" />;
  return <Circle size={14} className="text-yellow" />;
}

function typeLabel(type: string): string {
  const labels: Record<string, string> = {
    financial: "金融应用",
    platform: "消息平台",
    mcp: "MCP 服务",
    plugin: "插件"
  };
  return labels[type] || type;
}

function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    trading: "交易",
    data: "数据",
    communication: "通信",
    tool: "工具"
  };
  return labels[category] || category;
}

function normalizeSummary(payload: { data?: unknown } | ConnectorsSummary): ConnectorsSummary {
  const candidate = "data" in payload && payload.data ? payload.data : payload;
  const record = candidate && typeof candidate === "object" ? (candidate as Partial<ConnectorsSummary>) : {};
  return {
    total: Number(record.total || 0),
    connected: Number(record.connected || 0),
    configured: Number(record.configured || 0),
    by_type: record.by_type || {},
    connectors: Array.isArray(record.connectors) ? record.connectors : []
  };
}

export function ConnectorsPanel({ apiToken = "", controlToken = "", endpoint = "http://127.0.0.1:8767" }: ConnectorsPanelProps) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [summary, setSummary] = useState<ConnectorsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("NOT_LOADED");

  const fetchConnectors = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await api.connectorsSummary();
      setSummary(normalizeSummary(payload));
      setMessage("CONNECTORS_LOADED");
    } catch (error) {
      setSummary(null);
      setMessage(formatApiError(error));
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchConnectors().catch(() => undefined);
  }, [fetchConnectors]);

  const grouped =
    summary?.connectors.reduce<Record<string, Connector[]>>((acc, connector) => {
      const key = connector.type || "other";
      if (!acc[key]) acc[key] = [];
      acc[key].push(connector);
      return acc;
    }, {}) || {};

  const typeOrder = ["financial", "platform", "mcp", "plugin", "other"];
  const sortedTypes = Object.keys(grouped).sort((a, b) => {
    const left = typeOrder.indexOf(a);
    const right = typeOrder.indexOf(b);
    return (left === -1 ? typeOrder.length : left) - (right === -1 ? typeOrder.length : right);
  });

  const gated = message === "AIASK_UNAUTHORIZED" || message === "AIASK_FORBIDDEN" || message === "AIASK_HTTP_503";

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <Cable size={20} />
          <span>连接器</span>
          <h2>应用绑定与集成</h2>
          <p>在一个界面里查看金融应用、消息平台、MCP 服务和原生插件连接状态。</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message} />
          <button className="btn-icon" onClick={fetchConnectors} disabled={loading} title="刷新连接器" type="button">
            <RefreshCw size={16} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      {gated && (
        <div className="notice warn">
          <span>查看连接器需要控制权限。</span>
          <p>请在设置中填写 Agent 控制令牌 Control token，然后刷新本面板。</p>
        </div>
      )}

      {summary && (
        <div className="diagnostics-summary wide">
          <div className="metric-card">
            <span>连接器总数</span>
            <strong>{summary.total}</strong>
          </div>
          <div className="metric-card ok">
            <span>已连接</span>
            <strong className="text-green">{summary.connected}</strong>
          </div>
          <div className="metric-card">
            <span>已配置</span>
            <strong>{summary.configured}</strong>
          </div>
          <div className="metric-card">
            <span>未配置</span>
            <strong className="text-muted">{Math.max(summary.total - summary.configured, 0)}</strong>
          </div>
        </div>
      )}

      {sortedTypes.map((type) => {
        const connectors = grouped[type];
        const active = connectors.filter((connector) => connector.connected || connector.status === "ready").length;
        return (
          <div key={type} className="capability-section">
            <div className="section-header">
              <div>
                <span>{type}</span>
                <h3>{typeLabel(type)}</h3>
              </div>
              <StatusBadge
                status={active ? "implemented" : "unconfigured"}
                label={`${active}/${connectors.length} 已连接`}
              />
            </div>
            <div className="connector-list">
              {connectors.map((connector, index) => (
                <article
                  key={`${connector.id || connector.name || connector.type || "connector"}-${index}`}
                  className="connector-item"
                >
                  <div className="connector-header">
                    {connectorStatusIcon(connector.status)}
                    <strong>{connector.name}</strong>
                    {connector.category && <span className="tag">{categoryLabel(connector.category)}</span>}
                    <StatusBadge
                      status={connector.status === "ready" || connector.status === "connected" ? "implemented" : connector.status}
                      label={connector.status}
                    />
                  </div>
                  {connector.description && <p className="muted">{connector.description}</p>}
                  {connector.missing_env && connector.missing_env.length > 0 && (
                    <div className="notice info compact">
                      <span>缺少环境变量：{connector.missing_env.join(", ")}</span>
                    </div>
                  )}
                  {Array.isArray(connector.metadata?.tools_read) && connector.metadata.tools_read.length > 0 && (
                    <div className="connector-tools">
                      <span className="muted">读取工具</span>
                      <strong>{String(connector.metadata.tools_read.length)}</strong>
                    </div>
                  )}
                  {Array.isArray(connector.metadata?.tools_trade) && connector.metadata.tools_trade.length > 0 && (
                    <div className="connector-tools">
                      <span className="muted">交易工具</span>
                      <strong>{String(connector.metadata.tools_trade.length)}</strong>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>
        );
      })}

      {!summary && !loading && !gated && (
        <div className="notice info">
          <span>尚未加载连接器摘要。</span>
        </div>
      )}
    </div>
  );
}
