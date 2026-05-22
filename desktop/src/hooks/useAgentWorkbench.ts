import type { FormEvent, KeyboardEvent } from "react";
import { useMemo, useState } from "react";
import { formatApiError, parseSseEvents, requestJson } from "../api";
import { buildTimeline } from "../components/Timeline";
import { shortText } from "../components/shared";
import { isMockEndpoint } from "../mockApi";
import type { AgentResponse, AgentToolCall, IntentRecord, InspectorTab, TaskThread, ToolEnvelope } from "../types";

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

export function useAgentWorkbench({
  endpoint,
  apiToken,
  controlToken,
  agentMode,
  userId,
  onAgentStatus,
  onInspectorTab,
  onRunEventsLoaded
}: {
  endpoint: string;
  apiToken: string;
  controlToken: string;
  agentMode: "finance_safe" | "hermes_full";
  userId?: string;
  onAgentStatus: (status: string) => void;
  onInspectorTab: (tab: InspectorTab) => void;
  onRunEventsLoaded: (events: Record<string, unknown>[]) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [threads, setThreads] = useState<TaskThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState("");
  const [intentIds, setIntentIds] = useState<string[]>([]);
  const [intentIdInput, setIntentIdInput] = useState("");
  const [intentEnvelope, setIntentEnvelope] = useState<ToolEnvelope | null>(null);
  const [intentMessage, setIntentMessage] = useState("");
  const [runEventsByRunId, setRunEventsByRunId] = useState<Record<string, unknown[]>>({});

  const selectedThread = useMemo(
    () => threads.find((item) => item.id === selectedThreadId) || threads[0] || null,
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
      metadata: { session_id: sessionId || undefined, mode: agentMode }
    };
    const optimisticThread: TaskThread = {
      id: tempId,
      title: shortText(currentPrompt, 54),
      prompt: currentPrompt,
      createdAt: new Date().toISOString(),
      status: "in_progress",
      sessionId,
      response: optimisticResponse
    };
    setThreads((items) => [optimisticThread, ...items].slice(0, 30));
    setSelectedThreadId(tempId);
    onInspectorTab("details");

    try {
      const response = await requestJson<AgentResponse>(endpoint, "/v1/responses", {
        method: "POST",
        token: agentMode === "hermes_full" ? controlToken : apiToken,
        body: {
          input: currentPrompt,
          session_id: sessionId || undefined,
          mode: agentMode,
          user_id: userId || undefined
        }
      });
      const nextThread: TaskThread = {
        ...optimisticThread,
        id: response.id,
        status: response.status,
        sessionId: response.metadata?.session_id || sessionId,
        runId: response.metadata?.run_id,
        response
      };
      onAgentStatus("AIASK_ONLINE");
      setSessionId(response.metadata?.session_id || sessionId);
      setThreads((items) => [nextThread, ...items.filter((item) => item.id !== tempId && item.id !== response.id)].slice(0, 30));
      setSelectedThreadId(response.id);

      const ids = Array.from(collectIntentIds(response));
      if (ids.length) {
        setIntentIds((items) => Array.from(new Set([...ids, ...items])).slice(0, 30));
        setIntentIdInput(ids[0]);
      }
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
                  output_text: message
                }
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
  }

  async function loadRunEvents(runId: string) {
    if (!runId) return;
    setBusy(true);
    try {
      if (isMockEndpoint(endpoint)) {
        const payload = await requestJson<{ data?: Record<string, unknown>[] }>(
          endpoint,
          `/v1/runs/${encodeURIComponent(runId)}/events`,
          {
            token: controlToken.trim() || apiToken
          }
        );
        const events = payload.data || [];
        setRunEventsByRunId((current) => ({ ...current, [runId]: events }));
        onRunEventsLoaded(events);
        return;
      }
      const response = await fetch(`${endpoint}/v1/runs/${encodeURIComponent(runId)}/events`, {
        headers: controlToken.trim()
          ? { Authorization: `Bearer ${controlToken.trim()}` }
          : apiToken.trim()
            ? { Authorization: `Bearer ${apiToken.trim()}` }
            : {}
      });
      if (!response.ok) throw new Error(`AIASK_HTTP_${response.status}`);
      const events = parseSseEvents<Record<string, unknown>>(await response.text());
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
      const envelope = await requestJson<ToolEnvelope>(endpoint, `/intents/${encodeURIComponent(intentId)}`, {
        token: apiToken
      });
      setIntentEnvelope(envelope);
      setIntentMessage(envelope.success ? "INTENT_LOADED" : envelope.error || "INTENT_ERROR");
      setIntentIds((items) => Array.from(new Set([intentId, ...items])).slice(0, 30));
    } catch (error) {
      setIntentEnvelope(null);
      setIntentMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  async function updateIntent(action: "confirm" | "deny") {
    if (!currentIntent || !controlToken.trim()) return;
    setBusy(true);
    try {
      const envelope = await requestJson<ToolEnvelope>(
        endpoint,
        `/intents/${encodeURIComponent(currentIntent.intent_id)}/${action}`,
        {
          method: "POST",
          token: controlToken,
          body: action === "deny" ? { reason: "desktop_denied" } : {}
        }
      );
      setIntentEnvelope(envelope);
      setIntentMessage(envelope.success ? `INTENT_${action.toUpperCase()}ED` : envelope.error || "INTENT_ERROR");
      await fetchIntent(currentIntent.intent_id);
    } catch (error) {
      setIntentMessage(formatApiError(error));
    } finally {
      setBusy(false);
    }
  }

  return {
    busy,
    currentIntent,
    handleComposerKeyDown,
    intentEnvelope,
    intentIdInput,
    intentIds,
    intentMessage,
    loadRunEvents,
    prompt,
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
    threads,
    timelineEvents,
    updateIntent,
    fetchIntent
  };
}
