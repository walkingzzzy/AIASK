import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FinanceLabPage } from "./FinanceLabPage";

describe("FinanceLabPage", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the factory relay from read-only Agent evidence and navigates to factory panels", async () => {
    const onOpenView = vi.fn();
    render(
      <FinanceLabPage
        endpoint="mock://aiask"
        apiToken="api-token"
        controlToken="mock-control-token"
        onOpenView={onOpenView}
      />
    );

    expect(screen.getByRole("heading", { name: "工厂接力总览" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("接力状态已加载")).toBeInTheDocument());

    await waitFor(() => expect(screen.getByRole("heading", { name: "券商只读与行为分析" })).toBeInTheDocument());
    expect(screen.getAllByText("QMT / MiniQMT").length).toBeGreaterThan(0);
    expect(screen.getByText("同花顺")).toBeInTheDocument();
    expect(screen.getByText("环境变量与依赖")).toBeInTheDocument();
    expect(screen.getByText("授权说明")).toBeInTheDocument();
    expect(screen.getByText("只读测试入口")).toBeInTheDocument();
    expect(screen.getByText("QMT_PATH")).toBeInTheDocument();
    expect(screen.getByText("Install and sign in to MiniQMT on the same Windows host as the Agent.")).toBeInTheDocument();
    expect(screen.getByText("/v1/desktop/broker/sync")).toBeInTheDocument();
    expect(screen.getByText("100,000")).toBeInTheDocument();
    expect(screen.getByText("HIGH_SINGLE_POSITION_CONCENTRATION")).toBeInTheDocument();
    expect(screen.getByText("Kweichow Moutai · 45,000")).toBeInTheDocument();
    expect(screen.getByText("Factor -> Strategy -> Incubation")).toBeInTheDocument();
    expect(screen.getAllByText("因子工厂").length).toBeGreaterThan(0);
    expect(screen.getAllByText("策略工厂").length).toBeGreaterThan(0);
    expect(screen.getAllByText("孵化工厂").length).toBeGreaterThan(0);
    expect(screen.getByText("momentum_20d")).toBeInTheDocument();
    expect(screen.getByText("strategy_mock")).toBeInTheDocument();
    expect(screen.getAllByText("completed").length).toBeGreaterThan(0);
    expect(screen.getByText("Weak cell")).toBeInTheDocument();
    expect(screen.getByText("Top blocker")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hit-rate evidence that needs review" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where hit-rate review is actionable" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What blocks graduation now" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Current strategy states with proof" })).toBeInTheDocument();
    expect(screen.getAllByText(/mean_reversion/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/missing_forward_window_5d/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/strategy_event_cn|Event CN/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "查看因子池" }));
    expect(onOpenView).toHaveBeenCalledWith("factor-factory");

    fireEvent.click(screen.getByRole("button", { name: "打开策略评审" }));
    expect(onOpenView).toHaveBeenCalledWith("strategy-factory");

    expect(screen.getByRole("button", { name: "运行只读测试并生成分析" })).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/我确认本次只读测试/));
    fireEvent.click(screen.getByRole("button", { name: /Sync QMT read-only/i }));
    await waitFor(() => expect(screen.getByText("BROKER_SYNCED")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("tab", { name: /同花顺/ }));
    await waitFor(() => expect(screen.getByText("THS_CLIENT_PATH")).toBeInTheDocument());
    expect(screen.getByText("Install and sign in to the Tonghuashun desktop trading client on Windows.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("86,000")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Sync .* read-only/i }));
    await waitFor(() => expect(screen.getByText("BROKER_SYNCED")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("CATL · 44,000")).toBeInTheDocument());
  });
});
