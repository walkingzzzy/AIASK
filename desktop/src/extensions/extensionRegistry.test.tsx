import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EXTENSION_SLOT_IDS,
  ExtensionsPilotPage,
  SlotRenderer,
  getInternalSlots,
  getSupportedExtensionSlots,
} from "./extensionRegistry";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("extensionRegistry", () => {
  it("exposes the controlled static slot surface", () => {
    expect(getSupportedExtensionSlots()).toEqual([
      "sidebar-top",
      "sidebar-secondary",
      "header-left",
      "header-right",
      "pre-main",
      "post-main",
      "overlay",
      "workbench.quick-actions",
    ]);
    expect(new Set(EXTENSION_SLOT_IDS).size).toBe(8);
  });

  it("registers only repo-native static entries for populated slots", () => {
    expect(getInternalSlots("sidebar-top")).toHaveLength(1);
    expect(getInternalSlots("header-left")[0].route).toBe("/readiness-health");
    expect(getInternalSlots("header-right")[0].route).toBe("/gateway");
    expect(getInternalSlots("workbench.quick-actions").length).toBeGreaterThanOrEqual(2);
    expect(getInternalSlots("overlay")).toHaveLength(0);
  });

  it("renders slot entries and dispatches navigation", () => {
    const onOpenView = vi.fn();
    render(
      <SlotRenderer
        controlToken="control"
        fullModeActive
        onOpenView={onOpenView}
        slot="header-right"
      />
    );

    fireEvent.click(screen.getByText("Gateway"));
    expect(onOpenView).toHaveBeenCalledWith("gateway");
  });

  it("keeps gated slot entries visible without external JavaScript", () => {
    render(
      <SlotRenderer
        controlToken=""
        fullModeActive={false}
        onOpenView={vi.fn()}
        slot="sidebar-top"
      />
    );

    expect(screen.getByText("Sessions")).toBeInTheDocument();
    expect(screen.getByText("gated")).toBeInTheDocument();
  });

  it("renders registry diagnostics with supported slots", () => {
    render(<ExtensionsPilotPage controlToken="control" fullModeActive />);

    expect(screen.getByText("Extensions Pilot")).toBeInTheDocument();
    expect(screen.getByText("Internal pages and slots only")).toBeInTheDocument();
    expect(screen.getAllByText("sidebar-top").length).toBeGreaterThan(0);
    expect(screen.getAllByText("workbench.quick-actions").length).toBeGreaterThan(0);
  });
});
