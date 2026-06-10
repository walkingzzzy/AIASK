import { useCallback, useMemo, useState } from "react";
import { formatApiError, normalizeEndpoint } from "../api";
import { isMockEndpoint, MOCK_CONTROL_TOKEN } from "../mockApi";
import { AiaskApi } from "../services/aiaskApi";
import type { HealthDetailed, HermesStatus, LocalProfile, ToolCatalogItem } from "../types";

const ENDPOINT_KEY = "aiask.endpoint";
const DEFAULT_ENDPOINT = "http://127.0.0.1:8767";
const VERIFIED_ENDPOINT_KEY = "aiask.endpoint.verified";
const AUTO_CONNECT_KEY = "aiask.endpoint.autoconnect";
const LIVE_USER_ID_KEY = "aiask.local.user_id";
const LIVE_PROFILE_NAME_KEY = "aiask.local.profile_name";
const MOCK_USER_ID_KEY = "aiask.mock.local.user_id";
const MOCK_PROFILE_NAME_KEY = "aiask.mock.local.profile_name";
const DEFAULT_USER_ID = "local";
const DEFAULT_PROFILE_NAME = "本地操作者";

function detectMockMode(): boolean {
  try {
    return new URLSearchParams(window.location.search).get("mock") === "1";
  } catch {
    return false;
  }
}

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore storage issues under tests or restricted webviews
  }
}

function storageRemove(key: string) {
  try {
    localStorage.removeItem(key);
  } catch {
    // ignore storage issues under tests or restricted webviews
  }
}

function looksLikeMockProfile(value: string | null): boolean {
  const normalized = (value || "").trim().toLowerCase();
  return normalized === "mock 本地操作者" || normalized.startsWith("mock ");
}

function initialUserId(mockMode: boolean): string {
  const key = mockMode ? MOCK_USER_ID_KEY : LIVE_USER_ID_KEY;
  return storageGet(key) || DEFAULT_USER_ID;
}

function initialProfileName(mockMode: boolean): string {
  if (mockMode) {
    return storageGet(MOCK_PROFILE_NAME_KEY) || storageGet(LIVE_PROFILE_NAME_KEY) || DEFAULT_PROFILE_NAME;
  }
  const stored = storageGet(LIVE_PROFILE_NAME_KEY);
  return stored && !looksLikeMockProfile(stored) ? stored : DEFAULT_PROFILE_NAME;
}

export interface HealthRefreshResult {
  health: HealthDetailed;
  tools: ToolCatalogItem[];
  hermesStatus: HermesStatus | null;
}

export function useAppConnectionSettings() {
  const mockMode = useMemo(() => detectMockMode(), []);
  const verifiedEndpoint = storageGet(VERIFIED_ENDPOINT_KEY) === "1";
  const autoConnectEnabled = storageGet(VERIFIED_ENDPOINT_KEY) === "1" && storageGet(AUTO_CONNECT_KEY) === "1";
  const [endpoint, setEndpoint] = useState(() =>
    mockMode
      ? "mock://aiask"
      : verifiedEndpoint
        ? storageGet(ENDPOINT_KEY) || DEFAULT_ENDPOINT
        : DEFAULT_ENDPOINT
  );
  const [apiToken, setApiToken] = useState("");
  const [controlToken, setControlToken] = useState(() => (mockMode ? MOCK_CONTROL_TOKEN : ""));
  const [agentMode, setAgentMode] = useState<"finance_safe" | "hermes_full">("finance_safe");
  const [userId, setUserId] = useState(() => initialUserId(mockMode));
  const [profileName, setProfileName] = useState(() => initialProfileName(mockMode));
  const [health, setHealth] = useState<HealthDetailed | null>(null);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [status, setStatus] = useState(() => (verifiedEndpoint ? "AIASK_OFFLINE" : "AIASK_DISCONNECTED"));
  const [connectionBusy, setConnectionBusy] = useState(false);

  const normalizedEndpoint = normalizeEndpoint(endpoint);
  const api = useMemo(
    () => new AiaskApi({ endpoint: normalizedEndpoint, apiToken, controlToken }),
    [apiToken, controlToken, normalizedEndpoint]
  );
  const agentReachable = mockMode || !!health || autoConnectEnabled;

  const refreshHealth = useCallback(async (): Promise<HealthRefreshResult> => {
    setConnectionBusy(true);
    try {
      const [nextHealth, nextTools] = await Promise.all([api.health(), api.tools()]);
      const nextToolList = nextTools.data || [];
      setHealth(nextHealth);
      setTools(nextToolList);
      setStatus("AIASK_ONLINE");
      if (!isMockEndpoint(normalizedEndpoint)) {
        storageSet(ENDPOINT_KEY, normalizedEndpoint);
        storageSet(VERIFIED_ENDPOINT_KEY, "1");
        storageSet(AUTO_CONNECT_KEY, "1");
      }

      let hermesStatus: HermesStatus | null = null;
      try {
        hermesStatus = await api.hermesStatus();
      } catch {
        hermesStatus = null;
      }
      return { health: nextHealth, tools: nextToolList, hermesStatus };
    } catch (error) {
      setStatus(formatApiError(error));
      setHealth(null);
      setTools([]);
      throw error;
    } finally {
      setConnectionBusy(false);
    }
  }, [api, normalizedEndpoint]);

  const resetEndpointToDefault = useCallback(() => {
    setEndpoint(mockMode ? "mock://aiask" : DEFAULT_ENDPOINT);
    setHealth(null);
    setTools([]);
    setStatus("AIASK_DISCONNECTED");
    if (!mockMode) {
      storageRemove(ENDPOINT_KEY);
      storageRemove(VERIFIED_ENDPOINT_KEY);
      storageRemove(AUTO_CONNECT_KEY);
    }
  }, [mockMode]);

  const updateLocalProfile = useCallback((profile: LocalProfile) => {
    const nextUserId = profile.user_id || DEFAULT_USER_ID;
    const nextProfileName = profile.profile_name || DEFAULT_PROFILE_NAME;
    const userIdKey = mockMode ? MOCK_USER_ID_KEY : LIVE_USER_ID_KEY;
    const profileNameKey = mockMode ? MOCK_PROFILE_NAME_KEY : LIVE_PROFILE_NAME_KEY;
    setUserId(nextUserId);
    setProfileName(nextProfileName);
    storageSet(userIdKey, nextUserId);
    storageSet(profileNameKey, nextProfileName);
  }, [mockMode]);

  return {
    agentMode,
    agentReachable,
    api,
    apiToken,
    autoConnectEnabled,
    connectionBusy,
    controlToken,
    defaultEndpoint: mockMode ? "mock://aiask" : DEFAULT_ENDPOINT,
    endpoint,
    health,
    mockMode,
    normalizedEndpoint,
    profileName,
    refreshHealth,
    resetEndpointToDefault,
    setAgentMode,
    setApiToken,
    setControlToken,
    setEndpoint,
    setHealth,
    setStatus,
    setTools,
    status,
    tools,
    updateLocalProfile,
    userId,
  };
}
