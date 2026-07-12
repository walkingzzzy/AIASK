import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { act } from "react";

import { App } from "./App";

describe("App", () => {
  it("renders the V1 workbench with factory entries kept out of primary rail", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/"]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
          <App />
        </MemoryRouter>
      );
    });

    expect(await screen.findByRole("heading", { level: 1, name: "AI 任务工作台" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /策略工厂/ })).not.toBeInTheDocument();
    cleanup();
  });

  it("opens factory paths as controlled finance pages", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/strategy-factory"]} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
          <App />
        </MemoryRouter>
      );
    });

    expect(await screen.findByRole("heading", { level: 1, name: "策略工厂" })).toBeInTheDocument();
    cleanup();
  });
});
