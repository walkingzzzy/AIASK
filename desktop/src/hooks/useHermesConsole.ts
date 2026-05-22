import { useCallback, useMemo, useState } from "react";
import { formatApiError } from "../api";
import { AiaskApi } from "../services/aiaskApi";
import type { FullModeConsoleData, HermesConsoleSnapshot, HermesStatus, ToolCatalogItem } from "../types";

export function useHermesConsole(endpoint: string, apiToken: string, controlToken: string) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [apiToken, controlToken, endpoint]);
  const [hermesStatus, setHermesStatus] = useState<HermesStatus | null>(null);
  const [hermesTools, setHermesTools] = useState<ToolCatalogItem[]>([]);
  const [fullConsole, setFullConsole] = useState<FullModeConsoleData>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async (): Promise<HermesConsoleSnapshot> => {
    setBusy(true);
    try {
      const snapshot = await api.fullConsoleSnapshot();
      setHermesStatus(snapshot.hermesStatus);
      setHermesTools(snapshot.hermesTools);
      setFullConsole(snapshot.fullConsole);
      setMessage(snapshot.message);
      return snapshot;
    } catch (error) {
      const nextMessage = formatApiError(error);
      setHermesTools([]);
      setMessage(nextMessage);
      throw error;
    } finally {
      setBusy(false);
    }
  }, [api]);

  return {
    busy,
    fullConsole,
    hermesStatus,
    hermesTools,
    message,
    refresh,
    setFullConsole,
    setHermesStatus,
    setHermesTools,
    setMessage
  };
}
