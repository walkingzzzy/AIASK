import { useCallback, useMemo, useState } from "react";
import { formatApiError } from "../api";
import { AiaskApi } from "../services/aiaskApi";
import type { CapabilityWorkbenchPayload } from "../types";

export function useCapabilityWorkbench(endpoint: string, apiToken: string, controlToken: string) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [payload, setPayload] = useState<CapabilityWorkbenchPayload | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const nextPayload = await api.capabilities();
      setPayload(nextPayload);
      setMessage("CAPABILITIES_SYNCED");
      return nextPayload;
    } catch (error) {
      setMessage(formatApiError(error));
      throw error;
    } finally {
      setBusy(false);
    }
  }, [api]);

  return { api, payload, setPayload, message, setMessage, busy, refresh };
}

