import { RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { formatApiError } from "../../api";
import { JsonPanel, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";

export function SecurityPanel({ apiToken, controlToken, endpoint }: { apiToken: string; controlToken: string; endpoint: string }) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [path, setPath] = useState(".");
  const [text, setText] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [message, setMessage] = useState("NOT_RUN");
  const [busy, setBusy] = useState(false);

  async function scan(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = await api.hermesToolCall("agent_security_scan", text.trim() ? { text } : { path, include_env: false });
      setResult(payload);
      setMessage(payload.success ? "SECURITY_SCAN_COMPLETED" : payload.error || "SECURITY_SCAN_FAILED");
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
          <ShieldCheck size={20} />
          <span>安全扫描</span>
          <h2>安全扫描与修复建议</h2>
          <p>扫描默认不包含环境变量内容，避免泄露本地密钥。</p>
        </div>
        <StatusBadge status={message.startsWith("AIASK_") ? "gated" : "ready"} label={message} />
      </div>
      <form className="capability-section" onSubmit={scan}>
        <label className="field-row">
          <span>路径</span>
          <input value={path} onChange={(event) => setPath(event.target.value)} />
        </label>
        <label className="field-row">
          <span>文本片段</span>
          <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="可选；填写后扫描文本而不是路径" />
        </label>
        <button className="primary-button" disabled={busy || (!path.trim() && !text.trim())} type="submit">
          <RefreshCw size={14} className={busy ? "spin" : ""} />
          运行扫描
        </button>
      </form>
      <details className="raw-details" open>
        <summary>扫描结果</summary>
        <JsonPanel value={result || { status: "not_run" }} />
      </details>
    </div>
  );
}
