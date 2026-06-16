import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useAppConnectionSettings } from "./useAppConnectionSettings";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  window.history.pushState({}, "", "/");
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  window.history.pushState({}, "", "/");
});

describe("useAppConnectionSettings", () => {
  it("does not reuse a persisted mock profile in live mode", () => {
    localStorage.setItem("aiask.local.profile_name", "Mock 本地操作者");

    const { result } = renderHook(() => useAppConnectionSettings());

    expect(result.current.mockMode).toBe(false);
    expect(result.current.endpoint).toBe("http://127.0.0.1:8767");
    expect(result.current.defaultEndpointActive).toBe(true);
    expect(result.current.agentReachable).toBe(true);
    expect(result.current.profileName).toBe("本地操作者");
  });

  it("keeps mock profile state isolated from live profile state", () => {
    window.history.pushState({}, "", "/?mock=1");
    const { result } = renderHook(() => useAppConnectionSettings());

    act(() => {
      result.current.updateLocalProfile({ user_id: "mock-local", profile_name: "Mock 本地操作者" });
    });

    expect(result.current.mockMode).toBe(true);
    expect(result.current.endpoint).toBe("mock://aiask");
    expect(result.current.profileName).toBe("Mock 本地操作者");
    expect(localStorage.getItem("aiask.mock.local.profile_name")).toBe("Mock 本地操作者");
    expect(localStorage.getItem("aiask.local.profile_name")).toBeNull();
  });

  it("persists live profile state to the live profile keys", () => {
    const { result } = renderHook(() => useAppConnectionSettings());

    act(() => {
      result.current.updateLocalProfile({ user_id: "live-local", profile_name: "真实后端操作者" });
    });

    expect(result.current.mockMode).toBe(false);
    expect(result.current.profileName).toBe("真实后端操作者");
    expect(localStorage.getItem("aiask.local.profile_name")).toBe("真实后端操作者");
    expect(localStorage.getItem("aiask.mock.local.profile_name")).toBeNull();
  });

  it("restores live tokens from session storage without writing them to local storage", () => {
    const first = renderHook(() => useAppConnectionSettings());

    act(() => {
      first.result.current.setApiToken("api-session-token");
      first.result.current.setControlToken("control-session-token");
    });

    first.unmount();
    const second = renderHook(() => useAppConnectionSettings());

    expect(second.result.current.apiToken).toBe("api-session-token");
    expect(second.result.current.controlToken).toBe("control-session-token");
    expect(localStorage.getItem("aiask.session.api_token")).toBeNull();
    expect(localStorage.getItem("aiask.session.control_token")).toBeNull();
  });
});
