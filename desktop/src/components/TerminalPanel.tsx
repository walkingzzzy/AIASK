import { Play, TerminalSquare, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button, EmptyState, JsonPanel, StatusBadge } from "./ui";
import { dataObject, list, valueOf } from "../pages/pageUtils";
import type { ApiProblem, UnknownRecord } from "../types";

type TerminalHistoryItem = {
  id: string;
  command: string;
  stdout: string;
  stderr: string;
  returncode: number | null;
  timedOut: boolean;
  classification: string;
  hint: string;
  backend: string;
  createdAt: string;
  sessionId: string;
};

function displayTime(value: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function classifyTerminalResult(payload: UnknownRecord) {
  const stderr = String(payload.stderr || "");
  const stdout = String(payload.stdout || "");
  const returncode = payload.returncode === undefined || payload.returncode === null ? null : Number(payload.returncode);
  const timedOut = Boolean(payload.timed_out || payload.timeout || payload.timedOut);
  const combined = `${stderr}\n${stdout}`.toLowerCase();

  if (timedOut) {
    return {
      classification: "timeout",
      hint: "命令超过 Agent 超时时间。请缩小命令范围，或减少输出内容后重试。"
    };
  }
  if (combined.includes("permission denied") || combined.includes("access is denied") || combined.includes("control token") || combined.includes("unauthorized")) {
    return {
      classification: "permission",
      hint: "Agent 或操作系统拒绝访问。请检查完整模式、控制权限和路径权限。"
    };
  }
  if (returncode !== null && returncode !== 0) {
    return {
      classification: "command_failed",
      hint: "命令返回了非零退出码。请查看错误输出并调整命令。"
    };
  }
  return {
    classification: returncode === null ? "background" : "completed",
    hint: returncode === null ? "命令已作为后台进程接收。" : "命令已成功完成。"
  };
}

function terminalClassificationLabel(classification: string) {
  const labels: Record<string, string> = {
    timeout: "超时",
    permission: "权限不足",
    command_failed: "命令失败",
    background: "后台运行",
    completed: "已完成"
  };
  return labels[classification] || classification;
}

export function TerminalPanel({
  visible,
  controlAvailable,
  backends,
  sessions,
  loading,
  error,
  onRefresh,
  onExecute
}: {
  visible: boolean;
  controlAvailable: boolean;
  backends: unknown;
  sessions: unknown;
  loading: boolean;
  error: ApiProblem | null;
  onRefresh: () => void;
  onExecute: (payload: { command: string; backend: string; session_id?: string }) => Promise<unknown>;
}) {
  const backendRows = list<UnknownRecord>(backends);
  const sessionRows = list<UnknownRecord>(sessions);
  const [command, setCommand] = useState("pwd");
  const [backend, setBackend] = useState("local");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<TerminalHistoryItem[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);

  useEffect(() => {
    if (!backendRows.length) return;
    const current = backendRows.find((item) => String(item.name || "").toLowerCase() === backend.toLowerCase());
    if (!current) {
      setBackend(String(backendRows[0].name || "local"));
    }
  }, [backend, backendRows]);

  const activeSession = useMemo(() => {
    const selected = sessionRows.find((item) => String(item.backend || "").toLowerCase() === backend.toLowerCase());
    return selected || sessionRows[0] || null;
  }, [backend, sessionRows]);

  async function runCommand(input: string) {
    if (!input.trim()) return;
    setBusy(true);
    try {
      const result = await onExecute({
        command: input.trim(),
        backend,
        session_id: String(activeSession?.session_id || activeSession?.id || "")
      });
      const payload = dataObject(result, {});
      const classified = classifyTerminalResult(payload);
      const record: TerminalHistoryItem = {
        id: String(payload.process_id || payload.id || `terminal_${Date.now()}`),
        command: input.trim(),
        stdout: String(payload.stdout || ""),
        stderr: String(payload.stderr || ""),
        returncode: payload.returncode === undefined || payload.returncode === null ? null : Number(payload.returncode),
        timedOut: Boolean(payload.timed_out || payload.timeout || payload.timedOut),
        classification: classified.classification,
        hint: classified.hint,
        backend: String(payload.backend || backend),
        createdAt: new Date().toISOString(),
        sessionId: String(payload.session_id || activeSession?.session_id || "")
      };
      setHistory((current) => [record, ...current].slice(0, 20));
      setLastResult(result);
      setCursor(null);
    } finally {
      setBusy(false);
    }
  }

  function moveHistory(direction: "up" | "down") {
    if (!history.length) return;
    if (direction === "up") {
      const nextIndex = cursor === null ? 0 : Math.min(cursor + 1, history.length - 1);
      setCursor(nextIndex);
      setCommand(history[nextIndex].command);
      return;
    }
    if (cursor === null) return;
    const nextIndex = cursor - 1;
    if (nextIndex < 0) {
      setCursor(null);
      setCommand("");
      return;
    }
    setCursor(nextIndex);
    setCommand(history[nextIndex].command);
  }

  if (!visible) return null;

  return (
    <section className="panel terminal-panel" data-testid="terminal-panel">
      <div className="panel-header">
        <div>
          <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TerminalSquare size={18} />
            终端
          </h2>
          <p style={{ margin: "6px 0 0", color: "var(--text-muted)" }}>
            通过 Agent 完整模式管理工具执行受控命令。
          </p>
        </div>
        <div className="page-actions">
          <StatusBadge tone={controlAvailable ? "success" : "gated"}>
            {controlAvailable ? "完整控制已就绪" : "需要控制权限"}
          </StatusBadge>
          <Button onClick={onRefresh} busy={loading}>
            刷新
          </Button>
        </div>
      </div>

      <div className="terminal-toolbar">
        <label className="field">
          <span>执行后端</span>
          <select value={backend} onChange={(event) => setBackend(event.target.value)}>
            {backendRows.map((item) => (
              <option key={String(item.name || "local")} value={String(item.name || "local")}>
                {String(item.name || "local")}
              </option>
            ))}
          </select>
        </label>
        <label className="field terminal-command-field">
          <span>命令</span>
          <input
            data-testid="terminal-command-input"
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void runCommand(command);
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                moveHistory("up");
              }
              if (event.key === "ArrowDown") {
                event.preventDefault();
                moveHistory("down");
              }
            }}
            placeholder="通过 agent_terminal 执行安全命令"
          />
        </label>
        <div className="page-actions terminal-actions">
          <Button
            data-testid="terminal-run-command"
            icon={<Play size={16} />}
            tone="success"
            disabled={!controlAvailable || !command.trim()}
            busy={busy}
            onClick={() => void runCommand(command)}
          >
            运行
          </Button>
          <Button
            icon={<Trash2 size={16} />}
            disabled={!history.length}
            onClick={() => {
              setHistory([]);
              setLastResult(null);
              setCursor(null);
            }}
          >
            清空
          </Button>
        </div>
      </div>

      {error ? (
        <div className="state state-error" role="alert">
          <strong>{error.title}</strong>
          <p>{error.detail}</p>
        </div>
      ) : null}

      <div className="terminal-layout">
        <div className="terminal-output">
          {history.length ? (
            history.map((item) => (
              <article className="terminal-output-card" key={item.id}>
                <div className="terminal-output-head">
                  <strong>{item.command}</strong>
                  <StatusBadge tone={item.returncode === 0 || item.returncode === null ? "success" : "danger"}>
                    {item.returncode === null ? "后台运行" : `退出码 ${item.returncode}`}
                  </StatusBadge>
                  <StatusBadge tone={item.classification === "completed" || item.classification === "background" ? "success" : item.classification === "permission" ? "gated" : "warning"}>
                    {terminalClassificationLabel(item.classification)}
                  </StatusBadge>
                </div>
                <div className="terminal-output-meta">
                  <span>{item.backend}</span>
                  <span>{displayTime(item.createdAt)}</span>
                </div>
                <pre className="terminal-output-block">{item.stdout || item.stderr || "（无输出）"}</pre>
                {item.stderr && item.stdout ? <pre className="terminal-output-block error">{item.stderr}</pre> : null}
                <p style={{ margin: "0.5rem 0 0", color: "var(--text-muted)", fontSize: 12 }}>{item.hint}</p>
              </article>
            ))
          ) : (
            <EmptyState
              title="暂无终端输出"
              detail="运行命令后会生成历史记录。可用上下方向键复用最近命令。"
            />
          )}
        </div>

        <div className="terminal-side">
          <div className="rail-card">
            <span className="rail-card-title">执行后端</span>
            <strong>{backendRows.length || 0} 个可用</strong>
            <p>
              {backendRows.length
                ? backendRows.map((item) => String(item.name || "local")).join(", ")
                : "Agent 尚未返回可用后端。"}
            </p>
          </div>

          <div className="rail-card">
            <span className="rail-card-title">受管会话</span>
            <strong>{sessionRows.length}</strong>
            <p>{activeSession ? `当前会话：${valueOf(activeSession, ["session_id", "id"], "-")}` : "暂无活跃终端会话。"}</p>
          </div>

          <JsonPanel
            title="终端证据"
            data={{
              backend_rows: backendRows,
              session_rows: sessionRows,
              last_result: lastResult
            }}
          />
        </div>
      </div>
    </section>
  );
}
