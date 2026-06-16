import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiaskApi } from "../../services/aiaskApi";
import { ArtifactsPage } from "./ArtifactsPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ArtifactsPage", () => {
  const mockProps = {
    apiToken: "test-token",
    controlToken: "mock-control-token",
    endpoint: "mock://aiask",
    onOpenView: vi.fn(),
  };

  it("loads durable artifacts from recent runs", async () => {
    render(<ArtifactsPage {...mockProps} />);

    expect(screen.getByRole("heading", { name: "产物" })).toBeInTheDocument();
    await screen.findByText("600519 实时行情快照");
    expect(screen.getByText("600519 新闻摘要")).toBeInTheDocument();
    expect(screen.getByText("call_mock_script_snippet.py")).toBeInTheDocument();
    expect(screen.getByText("agent_terminal output")).toBeInTheDocument();
    const evidenceLinks = screen.getAllByRole("link", { name: /Open evidence/ }).map((link) => link.getAttribute("href"));
    expect(evidenceLinks).toContain("mock://aiask/v1/artifacts/art_mock_terminal/content?max_bytes=1048576");
  });

  it("filters artifacts by kind and search query", async () => {
    render(<ArtifactsPage {...mockProps} />);

    await screen.findByText("600519 实时行情快照");
    fireEvent.change(screen.getByLabelText("产物类型"), { target: { value: "script" } });
    expect(screen.getByText("call_mock_script_snippet.py")).toBeInTheDocument();
    expect(screen.queryByText("600519 新闻摘要")).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("搜索产物、路径、运行或工具..."), { target: { value: "terminal" } });
    expect(screen.getByText("没有匹配产物")).toBeInTheDocument();
  });

  it("shows an empty action when no run artifacts exist", async () => {
    const onOpenView = vi.fn();
    vi.spyOn(AiaskApi.prototype, "runsList").mockResolvedValue({ object: "list", data: [] });
    render(<ArtifactsPage {...mockProps} onOpenView={onOpenView} />);

    await waitFor(() => expect(screen.getByText("暂无产物")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /打开运行 \/ 事件/ }));
    expect(onOpenView).toHaveBeenCalledWith("runs-events");
  });
});
