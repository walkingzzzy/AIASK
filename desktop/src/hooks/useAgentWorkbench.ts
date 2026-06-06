import type { FormEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { formatApiError } from "../api";
import { buildTimeline } from "../components/Timeline";
import { shortText } from "../components/shared";
import { AiaskApi } from "../services/aiaskApi";
import type {
  AgentResponse,
  AgentToolCall,
  DesktopRunSummary,
  DesktopWorkbenchSummary,
  IntentRecord,
  InspectorTab,
  NormalizedRunEvent,
  TaskThread,
  ToolEnvelope,
} from "../types";

function collectIntentIds(value: unknown, bucket = new Set<string>()): Set<string> {
  if (!value || typeof value !== "object") return bucket;
  if (Array.isArray(value)) {
    value.forEach((item) => collectIntentIds(item, bucket));
    return bucket;
  }
  const record = value as Record<string, unknown>;
  for (const key of ["intent_id", "action_id"]) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.startsWith("intent_")) {
      bucket.add(candidate);
    }
  }
  Object.values(record).forEach((item) => collectIntentIds(item, bucket));
  return bucket;
}

function contentText(value: unknown): string {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  const record = value as Record<string, unknown>;
  return String(record.content || record.text || record.output_text || "");
}

function threadFromSummary(session: DesktopWorkbenchSummary["recent_sessions"][number]): TaskThread {
  const sessionId = String(session.session_id || "");
  return {
    id: sessionId,
    title: String(session.title || sessionId || "最近会话"),
    prompt: String(session.title || "点击加载最近会话"),
    createdAt: String(session.last_message_at || new Date().toISOString()),
    status: String(session.status || "summary"),
    sessionId,
    runId: session.last_run_id || undefined,
    lastMessageAt: session.last_message_at || undefined,
  };
}

export function useAgentWorkbench({
  endpoint,
  apiToken,
  controlToken,
  agentMode,
  canLoadHistory = true,
  userId,
  onAgentStatus,
  onInspectorTab,
  onRunEventsLoaded,
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  agentMode: "finance_safe" | "hermes_full";
  canLoadHistory?: boolean;
  userId?: string;
  onAgentStatus: (status: string) => void;
  onInspectorTab: (tab: InspectorTab) => void;
  onRunEventsLoaded: (events: NormalizedRunEvent[]) => void;
}) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [threads, setThreads] = useState<TaskThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState("");
  const [intentIds, setIntentIds] = useState<string[]>([]);
  const [intentIdInput, setIntentIdInput] = useState("");
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [intentMessage, setIntentMessage] = useState("");
  const [runEventsByRunId, setRunEventsByRunId] = useState<Record<string, NormalizedRunEvent[]>>({});
  const [summary, setSummary] = useState<DesktopWorkbenchSummary | null>(null);
  const [recentRuns, setRecentRuns] = useState<DesktopRunSummary[]>([]);

  const selectedThread = useMemo(
    () => (selectedThreadId ? threads.find((item) => item.id === selectedThreadId) || null : null),
    [threads, selectedThreadId]
  );
  const selectedResponse = selectedThread?.response || null;
  const selectedRunId = selectedResponse?.metadata?.run_id || selectedThread?.runId || "";
  const timelineEvents = useMemo(
    () => buildTimeline(selectedThread, selectedRunId ? runEventsByRunId[selectedRunId] || [] : []),
    [selectedRunId, runEventsByRunId, selectedThread]
  );
  const currentIntent = ((intentEnvelope?.data as { intent?: IntentRecord } | undefined)?.intent || null) as IntentRecord | null;
  const selectedResponseRecord = selectedResponse as (AgentResponse & {
    model?: string;
    usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
    metadata?: AgentResponse["metadata"] & { tool_calls?: AgentToolCall[] };
  }) | null;
  const selectedAuditEventCount = selectedResponse?.metadata?.audit_events?.length ?? 0;

  async function refreshSummary() {
    if (!canLoadHistory) return null;
    try {
      const payload = await api.workbenchSummary();
      setSummary(payload);
      setRecentRuns(payload.recent_runs || []);
      setThreads((current) => {
        const hydrated = current.filter((item) => item.response || item.status === "in_progress");
        const bySession = new Set(hydrated.map((item) => item.sessionId || item.id));
        const summaryThreads = (payload.recent_sessions || [])
          .map(threadFromSummary)
          .filter((item) => !bySession.has(item.sessionId || item.id));
        return [...hydrated, ...summaryThreads].slice(0, 50);
      });
      return payload;
    } catch (error) {
      onAgentStatus(formatApiError(error));
      return null;
    }
  }

  async function hydrateThread(id: string) {
    const thread = threads.find((item) => item.id === id);
    const sid = thread?.sessionId || id;
    if (!sid || thread?.response) return;
    try {
      const payload = await api.sessionMessages(sid, 200);
      const messages = payload.data || [];
      const firstUser = messages.find((item) => String(item.role) === "user");
      const assistantMessages = messages.filter((item) => String(item.role) === "assistant");
      const lastAssistant = assistantMessages[assistantMessages.length - 1];
      const output = messages
        .slice(-8)
        .map((item) => `${String(item.role || "message")}: ${contentText(item.payload || item)}`)
        .join("\n\n");
      const response: AgentResponse = {
        id: `history_${sid}`,
        object: "response",
        status: "completed",
        output_text: contentText(lastAssistant?.payload || lastAssistant) || output || "历史会话已加载。",
        metadata: { session_id: sid, run_id: thread?.runId },
      };
      setThreads((items) =>
        items.map((item) =>
          item.id === id
            ? {
                ...item,
                prompt: contentText(firstUser?.payload || firstUser) || item.prompt,
                response,
                status: "completed",
              }
            : item
        )
      );
      setSessionId(sid);
    } catch (error) {
      onAgentStatus(formatApiError(error));
    }
  }

  async function sendResponse(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim()) return;

    const currentPrompt = prompt.trim();
    setPrompt("");
    setBusy(true);

    const tempId = `task_${Date.now()}`;
    const optimisticResponse: AgentResponse = {
      id: tempId,
      object: "response",
      status: "in_progress",
      output_text: "Working...",
      metadata: { session_id: sessionId || undefined, mode: agentMode },
    };
    const optimisticThread: TaskThread = {
      id: tempId,
      title: shortText(currentPrompt, 54),
      prompt: currentPrompt,
      createdAt: new Date().toISOString(),
      status: "in_progress",
      sessionId,
      response: optimisticResponse,
    };
    setThreads((items) => [optimisticThread, ...items.filter((item) => item.id !== tempId)].slice(0, 50));
    setSelectedThreadId(tempId);
    onInspectorTab("details");

    try {
      const response = await api.response(
        {
          input: currentPrompt,
          session_id: sessionId || undefined,
          mode: agentMode,
          user_id: userId || undefined,
        },
        agentMode === "hermes_full" ? controlToken : apiToken
      );
      const nextThread: TaskThread = {
        ...optimisticThread,
        id: response.id,
        status: response.status,
        sessionId: response.metadata?.session_id || sessionId,
        runId: response.metadata?.run_id,
        response,
      };
      onAgentStatus("AIASK_ONLINE");
      setSessionId(response.metadata?.session_id || sessionId);
      setThreads((items) => [nextThread, ...items.filter((item) => item.id !== tempId && item.id !== response.id)].slice(0, 50));
      setSelectedThreadId(response.id);
      const ids = Array.from(collectIntentIds(response));
      if (ids.length) {
        setIntentIds((items) => Array.from(new Set([...ids, ...items])).slice(0, 50));
        setIntentIdInput(ids[0]);
      }
      await refreshSummary();
    } catch (error) {
      const message = formatApiError(error);
      onAgentStatus(message);
      setThreads((items) =>
        items.map((item) =>
          item.id === tempId
            ? {
                ...item,
                status: "failed",
                response: {
                  ...optimisticResponse,
                  status: "failed",
                  output_text: message,
                },
              }
            : item
        )
      );
    } finally {
      setBusy(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function startNewTask() {
    setSelectedThreadId("");
    setPrompt("");
    onInspectorTab("details");
  }

  function selectThread(id: string) {
    setSelectedThreadId(id);
    onInspectorTab("details");
    void hydrateThread(id);
  }

  function removeResponseThread(responseId: string) {
    setThreads((items) => items.filter((item) => item.id !== responseId && item.response?.id !== responseId));
    setSelectedThreadId((current) => {
      const currentThread = threads.find((item) => item.id === current);
      if (current === responseId || currentThread?.response?.id === responseId) return "";
      return current;
    });
  }

  useEffect(() => {
    if (!canLoadHistory) return;
    refreshSummary().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canLoadHistory, endpoint, apiToken, userId]);

  async function loadRunEvents(runId: string) {
    if (!runId) return;
    setBusy(true);
    try {
      const events = await api.runEvents(runId, controlToken.trim() || apiToken);
      setRunEventsByRunId((current) => ({ ...current, [runId]: events }));
      onRunEventsLoaded(events);
    } catch (error) {
      onAgentStatus(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function fetchIntent(id = intentIdInput) {
    const intentId = id.trim();
    if (!intentId) return;
    setBusy(true);
    onInspectorTab("intents");
    try {
      const envelope = await api.getIntent(intentId);
      setIntentEnvelope(envelope);
      setIntentMessage(envelope.success ? "INTENT_LOADED" : envelope.error || "INTENT_ERROR");
      setIntentIds((items) => Array.from(new Set([intentId, ...items])).slice(0, 50));
    } catch (error) {
      setIntentEnvelope(null);
      setIntentMessage(formatApiError(error));
    }
    setBusy(false);
  }

  async function updateIntent(action: "confirm" | "deny") {
    if (!currentIntent || !controlToken.trim()) return;
    setBusy(true);
    try {
      const envelope =
        action === "confirm"
          ? await api.confirmIntent(currentIntent.intent_id)
          : await api.denyIntent(currentIntent.intent_id, "desktop_denied");
      setIntentEnvelope(envelope);
      setIntentMessage(envelope.success ? `INTENT_${action.toUpperCase()}ED` : envelope.error || "INTENT_ERROR");
      await fetchIntent(currentIntent.intent_id);
      await refreshSummary();
    } catch (error) {
      setIntentMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return {
    busy,
    currentIntent,
    fetchIntent,
    handleComposerKeyDown,
    intentEnvelope,
    intentIdInput,
    intentIds,
    intentMessage,
    loadRunEvents,
    prompt,
    recentRuns,
    refreshSummary,
    removeResponseThread,
    selectThread,
    selectedAuditEventCount,
    selectedResponse,
    selectedResponseRecord,
    selectedRunId,
    selectedThread,
    selectedThreadId,
    sendResponse,
    sessionId,
    setIntentIdInput,
    setPrompt,
    setSelectedThreadId,
    setSessionId,
    startNewTask,
    summary,
    threads,
    timelineEvents,
    updateIntent,
  };
}
