import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PluginsSkillsPage } from "./PluginsSkillsPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PluginsSkillsPage", () => {
  const props = {
    endpoint: "mock://aiask",
    apiToken: "test-token",
    controlToken: "mock-control-token",
  };

  it("renders plugin and skill lifecycle state from Agent APIs", async () => {
    render(<PluginsSkillsPage {...props} onApplyToChat={vi.fn()} />);

    expect(screen.getByText("插件 / 技能")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("能力已同步").length).toBeGreaterThan(0));

    expect(screen.getByText("原生插件与技能操作")).toBeInTheDocument();
    expect(screen.getAllByText("risk-review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("audit-plugin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已安装").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已启用").length).toBeGreaterThan(0);
    expect(screen.getByText("插件准备度详情")).toBeInTheDocument();
    expect(screen.getAllByText(/工具 1 \/ 命令 0 \/ 钩子 0/).length).toBeGreaterThan(0);
  });

  it("applies a selected skill back to chat", async () => {
    const onApplyToChat = vi.fn();
    render(<PluginsSkillsPage {...props} onApplyToChat={onApplyToChat} />);

    await waitFor(() => expect(screen.getAllByText("risk-review").length).toBeGreaterThan(0));
    const applyButtons = await screen.findAllByRole("button", { name: "应用到对话" });
    fireEvent.click(applyButtons[0]);
    expect(onApplyToChat).toHaveBeenCalledWith(expect.objectContaining({ name: "risk-review" }));
  });
});
