import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';

export const ROOT = process.cwd();
export const APPS_WEB = path.join(ROOT, 'apps', 'web');
export const AKSHARE_MCP = path.join(ROOT, 'packages', 'akshare-mcp');
export const REPORTS_ROOT = path.join(ROOT, 'reports', 'realworld-e2e');

export function timestampId() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

export async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

export async function removeIfExists(targetPath) {
  await fs.rm(targetPath, { recursive: true, force: true });
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function sanitizeIdentifier(value, maxLength = 48) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, maxLength);
}

export function parseEnvFile(text) {
  const result = {};
  for (const line of String(text || '').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const index = trimmed.indexOf('=');
    if (index < 0) continue;
    const key = trimmed.slice(0, index).trim();
    let value = trimmed.slice(index + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }
  return result;
}

export async function loadMergedEnv() {
  const envFiles = [
    path.join(ROOT, '.env'),
    path.join(ROOT, 'apps', 'bff', '.env'),
    path.join(ROOT, 'packages', 'akshare-mcp', '.env'),
  ];

  const merged = {};
  for (const envFile of envFiles) {
    try {
      Object.assign(merged, parseEnvFile(await fs.readFile(envFile, 'utf8')));
    } catch {
      // ignore missing env file
    }
  }
  Object.assign(merged, process.env);
  return merged;
}

export function resolvePythonBin() {
  const isWindows = process.platform === 'win32';
  return isWindows
    ? path.join(AKSHARE_MCP, '.venv', 'Scripts', 'python.exe')
    : path.join(AKSHARE_MCP, '.venv', 'bin', 'python');
}

export async function runCommand(command, args, options = {}) {
  const child = spawn(command, args, {
    cwd: options.cwd || ROOT,
    env: options.env || process.env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let stdout = '';
  let stderr = '';

  child.stdout.on('data', (chunk) => {
    stdout += chunk.toString();
  });
  child.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  const exitCode = await new Promise((resolve) => child.on('close', resolve));

  if (options.stdoutPath) {
    await fs.writeFile(options.stdoutPath, stdout, 'utf8');
  }
  if (options.stderrPath) {
    await fs.writeFile(options.stderrPath, stderr, 'utf8');
  }

  return {
    exitCode: Number(exitCode ?? 1),
    stdout,
    stderr,
  };
}

export function startProcess(command, args, options) {
  const child = spawn(command, args, {
    cwd: options.cwd || ROOT,
    env: options.env || process.env,
    detached: process.platform !== 'win32',
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const chunks = [];
  const onData = (chunk) => {
    chunks.push(chunk.toString());
    if (chunks.length > 800) {
      chunks.shift();
    }
  };

  child.stdout.on('data', onData);
  child.stderr.on('data', onData);

  return {
    child,
    async flushLogs() {
      if (options.logPath) {
        await fs.writeFile(options.logPath, chunks.join(''), 'utf8');
      }
    },
  };
}

export async function stopProcess(handle) {
  if (!handle?.child) return;
  if (handle.child.killed) {
    await handle.flushLogs?.();
    return;
  }

  try {
    if (process.platform !== 'win32' && handle.child.pid) {
      process.kill(-handle.child.pid, 'SIGTERM');
    } else {
      handle.child.kill('SIGTERM');
    }
  } catch {
    handle.child.kill('SIGTERM');
  }
  const closed = await Promise.race([
    new Promise((resolve) => handle.child.on('close', resolve)),
    sleep(10_000).then(() => 'timeout'),
  ]);
  if (closed === 'timeout') {
    try {
      if (process.platform !== 'win32' && handle.child.pid) {
        process.kill(-handle.child.pid, 'SIGKILL');
      } else {
        handle.child.kill('SIGKILL');
      }
    } catch {
      handle.child.kill('SIGKILL');
    }
  }
  await handle.flushLogs?.();
}

export async function waitForHttp(url, options = {}) {
  const timeoutMs = Number(options.timeoutMs || 180_000);
  const validateResponse = options.validateResponse || ((response) => response.ok);
  const deadline = Date.now() + timeoutMs;
  let lastError = 'unreachable';

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (validateResponse(response)) {
        return;
      }
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(1_000);
  }

  throw new Error(`timed out waiting for ${url}: ${lastError}`);
}

function readCookiePairs(response) {
  if (typeof response.headers.getSetCookie === 'function') {
    return response.headers.getSetCookie();
  }
  const single = response.headers.get('set-cookie');
  return single ? [single] : [];
}

export class SessionClient {
  constructor(baseUrl) {
    this.baseUrl = String(baseUrl).replace(/\/$/, '');
    this.cookies = new Map();
  }

  cookieHeader() {
    return Array.from(this.cookies.values()).join('; ');
  }

  mergeCookies(response) {
    for (const setCookie of readCookiePairs(response)) {
      const pair = String(setCookie).split(';')[0];
      const [name] = pair.split('=');
      if (name) {
        this.cookies.set(name.trim(), pair.trim());
      }
    }
  }

  async request(method, endpoint, body) {
    const headers = {};
    if (this.cookies.size > 0) {
      headers.cookie = this.cookieHeader();
    }
    if (body !== undefined) {
      headers['content-type'] = 'application/json';
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      redirect: 'manual',
    });
    this.mergeCookies(response);

    const rawText = await response.text();
    const payload = rawText ? (() => {
      try {
        return JSON.parse(rawText);
      } catch {
        return rawText;
      }
    })() : null;

    if (!response.ok) {
      const detail = payload && typeof payload === 'object' ? JSON.stringify(payload) : String(payload ?? '');
      throw new Error(`${method} ${endpoint} failed: ${response.status} ${detail}`);
    }

    if (payload && typeof payload === 'object' && 'data' in payload) {
      return payload.data;
    }
    return payload;
  }

  get(endpoint) {
    return this.request('GET', endpoint);
  }

  post(endpoint, body) {
    return this.request('POST', endpoint, body);
  }

  delete(endpoint, body) {
    return this.request('DELETE', endpoint, body);
  }

  login(username, password, extra = {}) {
    return this.post('/auth/login', { username, password, ...extra });
  }

  register(username, password) {
    return this.post('/auth/register', { username, password });
  }
}

export function readPath(input, ...pathSegments) {
  return pathSegments.reduce((value, segment) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return undefined;
    }
    return value[segment];
  }, input);
}

export function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      return String(value);
    }
  }
  return null;
}
