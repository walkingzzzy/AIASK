import { describe, expect, it } from "vitest";

import { V1_DEFERRED_VIEWS } from "./routes";
import { V1_VIEWS } from "./views";

describe("V1 view registry", () => {
  it("has unique routes and ids", () => {
    expect(new Set(V1_VIEWS.map((view) => view.id)).size).toBe(V1_VIEWS.length);
    expect(new Set(V1_VIEWS.map((view) => view.route)).size).toBe(V1_VIEWS.length);
  });

  it("includes factory control surfaces", () => {
    const ids = V1_VIEWS.map((view) => view.id);
    expect(V1_DEFERRED_VIEWS).toEqual([]);
    for (const factory of ["strategy-factory", "factor-factory", "incubation", "factory-events"]) {
      expect(ids).toContain(factory);
    }
  });

  it("keeps factory navigation labels Chinese-first and controlled", () => {
    const visibleText = V1_VIEWS.flatMap((view) => [view.label, view.shortLabel, view.description]).join("\n");
    expect(visibleText).toContain("策略工厂");
    expect(visibleText).toContain("因子工厂");
    expect(visibleText).toContain("孵化工厂");
    expect(visibleText).toContain("工厂事件");
    expect(visibleText).not.toMatch(/Strategy Factory|Factor Factory|Factory Events|Incubation/i);
  });
});
