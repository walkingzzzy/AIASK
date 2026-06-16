import { type Route } from "@playwright/test";
import { settingsStatusPayload } from "./capabilitiesMockCorePayloads";
import { runEventsPayload, workbenchSummaryPayload } from "./capabilitiesMockDesktopFixtures";

type MockRequest = ReturnType<Route["request"]>;
type FulfillJson = (route: Route, payload: unknown, status?: number) => Promise<void>;

interface DesktopGovernanceRouteContext {
  route: Route;
  request: MockRequest;
  url: URL;
  path: string;
  authorized: boolean;
  fulfillJson: FulfillJson;
}

export async function handleDesktopGovernanceRoutes({
  route,
  request,
  url,
  path,
  authorized,
  fulfillJson,
}: DesktopGovernanceRouteContext) {
  const handled = async (payload: unknown, status?: number) => {
    await fulfillJson(route, payload, status);
    return true;
  };
  if (path === "/v1/desktop/events") {
    const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
    const events = Array.isArray(body.events) ? body.events : [];
    return handled({
      object: "list",
      data: events.map((event: Record<string, unknown>, index: number) => ({
        id: `event_${index + 1}`,
        recorded_at: "2026-06-12T00:00:00.000Z",
        ...event,
        payload: event.payload || {},
      })),
      count: events.length,
      secrets_redacted: true,
    });
  }
  if (path === "/v1/desktop/feedback") {
    const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
    return handled({
      object: "aiask.feedback",
      data: {
        feedback_id: "feedback_e2e",
        user_id: body.user_id || "local-e2e",
        session_id: body.session_id || "session_fixture",
        target_type: body.target_type || "page",
        target_id: body.target_id || "workbench",
        feedback_type: body.feedback_type || "thumbs_up",
        rating: body.rating ?? 5,
        allow_learning: body.allow_learning === true,
        payload: {},
        created_at: "2026-06-12T00:00:00.000Z"
      },
      secrets_redacted: true
    });
  }
  if (path === "/v1/desktop/analytics/summary") {
    const userId = url.searchParams.get("user_id");
    return handled({
      object: "aiask.analytics_summary",
      scope: userId ? "user" : "aggregate",
      user_id: userId || null,
      totals: { events: 1, tool_invocations: 1, feedback: 1 },
      events_by_type: [{ event_type: "page_view", count: 1 }],
      pages: [{ page_key: "workbench", count: 1 }],
      tools: [{ tool_name: "agent_tool_catalog", count: 1, succeeded: 1, failed: 0, failure_rate: 0, avg_duration_ms: 5 }],
      feedback: [{ target_type: "page", feedback_type: "thumbs_up", count: 1, avg_rating: 5 }],
      secrets_redacted: true
    });
  }
  if (path === "/v1/desktop/retention/sweep") {
    const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
    return handled({
      object: "aiask.retention_sweep",
      dry_run: body.dry_run !== false,
      user_id: body.user_id || null,
      counts: { user_activity_events: 0, tool_invocations_payloads: 0, run_events: 0, feedback_events: 0, messages: 0 },
      tables: ["user_activity_events", "tool_invocations_payloads", "run_events", "feedback_events", "messages"],
      market_data_affected: false,
      secrets_redacted: true
    });
  }
  if (path === "/v1/desktop/runs") {
    return handled({ object: "list", data: workbenchSummaryPayload().recent_runs });
  }
  if (path === "/v1/desktop/settings/status") {
    return handled(settingsStatusPayload(authorized));
  }
  const userActivityMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/activity$/);
  if (userActivityMatch) {
    const userId = decodeURIComponent(userActivityMatch[1]);
    return handled({
      object: "aiask.user_activity",
      user_id: userId,
      sessions: workbenchSummaryPayload().recent_sessions,
      runs: workbenchSummaryPayload().recent_runs,
      events: [
        {
          id: "activity_page_view",
          user_id: userId,
          page_key: "workbench",
          event_type: "page_view",
          source: "desktop.e2e",
          created_at: "2026-06-12T00:00:00.000Z",
        },
      ],
      tool_invocations: [],
      feedback: [],
      policy: {
        user_id: userId,
        event_ttl_days: 30,
        audit_ttl_days: 90,
        run_event_ttl_days: 90,
        tool_payload_ttl_days: 14,
        conversation_retention: "local",
        allow_product_analytics: false,
        allow_learning: true,
        updated_at: "2026-06-12T00:00:00.000Z",
      },
      secrets_redacted: true,
    });
  }
  const userExportMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/export$/);
  if (userExportMatch) {
    const userId = decodeURIComponent(userExportMatch[1]);
    return handled({
      object: "aiask.user_data_export",
      user_id: userId,
      exported_at: "2026-06-12T00:00:00.000Z",
      profile_policy: {
        user_id: userId,
        event_ttl_days: 30,
        audit_ttl_days: 90,
        run_event_ttl_days: 90,
        tool_payload_ttl_days: 14,
        conversation_retention: "local",
        allow_product_analytics: false,
        allow_learning: true,
        updated_at: "2026-06-12T00:00:00.000Z"
      },
      sessions: workbenchSummaryPayload().recent_sessions,
      messages: [{ message_id: "msg_fixture", role: "assistant", content: "AIASK_OK" }],
      runs: workbenchSummaryPayload().recent_runs,
      run_events: runEventsPayload().data,
      activity_events: [{ id: "activity_page_view", user_id: userId, page_key: "workbench", event_type: "page_view", payload: {}, created_at: "2026-06-12T00:00:00.000Z" }],
      tool_invocations: [{ invocation_id: "tool_e2e", tool_name: "agent_tool_catalog", status: "succeeded", secrets_redacted: true }],
      feedback: [{ feedback_id: "feedback_e2e", target_type: "page", feedback_type: "thumbs_up", allow_learning: true }],
      sources: [],
      artifacts: [],
      analytics: {
        object: "aiask.analytics_summary",
        scope: "user",
        user_id: userId,
        totals: { events: 1, tool_invocations: 1, feedback: 1 },
        events_by_type: [{ event_type: "page_view", count: 1 }],
        pages: [{ page_key: "workbench", count: 1 }],
        tools: [{ tool_name: "agent_tool_catalog", count: 1, succeeded: 1, failed: 0, failure_rate: 0, avg_duration_ms: 5 }],
        feedback: [{ target_type: "page", feedback_type: "thumbs_up", count: 1, avg_rating: 5 }],
        secrets_redacted: true
      },
      secrets_redacted: true
    });
  }
  const userDeleteMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/delete$/);
  if (userDeleteMatch) {
    const userId = decodeURIComponent(userDeleteMatch[1]);
    const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
    return handled({
      object: "aiask.user_data_delete",
      user_id: userId,
      dry_run: body.dry_run !== false,
      hard_delete: body.hard_delete === true,
      anonymized_user_id: body.hard_delete === true ? null : `deleted:${userId}`,
      counts: { sessions: 1, messages: 1, responses: 1, runs: 1, run_events: 5, activity_events: 1, tool_invocations: 1, feedback: 1, sources: 0, artifacts: 0, search_rows: 0 },
      external_side_effects: "not_rolled_back",
      secrets_redacted: true
    });
  }
  const userLearningMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/learning-dataset$/);
  if (userLearningMatch) {
    const userId = decodeURIComponent(userLearningMatch[1]);
    return handled({
      object: "aiask.learning_dataset",
      user_id: userId,
      allowed: true,
      items: [{ kind: "feedback", target_type: "page", feedback_type: "thumbs_up", rating: 5, created_at: "2026-06-12T00:00:00.000Z" }],
      count: 1,
      secrets_redacted: true
    });
  }
  const userRecommendationsMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/recommendations$/);
  if (userRecommendationsMatch) {
    const userId = decodeURIComponent(userRecommendationsMatch[1]);
    return handled({
      object: "aiask.workflow_recommendations",
      user_id: userId,
      data_source: "local_user_activity",
      data: [{ id: "feedback:collect", kind: "feedback_collection", priority: "medium", title: "Collect explicit feedback", reason: "E2E recommendation." }],
      count: 1,
      secrets_redacted: true
    });
  }
  const userPolicyMatch = path.match(/^\/v1\/desktop\/users\/([^/]+)\/data-policy$/);
  if (userPolicyMatch) {
    const userId = decodeURIComponent(userPolicyMatch[1]);
    const body = request.postData() ? JSON.parse(request.postData() || "{}") : {};
    return handled({
      object: "aiask.user_data_policy",
      data: {
        user_id: userId,
        event_ttl_days: body.event_ttl_days ?? 30,
        audit_ttl_days: body.audit_ttl_days ?? 90,
        run_event_ttl_days: body.run_event_ttl_days ?? 90,
        tool_payload_ttl_days: body.tool_payload_ttl_days ?? 14,
        conversation_retention: body.conversation_retention || "local",
        allow_product_analytics: body.allow_product_analytics ?? false,
        allow_learning: body.allow_learning ?? true,
        updated_at: "2026-06-12T00:00:00.000Z",
      },
      secrets_redacted: true,
    });
  }

  return false;
}
