import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LegacyBanner } from "./LegacyBanner";

afterEach(() => cleanup());

describe("LegacyBanner", () => {
  it("separates legacy title and migration copy", () => {
    render(
      <LegacyBanner
        title="旧入口：MCP"
        description="主路径已迁移到集成，此页仅保留为 MCP 高级诊断快捷入口。"
      />
    );

    expect(screen.getByText("旧入口：MCP")).toBeInTheDocument();
    expect(screen.getByText("主路径已迁移到集成，此页仅保留为 MCP 高级诊断快捷入口。")).toBeInTheDocument();
    expect(screen.queryByText(/MCPThe primary path/)).not.toBeInTheDocument();
  });

  it("opens the replacement view", () => {
    const onOpenReplacement = vi.fn();
    render(
      <LegacyBanner
        title="旧入口：Tools"
        description="主路径已迁移到 Approvals。"
        replacementLabel="前往审批"
        replacementView="tools-intents-approvals"
        onOpenReplacement={onOpenReplacement}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /前往审批/ }));
    expect(onOpenReplacement).toHaveBeenCalledWith("tools-intents-approvals");
  });
});
