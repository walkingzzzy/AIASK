import { useCallback, useMemo, useState } from "react";
import { formatApiError } from "../api";
import { AiaskApi } from "../services/aiaskApi";
import type { AiSmokeResult, AiStatus } from "../types";

export function useAiSmoke(endpoint: string, apiToken: string, controlToken: string) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [result, setResult] = useState<AiSmokeResult | null>(null);
  const [models, setModels] = useState<Array<Record<string, unknown>>>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    const nextStatus = await api.aiStatus();
    setStatus(nextStatus);
    return nextStatus;
  }, [api]);

  const runSmoke = useCallback(
    async (prompt?: string, model?: string) => {
      setBusy(true);
      try {
        const nextResult = await api.aiSmoke(prompt, model);
        setResult(nextResult);
        setMessage(nextResult.success ? "AI_SMOKE_PASSED" : nextResult.error_code || "AI_SMOKE_FAILED");
        return nextResult;
      } catch (error) {
        setMessage(formatApiError(error));
        throw error;
      } finally {
        setBusy(false);
      }
    },
    [api]
  );

  const refreshModels = useCallback(async () => {
    setBusy(true);
    try {
      const nextModels = await api.aiModels();
      setModels(nextModels.data || []);
      setMessage(nextModels.error || "AI_MODELS_LOADED");
      return nextModels;
    } finally {
      setBusy(false);
    }
  }, [api]);

  return { status, result, models, message, busy, refreshStatus, runSmoke, refreshModels };
}

