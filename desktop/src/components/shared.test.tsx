import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmActionButton, GatedState, JsonPanel, RawEvidencePanel, StatusBadge } from "./shared";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("shared UI primitives", () => {
  it("localizes status labels while preserving the technical title", () => {
    render(<StatusBadge status="approval_required" />);

    expect(screen.getByText("需要审批")).toBeInTheDocument();
    expect(screen.getByTitle("approval_required / 需要审批")).toBeInTheDocument();
  });

  it("renders gated states with a localized reason and next action", () => {
    render(
      <GatedState
        action={<button type="button">打开设置</button>}
        reason="control token required"
        status="gated"
        title="控制令牌未就绪"
      />
    );

    expect(screen.getByText("控制令牌未就绪")).toBeInTheDocument();
    expect(screen.getByText(/缺少控制令牌/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开设置" })).toBeInTheDocument();
  });

  it("keeps raw evidence collapsed by default", () => {
    render(<RawEvidencePanel title="结构化报告" value={{ status: "ready" }} />);

    const details = screen.getByText("结构化报告").closest("details");
    expect(details).not.toHaveAttribute("open");
  });

  it("redacts secret-looking raw JSON values while keeping configuration flags", () => {
    const { container } = render(
      <JsonPanel
        value={{
          api_key: "sk-test-secret-value-1234567890",
          nested: {
            Authorization: "Bearer live-secret-token-1234567890",
            scan_text: "password=secret\nAIASK_AGENT_CONTROL_TOKEN=token",
            api_key_configured: true,
            required_env: ["AIASK_OPENAI_API_KEY"]
          }
        }}
      />
    );

    const text = container.querySelector(".json-panel")?.textContent || "";
    expect(text).toContain("[redacted]");
    expect(text).toContain('"api_key_configured": true');
    expect(text).toContain("AIASK_OPENAI_API_KEY");
    expect(text).not.toContain("sk-test-secret-value");
    expect(text).not.toContain("live-secret-token");
    expect(text).not.toContain("password=secret");
    expect(text).not.toContain("AIASK_AGENT_CONTROL_TOKEN=token");
  });

  it("confirms danger actions before calling the handler", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const onConfirmed = vi.fn();

    render(
      <ConfirmActionButton actionLabel="删除响应" confirmDetail="Response: r1" isDanger onConfirmed={onConfirmed}>
        删除
      </ConfirmActionButton>
    );

    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("删除响应"));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("此操作会改变当前任务"));
    expect(onConfirmed).toHaveBeenCalledTimes(1);
  });
});
