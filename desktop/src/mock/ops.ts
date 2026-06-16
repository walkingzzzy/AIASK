export function mockLearningStatus() {
  return { object: "aiask.learning_status", status: "ready", proposal_count: 1, apply_requires_control: true };
}

export function mockLearningReview() {
  return {
    object: "list",
    data: [{ proposal_id: "learn_mock", status: "pending_review", summary: "Mock 提示词改进建议" }]
  };
}

export function mockLearningApply(body: Record<string, unknown>) {
  return { object: "learning.proposal", data: { proposal_id: body.proposal_id, status: "applied" } };
}

export function mockRlEnvironments() {
  return {
    object: "list",
    data: { environments: [{ id: "finance_safe_eval", status: "ready" }], missing_env: ["TINKER_API_KEY"] }
  };
}

export function mockRlConfig() {
  return { object: "aiask.rl_config", status: "configured", provider: "mock", secrets_redacted: true };
}

export function mockRlRunStart(body: Record<string, unknown>) {
  return { object: "rl.run", data: { run_id: "rl_mock_new", environment: body.environment || "finance_safe_eval", status: "running" } };
}

export function mockRlRunsList() {
  return { object: "list", data: [{ run_id: "rl_mock", environment: "finance_safe_eval", status: "dry_run_ready" }] };
}

export function mockRlRunGet(runId: string) {
  return { object: "rl.run", data: { run_id: runId, environment: "finance_safe_eval", status: "dry_run_ready" } };
}

export function mockRlRunArtifact(runId: string, action: string) {
  return { object: `rl.${action}`, data: { run_id: runId, status: action === "stop" ? "stopped" : "ready" } };
}

export function mockWebhooksList() {
  return {
    object: "list",
    data: [{ webhook_id: "webhook_mock", name: "Mock Webhook", events: ["MCP UI 冒烟测试"], prompt: "mock", enabled: true, status: "ready" }]
  };
}

export function mockWebhookCreate(body: Record<string, unknown>) {
  return { object: "webhook", data: { webhook_id: `webhook_mock_${Date.now()}`, ...body, enabled: true } };
}

export function mockWebhookDelete(webhookId: string) {
  return { object: "webhook.deleted", deleted: true, webhook_id: webhookId };
}

export function mockWebhookTrigger(webhookId: string) {
  return { webhook_id: webhookId, rendered: true };
}
