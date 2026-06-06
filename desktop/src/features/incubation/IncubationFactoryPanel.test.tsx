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

    await waitFor(() => expect(screen.getByText("Trade Prediction Observability")).toBeInTheDocument());

    expect(screen.getByText("Predictions")).toBeInTheDocument();
    expect(screen.getByText("Sample n")).toBeInTheDocument();
    expect(screen.getByText("Score Versions")).toBeInTheDocument();
    expect(screen.getByText("score_version")).toBeInTheDocument();
    expect(screen.getAllByText(/trade_prediction_score_v2/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/partial_intraday_missing/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/intraday_missing/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/strategy_momentum_cn/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/event_driven/).length).toBeGreaterThan(0);
  });
});
