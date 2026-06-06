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

    expect(screen.getByText("Plugins / Skills")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("CAPABILITIES_SYNCED").length).toBeGreaterThan(0));

    expect(screen.getByText("Native plugin and skill operations")).toBeInTheDocument();
    expect(screen.getAllByText("risk-review").length).toBeGreaterThan(0);
    expect(screen.getAllByText("audit-plugin").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已安装").length).toBeGreaterThan(0);
    expect(screen.getAllByText("已启用").length).toBeGreaterThan(0);
    expect(screen.getByText("Plugin readiness details")).toBeInTheDocument();
    expect(screen.getAllByText(/tools 1 \/ commands 0 \/ hooks 0/).length).toBeGreaterThan(0);
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
