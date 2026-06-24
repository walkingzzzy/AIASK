import { useEffect, useMemo, useState } from "react";

import { AiaskApi } from "../services/aiaskApi";
import type { ApiMode, ConnectionSettings } from "../types";

const STORAGE_KEY = "aiask.desktop.connectionSettings.v1";

const defaults: ConnectionSettings = {
  baseUrl: import.meta.env.VITE_AIASK_API_BASE || "http://127.0.0.1:8765",
  apiToken: import.meta.env.VITE_AIASK_API_TOKEN || "",
  controlToken: import.meta.env.VITE_AIASK_CONTROL_TOKEN || "",
  mode: (import.meta.env.VITE_AIASK_API_MODE as ApiMode | undefined) || "mock",
  userId: import.meta.env.VITE_AIASK_USER_ID || "local-user"
};

function readSettings(): ConnectionSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaults;
    return { ...defaults, ...JSON.parse(raw) };
  } catch {
    return defaults;
  }
}

export function useConnectionSettings() {
  const [settings, setSettings] = useState<ConnectionSettings>(() => readSettings());

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  const api = useMemo(() => new AiaskApi(settings), [settings]);

  function updateSettings(patch: Partial<ConnectionSettings>) {
    setSettings((current) => ({ ...current, ...patch }));
  }

  return {
    settings,
    updateSettings,
    api,
    controlAvailable: Boolean(settings.controlToken.trim())
  };
}
