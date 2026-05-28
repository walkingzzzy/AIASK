import { useEffect, useState } from "react";
import { useAiSmoke } from "../../hooks/useAiSmoke";
import type { CapabilityWorkbenchPayload } from "../../types";
import { JsonPanel, StatusBadge } from "../../components/shared";

export function AiTestingPanel({
  payload,
  endpoint,
  apiToken,
  controlToken
}: {
  payload: CapabilityWorkbenchPayload | null;
  endpoint: string;
  apiToken: string;
  controlToken: string;
}) {
  const { status, result, models, message, busy, refreshStatus, runSmoke, refreshModels } = useAiSmoke(endpoint, apiToken, controlToken);
  const [prompt, setPrompt] = useState("请回复 AIASK model smoke ok。");
  const [model, setModel] = useState("");
  const currentStatus = status || payload?.ai || null;
  const runtimeMode = currentStatus?.mock ? "mock" : "live";

  useEffect(() => {
    refreshStatus().catch(() => undefined);
  }, [refreshStatus]);

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>AI 测试</span>
          <h2>{currentStatus?.model || "模型运行时"}</h2>
          <p>
            Provider {currentStatus?.provider || "-"} / {runtimeMode} / base URL{" "}
            {currentStatus?.base_url_configured ? "已配置" : "默认"}
          </p>
        </div>
        <div className="status-cluster">
          <StatusBadge status={runtimeMode === "live" ? "live_backend" : "mock_fixture"} label={runtimeMode} />
          <StatusBadge status={currentStatus?.configured ? "implemented" : "unconfigured"} />
        </div>
      </div>

      <section className="capability-grid two">
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>运行时</span>
              <h3>模型配置</h3>
            </div>
            <button className="small-button" disabled={busy} onClick={() => refreshStatus()} type="button">刷新</button>
          </div>
          <div className="kv-grid">
            <span>Provider</span>
            <strong>{currentStatus?.provider || "-"}</strong>
            <span>Model</span>
            <strong>{currentStatus?.model || "-"}</strong>
            <span>Mock 模式</span>
            <strong>{String(currentStatus?.mock ?? "-")}</strong>
            <span>模式</span>
            <strong>{runtimeMode}</strong>
            <span>Base URL</span>
            <strong>{currentStatus?.base_url_configured ? "已配置" : "默认"}</strong>
            <span>API key</span>
            <strong>{currentStatus?.api_key_configured ? "已配置" : "未配置"}</strong>
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>冒烟测试</span>
              <h3>运行 AI 冒烟测试</h3>
            </div>
            <StatusBadge status={result?.success ? "implemented" : result ? "failed" : "not_loaded"} />
          </div>
          <label className="field-row">
            <span>提示词 Prompt</span>
            <input value={prompt} onChange={(event) => setPrompt(event.target.value)} />
          </label>
          <label className="field-row">
            <span>模型覆盖</span>
            <input value={model} onChange={(event) => setModel(event.target.value)} placeholder={currentStatus?.model || "可选"} />
          </label>
          <div className="button-row">
            <button disabled={busy} onClick={() => runSmoke(prompt, model || undefined)} type="button">运行 AI 冒烟测试</button>
            <button disabled={busy} onClick={() => refreshModels()} type="button">列出模型</button>
          </div>
          <p className="status-line">{message || "就绪"}</p>
        </div>
      </section>

      <section className="capability-grid two">
        <div className="capability-section">
          <h3>冒烟测试结果</h3>
          <div className="kv-grid">
            <span>成功</span>
            <strong>{String(result?.success ?? false)}</strong>
            <span>已配置</span>
            <strong>{String(result?.configured ?? false)}</strong>
            <span>模式</span>
            <strong>{result ? (result.mock ? "mock" : "live") : "-"}</strong>
            <span>延迟</span>
            <strong>{result?.latency_ms === undefined ? "-" : `${result.latency_ms}ms`}</strong>
            <span>预览</span>
            <strong>{result?.response_preview || result?.error || "-"}</strong>
          </div>
        </div>
        <div className="capability-section">
          <h3>模型</h3>
          <div className="mini-list">
            {models.slice(0, 20).map((item) => (
              <article key={String(item.id || JSON.stringify(item))}>
                <strong>{String(item.id || "-")}</strong>
                <span>{String(item.owned_by || item.object || "model")}</span>
              </article>
            ))}
            {!models.length && <p className="muted">点击“列出模型”查看 OpenAI-compatible 模型 ID。</p>}
          </div>
        </div>
      </section>

      <details className="raw-details">
        <summary>原始 AI 诊断</summary>
        <JsonPanel value={{ status: currentStatus, result, models }} />
      </details>
    </div>
  );
}
