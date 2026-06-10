import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { IncubationFactoryPanel } from "./IncubationFactoryPanel";

describe("IncubationFactoryPanel trade prediction observability", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders read-only trade prediction status, outcomes, and matrix data", async () => {
    render(<IncubationFactoryPanel endpoint="mock://aiask" apiToken="api-token" controlToken="" />);

    await waitFor(() => expect(screen.getByText("交易预测可观测性")).toBeInTheDocument());

    expect(screen.getByText("预测数")).toBeInTheDocument();
    expect(screen.getByText("样本数")).toBeInTheDocument();
    expect(screen.getByText("评分版本")).toBeInTheDocument();
    expect(screen.getByText("score_version")).toBeInTheDocument();
    expect(screen.getAllByText(/trade_prediction_score_v2/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/partial_intraday_missing/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/intraday_missing/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/strategy_momentum_cn/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/event_driven/).length).toBeGreaterThan(0);
  });
});
