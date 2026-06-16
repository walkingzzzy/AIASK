import type { UserActivityEvent, UserDataPolicy } from "../types";

let mockActivityEvents: UserActivityEvent[] = [];
let mockToolInvocations: Array<Record<string, unknown>> = [];
let mockFeedbackEvents: Array<Record<string, unknown>> = [];
let mockUserDataPolicies: Record<string, UserDataPolicy> = {};

export function mockNow() {
  return "2026-06-12T00:00:00Z";
}

function redactedAuditValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactedAuditValue);
  if (!value || typeof value !== "object") return value;
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    const lowered = key.toLowerCase();
    result[key] = lowered.includes("token") || lowered.includes("secret") || lowered.includes("password") || lowered.includes("api_key")
      ? "[redacted]"
      : redactedAuditValue(item);
  }
  return result;
}

export function mockUserPolicy(userId = "local"): UserDataPolicy {
  if (!mockUserDataPolicies[userId]) {
    mockUserDataPolicies[userId] = {
      user_id: userId,
      event_ttl_days: 90,
      audit_ttl_days: 180,
      run_event_ttl_days: 180,
      tool_payload_ttl_days: 90,
      conversation_retention: "keep_until_user_deletes",
      allow_product_analytics: true,
      allow_learning: false,
      updated_at: mockNow()
    };
  }
  return mockUserDataPolicies[userId];
}

export function mockUpdateUserPolicy(userId: string, body: Record<string, unknown>) {
  mockUserDataPolicies[userId] = { ...mockUserPolicy(userId), ...body, user_id: userId, updated_at: mockNow() };
  return mockUserDataPolicies[userId];
}

export function mockActivityEventsData() {
  return mockActivityEvents;
}

export function mockToolInvocationsData() {
  return mockToolInvocations;
}

export function mockFeedbackEventsData() {
  return mockFeedbackEvents;
}

export function mockRecordToolInvocation(tool: string, body: Record<string, unknown>, defaultUserId: string) {
  const item = {
    id: mockToolInvocations.length + 1,
    invocation_id: `tool_mock_${mockToolInvocations.length + 1}`,
    user_id: String(body.user_id || defaultUserId || "local"),
    session_id: body.session_id || "sess_mock",
    run_id: body.run_id || null,
    trace_id: body.trace_id || `trace_mock_${mockToolInvocations.length + 1}`,
    tool_name: tool,
    status: "succeeded",
    input_summary: redactedAuditValue(body),
    output_summary: { success: true },
    duration_ms: 5,
    source_chain: ["desktop.mockApi"],
    secrets_redacted: true,
    created_at: mockNow(),
    updated_at: mockNow()
  };
  mockToolInvocations = [item, ...mockToolInvocations].slice(0, 100);
}

export function mockCreateActivityEvents(body: Record<string, unknown>, defaultUserId: string) {
  const rawEvents = Array.isArray(body.events) ? body.events : [body];
  const events = rawEvents
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item)))
    .map((item, index) => ({
      id: mockActivityEvents.length + index + 1,
      user_id: String(item.user_id || defaultUserId || "local"),
      session_id: item.session_id ? String(item.session_id) : "sess_mock",
      run_id: item.run_id ? String(item.run_id) : null,
      trace_id: item.trace_id ? String(item.trace_id) : `trace_mock_event_${mockActivityEvents.length + index + 1}`,
      page_key: item.page_key ? String(item.page_key) : null,
      route: item.route ? String(item.route) : null,
      event_type: String(item.event_type || "event"),
      target_type: item.target_type ? String(item.target_type) : null,
      target_id: item.target_id ? String(item.target_id) : null,
      target_label: item.target_label ? String(item.target_label) : null,
      target_testid: item.target_testid ? String(item.target_testid) : null,
      payload: redactedAuditValue(item.payload || {}) as Record<string, unknown>,
      source: String(item.source || "desktop.mock"),
      created_at: mockNow()
    }));
  mockActivityEvents = [...events, ...mockActivityEvents].slice(0, 200);
  return { object: "list", data: events, count: events.length, secrets_redacted: true };
}

export function mockCreateFeedback(body: Record<string, unknown>, defaultUserId: string) {
  const feedback = {
    id: mockFeedbackEvents.length + 1,
    feedback_id: String(body.feedback_id || `feedback_mock_${mockFeedbackEvents.length + 1}`),
    user_id: String(body.user_id || defaultUserId || "local"),
    session_id: body.session_id || "sess_mock",
    run_id: body.run_id || null,
    target_type: String(body.target_type || "page"),
    target_id: body.target_id || null,
    feedback_type: String(body.feedback_type || "thumbs_up"),
    rating: body.rating ?? null,
    comment: body.comment || null,
    allow_learning: Boolean(body.allow_learning),
    payload: redactedAuditValue(body.payload || {}),
    created_at: mockNow()
  };
  mockFeedbackEvents = [feedback, ...mockFeedbackEvents].slice(0, 100);
  return { object: "aiask.feedback", data: feedback, secrets_redacted: true };
}

export function mockDeleteUserState(userId: string) {
  mockActivityEvents = mockActivityEvents.filter((event) => event.user_id !== userId);
  mockToolInvocations = mockToolInvocations.filter((item) => item.user_id !== userId);
  mockFeedbackEvents = mockFeedbackEvents.filter((item) => item.user_id !== userId);
}
