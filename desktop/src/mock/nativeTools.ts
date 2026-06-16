export function mockProcesses() {
  return { object: "list", data: [{ pid: "mock-agent", name: "AIASK Agent Mock", status: "running", source: "desktop.mockApi" }] };
}

export function mockBrowserSessions() {
  return { object: "list", data: [{ name: "default", provider: "playwright", persistent: true, status: "ready" }] };
}

export function mockTerminalBackends() {
  return { object: "list", data: [{ name: "local-powershell", shell: "powershell", status: "ready", read_only_probe: true }] };
}

export function mockTerminalBackendSessions(backend: string, userId: string, limit: number) {
  return {
    object: "list",
    backend,
    data: [
      {
        session_id: "terminal_mock",
        backend,
        status: "idle",
        user_id: userId,
        shell: backend.includes("powershell") ? "powershell" : "terminal",
        updated_at: "2026-05-22T09:00:00Z"
      }
    ].slice(0, limit)
  };
}

export function mockTerminalSessions(userId: string) {
  return { object: "list", data: [{ session_id: "terminal_mock", backend: "local-powershell", status: "idle", user_id: userId }] };
}
