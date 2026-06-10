import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SecurityPanel } from "./SecurityPanel";

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

describe("SecurityPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("runs text scans with env disabled and redacts scan input echoed in raw results", async () => {
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init: init || {} });
      return jsonResponse({
        success: true,
        data: {
          status: "completed",
          arguments: {
            text: "password=secret\nAIASK_AGENT_CONTROL_TOKEN=token",
            include_env: false
          },
          findings: []
        },
        error: null
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<SecurityPanel apiToken="" controlToken="control-token" endpoint="http://127.0.0.1:8767" />);

    fireEvent.change(screen.getByLabelText("文本片段"), {
      target: { value: "password=secret\nAIASK_AGENT_CONTROL_TOKEN=token" }
    });
    fireEvent.click(screen.getByRole("button", { name: /运行扫描/ }));

    await waitFor(() => expect(screen.getByText("SECURITY_SCAN_COMPLETED")).toBeInTheDocument());

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8767/v1/hermes/admin/tools/agent_security_scan");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.headers).toEqual(expect.objectContaining({ Authorization: "Bearer control-token" }));
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      text: "password=secret\nAIASK_AGENT_CONTROL_TOKEN=token",
      include_env: false
    });

    const rendered = document.querySelector(".raw-details")?.textContent || "";
    expect(rendered).toContain("[redacted]");
    expect(rendered).not.toContain("password=secret");
    expect(rendered).not.toContain("AIASK_AGENT_CONTROL_TOKEN=token");
  });
});
