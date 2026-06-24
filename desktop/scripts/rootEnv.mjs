import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");
const rootEnvPath = resolve(repoRoot, ".env");
const defaultAgentBase = "http://127.0.0.1:8765";

function parseEnvText(text) {
  const result = {};
  for (const rawLine of String(text || "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const normalized = line.startsWith("export ") ? line.slice(7).trim() : line;
    const index = normalized.indexOf("=");
    const key = normalized.slice(0, index).trim();
    if (!key) continue;
    let value = normalized.slice(index + 1).trim();
    if (value.length >= 2 && value[0] === value[value.length - 1] && (value[0] === '"' || value[0] === "'")) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }
  return result;
}

function loadRootEnvValues() {
  try {
    return parseEnvText(readFileSync(rootEnvPath, "utf8"));
  } catch {
    return {};
  }
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

export function buildDesktopEnv(baseEnv = process.env, mode = "") {
  const rootEnv = loadRootEnvValues();
  const env = {
    ...rootEnv,
    ...baseEnv
  };

  const resolvedMode = firstNonEmpty(mode, env.AIASK_E2E_MODE, env.VITE_AIASK_API_MODE) || "mock";
  const resolvedAgentBase = firstNonEmpty(env.AIASK_E2E_AGENT_BASE, env.VITE_AIASK_API_BASE, env.AIASK_AGENT_BASE) || defaultAgentBase;
  const resolvedApiToken = firstNonEmpty(env.AIASK_E2E_API_TOKEN, env.AIASK_AGENT_API_TOKEN);
  const resolvedControlToken = firstNonEmpty(env.AIASK_E2E_CONTROL_TOKEN, env.AIASK_AGENT_CONTROL_TOKEN, env.AIASK_LOCAL_CONTROL_TOKEN);
  const resolvedUserId = firstNonEmpty(env.AIASK_E2E_USER_ID, env.VITE_AIASK_USER_ID, env.AIASK_DEFAULT_USER_ID) || "e2e-user";

  return {
    ...env,
    AIASK_E2E_MODE: resolvedMode,
    AIASK_E2E_AGENT_BASE: resolvedAgentBase,
    AIASK_E2E_API_TOKEN: resolvedApiToken,
    AIASK_E2E_CONTROL_TOKEN: resolvedControlToken,
    AIASK_E2E_USER_ID: resolvedUserId,
    VITE_AIASK_API_BASE: firstNonEmpty(env.VITE_AIASK_API_BASE, resolvedAgentBase) || defaultAgentBase,
    VITE_AIASK_API_MODE: firstNonEmpty(env.VITE_AIASK_API_MODE, resolvedMode) || "mock",
    VITE_AIASK_API_TOKEN: firstNonEmpty(env.VITE_AIASK_API_TOKEN, resolvedApiToken),
    VITE_AIASK_CONTROL_TOKEN: firstNonEmpty(env.VITE_AIASK_CONTROL_TOKEN, resolvedControlToken),
    VITE_AIASK_USER_ID: firstNonEmpty(env.VITE_AIASK_USER_ID, resolvedUserId)
  };
}

export { defaultAgentBase, repoRoot, rootEnvPath };
