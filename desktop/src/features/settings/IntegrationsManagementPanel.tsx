import { Cable, RefreshCw, RotateCcw, Send, Settings2 } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge, compact, confirmAction } from "../../components/shared";
import { ConnectorWizard } from "../connectors/ConnectorWizard";
import { AiaskApi } from "../../services/aiaskApi";
import type { ConnectorDetail, GatewayDaemonStatus, GatewayMessage, GatewayPlatform } from "../../types";

function connectorKey(connector: ConnectorDetail): string {
  return connector.id || `${connector.type}:${connectorRef(connector)}`;
}

/**
 * Resolve the backend connector identifier segment.
 *
 * The backend keys connectors as `${type}:${defId}` (e.g. "financial:tongdaxin")
 * and its routes expect the def-id segment (`tongdaxin`), NOT the localized
 * display name (`connector.name` = "通达信"). Passing the display name produces
 * 404s on `/v1/connectors/{type}/{name}` and misses ConnectorWizard configs.
 */
function connectorRef(connector: ConnectorDetail): string {
  if (connector.id && connector.id.includes(":")) {
    return connector.id.slice(connector.id.indexOf(":") + 1);
  }
  if (connector.id) return connector.id;
  return connector.name;
}

export function IntegrationsManagementPanel({
  apiToken,
  controlToken,
  endpoint,
  userId
}: {
  apiToken: string;
  controlToken: string;
  endpoint: string;
  userId?: string;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [connectors, setConnectors] = useState<ConnectorDetail[]>([]);
  const [platforms, setPlatforms] = useState<GatewayPlatform[]>([]);
  const [messages, setMessages] = useState<GatewayMessage[]>([]);
  const [directory, setDirectory] = useState<Array<Record<string, unknown>>>([]);
  const [gatewayStatus, setGatewayStatus] = useState<unknown>(null);
  const [daemonStatus, setDaemonStatus] = useState<GatewayDaemonStatus | null>(null);
  const [selected, setSelected] = useState<ConnectorDetail | null>(null);
  const [wizard, setWizard] = useState<ConnectorDetail | null>(null);
  const [envPreview, setEnvPreview] = useState<Record<string, string> | null>(null);
  const [sendTarget, setSendTarget] = useState("");
  const [sendPlatform, setSendPlatform] = useState("local");
  const [sendMessage, setSendMessage] = useState("MCP UI smoke test: 集成消息预览");
  const [result, setResult] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_LOADED");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      const [connectorPayload, platformPayload, messagePayload, directoryPayload, statusPayload, daemonPayload] = await Promise.all([
        api.connectorsList(),
        api.gatewayPlatforms(),
        api.gatewayMessages(undefined, 30),
        api.gatewayDirectory(undefined, undefined, 50),
        api.gatewayStatus(),
        api.gatewayDaemonStatus()
      ]);
      setConnectors(connectorPayload.data || []);
      setPlatforms(platformPayload.data || []);
      setMessages(messagePayload.data || []);
      setDirectory(directoryPayload.data || []);
      setGatewayStatus(statusPayload);
      setDaemonStatus(daemonPayload);
      setMessage("INTEGRATIONS_LOADED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function testConnector(connector: ConnectorDetail) {
    setBusy(true);
    try {
      const payload = await api.connectorTest(connector.type, connectorRef(connector));
      setSelected(payload.data || connector);
      setResult(payload);
      setMessage("CONNECTOR_TESTED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function platformAction(platform: string, action: "start" | "stop" | "health") {
    if (action !== "health" && !confirmAction(action === "start" ? "启动 Gateway 平台" : "停止 Gateway 平台", `Platform: ${platform}`)) return;
    setBusy(true);
    setMessage(`GATEWAY_${action.toUpperCase()}_RUNNING`);
    try {
      const payload =
        action === "start"
          ? await api.gatewayPlatformStart(platform)
          : action === "stop"
            ? await api.gatewayPlatformStop(platform)
            : await api.gatewayPlatformHealth(platform);
      setResult(payload);
      setMessage(`GATEWAY_${action.toUpperCase()}_OK`);
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function refreshDirectory() {
    if (!confirmAction("刷新 Gateway 目录", "将通过 Agent 请求重新同步目录。")) return;
    setBusy(true);
    setMessage("DIRECTORY_REFRESH_RUNNING");
    try {
      setResult(await api.gatewayDirectoryRefresh());
      setMessage("DIRECTORY_REFRESHED");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function retryMessage(messageId: string) {
    if (!confirmAction("重试 Gateway 消息", `Message: ${messageId}`)) return;
    setBusy(true);
    setMessage("GATEWAY_RETRY_RUNNING");
    try {
      setResult(await api.gatewayMessageRetry(messageId));
      setMessage("GATEWAY_RETRY_OK");
      await refresh();
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function createSendIntent(event: FormEvent) {
    event.preventDefault();
    if (!confirmAction("创建 Gateway 发送审批", `Platform: ${sendPlatform}\nTarget: ${sendTarget}`)) return;
    setBusy(true);
    setMessage("GATEWAY_INTENT_CREATING");
    try {
      const payload = await api.gatewaySendIntent({
        platform: sendPlatform,
        target: sendTarget,
        message: sendMessage,
        user_id: userId
      });
      setResult(payload);
      setMessage(payload.success ? "GATEWAY_INTENT_CREATED" : payload.error || "GATEWAY_INTENT_FAILED");
    } catch (error) {
      setMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <Cable size={20} />
          <span>应用集成</span>
          <h2>连接器、网关与消息预览</h2>
          <p>凭据通过 Agent 启动环境变量配置；桌面端只生成配置片段、测试连接和创建审批意图。</p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message} />
          <button className="small-button" disabled={busy} onClick={refresh} type="button">
            <RefreshCw size={14} className={busy ? "spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      {!controlToken.trim() && <div className="notice warn">应用集成详情需要控制令牌；请先在“令牌与权限”中填写。</div>}

      <section className="capability-section">
        <div className="section-header">
          <div>
            <span>{connectors.length} 个连接器</span>
            <h3>连接器清单</h3>
          </div>
          <StatusBadge status={connectors.length ? "ready" : "not_loaded"} />
        </div>
        <div className="connector-list">
          {connectors.map((connector) => (
            <article className="connector-item" key={connectorKey(connector)}>
              <div className="connector-header">
                <strong>{connector.name}</strong>
                <span className="tag">{connector.type}</span>
                <StatusBadge status={connector.status || (connector.connected ? "ready" : "unconfigured")} label={connector.connected ? "已连接" : connector.configured ? "已配置" : "未配置"} />
              </div>
              {connector.description && <p className="muted">{connector.description}</p>}
              {connector.missing_env?.length ? <div className="notice info compact">缺少环境变量：{connector.missing_env.join(", ")}</div> : null}
              <div className="row-actions">
                <button className="small-button" disabled={busy} onClick={() => setSelected(connector)} type="button">详情</button>
                <button className="small-button" disabled={busy} onClick={() => testConnector(connector)} type="button">测试连接</button>
                <button className="small-button" disabled={busy} onClick={() => setWizard(connector)} type="button">
                  <Settings2 size={13} />
                  生成配置片段
                </button>
              </div>
            </article>
          ))}
          {!connectors.length && <p className="muted">尚未加载连接器；请填写控制令牌后刷新。</p>}
        </div>
      </section>

      {wizard && (
        <section className="capability-section">
          <ConnectorWizard
            connectorName={connectorRef(wizard)}
            connectorType={wizard.type}
            onClose={() => setWizard(null)}
            onSave={(config) => {
              setEnvPreview(config);
              setWizard(null);
              setMessage("ENV_SNIPPET_READY");
            }}
          />
        </section>
      )}

      {envPreview && (
        <section className="capability-section">
          <div className="section-header">
            <h3>环境变量片段</h3>
            <StatusBadge status="ready" label="需重启 Agent" />
          </div>
          <pre className="env-block">{Object.entries(envPreview).map(([key, value]) => `${key}=${value}`).join("\n")}</pre>
          <p className="muted">请把片段加入 Agent 启动环境后重启服务；桌面端不会保存这些密钥。</p>
        </section>
      )}

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <h3>Gateway 状态</h3>
            <StatusBadge status={daemonStatus?.data?.running ? "ready" : gatewayStatus ? "partial" : "not_loaded"} />
          </div>
          <div className="settings-static-grid">
            <span>Daemon</span>
            <strong>{daemonStatus?.data?.running ? "running" : daemonStatus?.data ? "stopped" : "-"}</strong>
            <span>Enabled</span>
            <strong>{String(daemonStatus?.data?.enabled ?? "-")}</strong>
            <span>Listeners</span>
            <strong>{Object.keys(daemonStatus?.data?.listeners || {}).length}</strong>
            <span>Status</span>
            <strong>{compact((gatewayStatus as Record<string, unknown> | null)?.status || (gatewayStatus as Record<string, unknown> | null)?.object || "-")}</strong>
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <h3>Gateway 平台</h3>
            <StatusBadge status={platforms.length ? "ready" : "not_loaded"} />
          </div>
          <div className="mini-list">
            {platforms.map((platform, index) => {
              const name = String(platform.platform || platform.name || index);
              return (
                <article className="job-row" key={name}>
                  <div>
                    <strong>{name}</strong>
                    <span>{compact(platform.status || (platform.enabled ? "enabled" : "disabled"))}</span>
                  </div>
                  <div className="row-actions">
                    <button className="small-button" disabled={busy} onClick={() => platformAction(name, "health")} type="button">健康</button>
                    <button className="small-button" disabled={busy} onClick={() => platformAction(name, "start")} type="button">启动</button>
                    <button className="small-button" disabled={busy} onClick={() => platformAction(name, "stop")} type="button">停止</button>
                  </div>
                </article>
              );
            })}
            {!platforms.length && <p className="muted">暂无平台状态。</p>}
          </div>
        </div>

        <form className="capability-section" onSubmit={createSendIntent}>
          <div className="section-header">
            <h3>消息发送预览</h3>
            <StatusBadge status="gated" label="需审批" />
          </div>
          <label className="field-row">
            <span>平台</span>
            <input value={sendPlatform} onChange={(event) => setSendPlatform(event.target.value)} />
          </label>
          <label className="field-row">
            <span>目标</span>
            <input value={sendTarget} onChange={(event) => setSendTarget(event.target.value)} placeholder="channel/user/room" />
          </label>
          <label className="field-row">
            <span>消息</span>
            <textarea value={sendMessage} onChange={(event) => setSendMessage(event.target.value)} />
          </label>
          <button className="primary-button" disabled={busy || !sendTarget.trim() || !sendMessage.trim()} type="submit">
            <Send size={14} />
            创建发送审批
          </button>
        </form>
      </section>

      <section className="capability-section">
        <div className="section-header">
          <h3>目录与消息</h3>
          <button className="small-button" disabled={busy} onClick={refreshDirectory} type="button">刷新目录</button>
        </div>
        <div className="settings-static-grid">
          <span>目录项</span>
          <strong>{directory.length}</strong>
          <span>最近消息</span>
          <strong>{messages.length}</strong>
        </div>
        <div className="mini-list">
          {messages.slice(0, 10).map((item, index) => {
            const id = String(item.message_id || item.id || index);
            return (
              <article className="job-row" key={id}>
                <div>
                  <strong>{item.platform || id}</strong>
                  <span>{compact(item.status || item.target || item.error || "-")}</span>
                </div>
                <button className="small-button" disabled={busy || !controlToken.trim() || !id} onClick={() => retryMessage(id)} type="button">
                  <RotateCcw size={13} />
                  重试
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <details className="raw-details">
        <summary>选中详情与最近结果</summary>
        <JsonPanel value={{ selected, result, gatewayStatus, daemonStatus, messages: messages.slice(0, 10), directory: directory.slice(0, 10) }} />
      </details>
    </div>
  );
}
