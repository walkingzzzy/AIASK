export function mockGatewayStatus() {
  return { object: "aiask.gateway_status", status: "ready", enabled_platforms: ["desktop"], pending_messages: 0 };
}

export function mockGatewayDaemonStatus() {
  return { object: "gateway.daemon", data: { enabled: true, running: true, listeners: { desktop: { status: "ready" } } } };
}

export function mockGatewayPlatforms() {
  return { object: "list", data: [{ platform: "desktop", status: "ready" }, { platform: "discord", status: "missing_credentials" }] };
}

export function mockGatewayPlatformAction(platform: string, action: string) {
  return { object: "gateway.platform", data: { platform, status: action === "stop" ? "stopped" : "ready" } };
}

export function mockGatewayMessages(userId: string) {
  return {
    object: "list",
    data: [
      { message_id: "msg_gateway_mock", platform: "desktop", status: "delivered", user_id: userId },
      {
        message_id: "msg_gateway_failed",
        platform: "discord",
        target: "ops-alerts",
        status: "failed",
        content: "Mock Gateway 投递失败",
        error_message: "missing DISCORD_BOT_TOKEN",
        retry_count: 1,
        created_at: "2026-05-22T09:00:00Z"
      }
    ]
  };
}

export function mockGatewayRetry(messageId: string) {
  return { object: "gateway.retry", data: { message_id: messageId, status: "queued" } };
}

export function mockGatewayDirectory(userId: string, profileName: string) {
  return { object: "list", data: [{ platform: "desktop", kind: "user", id: userId, display_name: profileName }] };
}

export function mockGatewayDirectoryRefresh(userId: string) {
  return { object: "gateway.directory_refresh", data: [{ platform: "desktop", kind: "user", id: userId }] };
}
