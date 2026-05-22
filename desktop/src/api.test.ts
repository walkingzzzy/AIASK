import { describe, expect, it } from "vitest";
import { parseSseEvents } from "./api";

describe("parseSseEvents", () => {
  it("preserves SSE id, event, and data fields", () => {
    const events = parseSseEvents<Record<string, unknown>>(
      [
        "id: 12",
        "event: run.started",
        'data: {"run_id":"run_1","status":"started"}',
        "",
        "id: 13",
        "event: model.delta",
        'data: {"content":"hello"}',
        "",
        "data: [DONE]",
        ""
      ].join("\n")
    );

    expect(events).toHaveLength(2);
    expect(events[0]).toMatchObject({
      id: "12",
      event: "run.started",
      run_id: "run_1",
      data: { run_id: "run_1", status: "started" }
    });
    expect(events[1]).toMatchObject({
      id: "13",
      event: "model.delta",
      content: "hello",
      data: { content: "hello" }
    });
  });
});

