import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { act } from "react";

import { App } from "./App";

describe("App", () => {
  it("renders the V1 workbench without deferred product entries", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      );
    });

    expect(await screen.findByRole("heading", { level: 1, name: "AI 任务工作台" })).toBeInTheDocument();
    expect(screen.queryByText(/策略工厂|四工厂|Strategy Factory|Factor Factory|Factory Events|Incubation/i)).not.toBeInTheDocument();
    cleanup();
  });

  it("redirects old deferred paths to finance lab", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/strategy-factory"]}>
          <App />
        </MemoryRouter>
      );
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Finance Lab" })).toBeInTheDocument();
    cleanup();
  });
});
