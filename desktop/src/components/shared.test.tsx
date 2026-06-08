import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConfirmActionButton, GatedState, RawEvidencePanel, StatusBadge } from "./shared";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("shared UI primitives", () => {
  it("localizes status labels while preserving the technical title", () => {
    render(<StatusBadge status="approval_required" />);

    expect(screen.getByText("需审批")).toBeInTheDocument();
    expect(screen.getByTitle("approval_required / 需审批")).toBeInTheDocument();
  });

  it("renders gated states with a reason and next action", () => {
    render(
      <GatedState
        action={<button type="button">打开 Settings</button>}
        reason="control token required"
        status="gated"
        title="控制令牌未就绪"
      />
    );

    expect(screen.getByText("控制令牌未就绪")).toBeInTheDocument();
    expect(screen.getByText(/缺少 Control token/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开 Settings" })).toBeInTheDocument();
  });

  it("keeps raw evidence collapsed by default", () => {
    render(<RawEvidencePanel title="结构化报告" value={{ status: "ready" }} />);

    const details = screen.getByText("结构化报告").closest("details");
    expect(details).not.toHaveAttribute("open");
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
    expect(onConfirmed).toHaveBeenCalledTimes(1);
  });
});
