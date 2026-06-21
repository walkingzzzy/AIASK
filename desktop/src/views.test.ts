import { describe, expect, it } from "vitest";

import { V1_DEFERRED_VIEWS } from "./routes";
import { V1_VIEWS } from "./views";

describe("V1 view registry", () => {
  it("has unique routes and ids", () => {
    expect(new Set(V1_VIEWS.map((view) => view.id)).size).toBe(V1_VIEWS.length);
    expect(new Set(V1_VIEWS.map((view) => view.route)).size).toBe(V1_VIEWS.length);
  });

  it("does not include deferred product entries", () => {
    const ids = V1_VIEWS.map((view) => view.id);
    for (const deferred of V1_DEFERRED_VIEWS) {
      expect(ids).not.toContain(deferred);
    }
  });

  it("keeps navigation labels clean", () => {
    const visibleText = V1_VIEWS.flatMap((view) => [view.label, view.shortLabel, view.description]).join("\n");
    expect(visibleText).not.toMatch(/策略工厂|四工厂|Strategy Factory|Factor Factory|Factory Events|Incubation/i);
  });
});
