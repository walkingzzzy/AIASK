import { useCallback, useMemo, useState } from "react";
import { formatApiError } from "../api";
import { AiaskApi } from "../services/aiaskApi";
import type { HealthDetailed, ToolCatalogItem } from "../types";

export function useConnection(endpoint: string, apiToken: string, controlToken: string) {
  const api = useMemo(() => new AiaskApi({ endpoint, apiToken, controlToken }), [endpoint, apiToken, controlToken]);
  const [health, setHealth] = useState<HealthDetailed | null>(null);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [status, setStatus] = useState("AIASK_DISCONNECTED");

  const refresh = useCallback(async () => {
    try {
      const [nextHealth, nextTools] = await Promise.all([api.health(), api.tools()]);
      setHealth(nextHealth);
      setTools(nextTools.data || []);
      setStatus("AIASK_ONLINE");
      return { health: nextHealth, tools: nextTools.data || [] };
    } catch (error) {
      setHealth(null);
      setTools([]);
      setStatus(formatApiError(error));
      throw error;
    }
  }, [api]);

  return { api, health, setHealth, tools, setTools, status, setStatus, refresh };
}

