import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the V1 workbench without deferred product entries", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { level: 1, name: "AI 对话工作台" })).toBeInTheDocument();
    expect(screen.queryByText(/策略工厂|四工厂|Strategy Factory|Factor Factory|Factory Events|Incubation/i)).not.toBeInTheDocument();
  });

  it("redirects old deferred paths to finance lab", async () => {
    render(
      <MemoryRouter initialEntries={["/strategy-factory"]}>
        <App />
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { level: 1, name: "金融工作台" })).toBeInTheDocument();
  });
});
