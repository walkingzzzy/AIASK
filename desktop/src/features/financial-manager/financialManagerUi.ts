import type { FinancialManagerAction, FinancialManagerGroup, FinancialManagerMode } from "../../types";

export function safeJsonParse(value: string): Record<string, unknown> {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
}

export function actionKey(action: Pick<FinancialManagerAction, "capability_id" | "action_id">): string {
  return `${action.capability_id}::${action.action_id}`;
}

export function modeLabel(mode?: FinancialManagerMode) {
  if (mode === "read_only") return "只读";
  if (mode === "stateful_intent") return "意图";
  if (mode === "blocked") return "禁用";
  return mode || "unknown";
}

export function groupLabel(group: FinancialManagerGroup | undefined, fallback: string) {
  return group?.label || fallback.replace(/-/g, " ");
}

export function statusDescription(action?: FinancialManagerAction | null): string {
  if (!action) return "请选择一个动作。";
  if (action.mode === "blocked") return action.blocked_reason || "该动作在当前版本禁用。";
  if (action.status === "missing_mcp_tool") return "后端 catalog 已注册此能力，但当前 Agent 没有发现对应 MCP 工具。请检查 MCP 注册、发现和授权状态。";
  if (action.status === "missing_tool") return "后端 catalog 已注册此能力，但当前 Agent 工具目录缺少对应 agent_* 工具。";
  if (action.status === "intent_ready") return "该动作会创建 ActionIntent，确认后才进入后端执行链。";
  if (action.status === "ready") return "当前 Agent 已发现执行工具，可以从桌面端发起。";
  if (action.available === false) return "当前动作暂不可用，请查看状态和工具字段。";
  return action.status || action.mode || "ready";
}

export function seedParams(action?: FinancialManagerAction | null): string {
  return JSON.stringify(action?.default_params || {}, null, 2);
}
