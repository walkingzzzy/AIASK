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
    await waitFor(() => expect(screen.getByText("工厂接力状态已加载")).toBeInTheDocument());

    expect(screen.getByText("Factor -> Strategy -> Incubation")).toBeInTheDocument();
    expect(screen.getAllByText("因子工厂").length).toBeGreaterThan(0);
    expect(screen.getAllByText("策略工厂").length).toBeGreaterThan(0);
    expect(screen.getAllByText("孵化工厂").length).toBeGreaterThan(0);
    expect(screen.getByText("momentum_20d")).toBeInTheDocument();
    expect(screen.getByText("strategy_mock")).toBeInTheDocument();
    expect(screen.getAllByText("completed").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "查看因子池" }));
    expect(onOpenView).toHaveBeenCalledWith("factor-factory");

    fireEvent.click(screen.getByRole("button", { name: "打开策略工厂" }));
    expect(onOpenView).toHaveBeenCalledWith("strategy-factory");
  });
});
