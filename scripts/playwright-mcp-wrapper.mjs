#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const scriptDir = path.dirname(scriptPath);
const repoRoot = path.resolve(scriptDir, '..');
const runtimeRoot = path.join(repoRoot, '.playwright-mcp-runtime');
const runtimeHome = path.join(runtimeRoot, 'home');
const runtimeTmp = path.join(runtimeRoot, 'tmp');
const runtimeCache = path.join(runtimeRoot, 'cache');
const runtimeBrowsers = path.join(runtimeRoot, 'ms-playwright');

for (const dir of [runtimeRoot, runtimeHome, runtimeTmp, runtimeCache, runtimeBrowsers]) {
  fs.mkdirSync(dir, { recursive: true });
}

function parseArgsEnv(raw) {
  if (!raw?.trim()) return null;
  const trimmed = raw.trim();
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed) && parsed.every((item) => typeof item === 'string')) {
      return parsed;
    }
  } catch {
    // fall through to whitespace split
  }
  return trimmed.split(/\s+/).filter(Boolean);
}

const localBinaryCandidates = [
  path.join(repoRoot, 'node_modules', '.bin', 'playwright-mcp'),
  path.join(repoRoot, 'node_modules', '.bin', 'mcp-playwright'),
];
const localBinary = localBinaryCandidates.find((candidate) => fs.existsSync(candidate)) ?? null;
const explicitCommand = process.env.PLAYWRIGHT_MCP_BIN?.trim();
const explicitArgs = parseArgsEnv(process.env.PLAYWRIGHT_MCP_ARGS);
const fallbackCommand = localBinary || 'npx';
const fallbackArgs = localBinary ? [] : ['-y', '@playwright/mcp@latest', '--isolated'];
const command = explicitCommand || fallbackCommand;
const args = [...(explicitArgs ?? fallbackArgs), ...process.argv.slice(2)];

const childEnv = {
  ...process.env,
  HOME: runtimeHome,
  USERPROFILE: runtimeHome,
  TMPDIR: runtimeTmp,
  TMP: runtimeTmp,
  TEMP: runtimeTmp,
  XDG_CACHE_HOME: runtimeCache,
  PLAYWRIGHT_BROWSERS_PATH: runtimeBrowsers,
  NO_PROXY: process.env.NO_PROXY || '*',
};

process.chdir(repoRoot);

if (process.env.PLAYWRIGHT_MCP_WRAPPER_DEBUG === '1' && !explicitCommand && !localBinary) {
  console.error(
    '[playwright-mcp-wrapper] local playwright-mcp binary not found, falling back to "npx -y @playwright/mcp@latest --isolated".',
  );
}

const child = spawn(command, args, {
  cwd: repoRoot,
  env: childEnv,
  stdio: 'inherit',
});

child.on('error', (error) => {
  console.error(
    `[playwright-mcp-wrapper] failed to start "${command}": ${error instanceof Error ? error.message : String(error)}`,
  );
  console.error(
    '[playwright-mcp-wrapper] set PLAYWRIGHT_MCP_BIN or PLAYWRIGHT_MCP_ARGS if the MCP command lives outside the repo.',
  );
  process.exit(1);
});

child.on('exit', (code, signal) => {
  if (signal) {
    console.error(`[playwright-mcp-wrapper] Playwright MCP server exited due to signal ${signal}.`);
    process.exit(1);
    return;
  }

  if (code && code !== 0) {
    console.error(
      `[playwright-mcp-wrapper] Playwright MCP server exited with code ${code}. Check package availability and the wrapper diagnostics above.`,
    );
  }

  process.exit(code ?? 0);
});
