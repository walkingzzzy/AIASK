#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '..');
const webRoot = path.join(repoRoot, 'apps', 'web');
const bffRoot = path.join(repoRoot, 'apps', 'bff');
const defaultOutDir = path.join(repoRoot, 'artifacts', 'data-quality-diagnosis');

const SOURCE_EXT_RE = /\.(tsx?|mjs|jsx?)$/;
const IGNORED_DIRS = new Set([
  '.git',
  '.next',
  'dist',
  'node_modules',
  'coverage',
  '__pycache__',
]);

const TRUST_META_KEYS = new Set([
  'data_quality',
  'result_contract',
  'fallback_used',
  'local_fallback_used',
  'fallback_reason',
  'degraded',
  'transport',
  'traceId',
  'meta',
  'contract_meta',
  'success',
  'ok',
  'message',
  'error',
]);

function parseArgs(argv) {
  const args = {
    bffBaseUrl: process.env.DATA_QUALITY_BFF_BASE_URL
      || process.env.BFF_BASE_URL
      || process.env.NEXT_PUBLIC_BFF_BASE_URL
      || 'http://127.0.0.1:3001/api',
    outDir: defaultOutDir,
    username: process.env.DATA_QUALITY_DIAG_USERNAME || process.env.AIASK_DIAG_USERNAME || '',
    password: process.env.DATA_QUALITY_DIAG_PASSWORD || process.env.AIASK_DIAG_PASSWORD || '',
    codes: ['000988', '600519', '000001'],
    timeoutMs: Number(process.env.DATA_QUALITY_PROBE_TIMEOUT_MS || 10_000),
    skipProbes: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    const readValue = () => {
      if (item.includes('=')) return item.split('=').slice(1).join('=');
      index += 1;
      return argv[index] ?? '';
    };
    if (item === '--skip-probes') args.skipProbes = true;
    else if (item.startsWith('--bff')) args.bffBaseUrl = readValue();
    else if (item.startsWith('--out-dir')) args.outDir = path.resolve(repoRoot, readValue());
    else if (item.startsWith('--username')) args.username = readValue();
    else if (item.startsWith('--password')) args.password = readValue();
    else if (item.startsWith('--codes')) {
      args.codes = readValue()
        .split(',')
        .map((code) => code.trim())
        .filter(Boolean);
    } else if (item.startsWith('--timeout-ms')) {
      args.timeoutMs = Number(readValue());
    }
  }

  args.bffBaseUrl = String(args.bffBaseUrl || '').replace(/\/$/, '');
  if (!Number.isFinite(args.timeoutMs) || args.timeoutMs <= 0) args.timeoutMs = 10_000;
  return args;
}

function walk(dir, predicate = () => true) {
  if (!fs.existsSync(dir)) return [];
  const output = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (IGNORED_DIRS.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      output.push(...walk(full, predicate));
    } else if (predicate(full)) {
      output.push(full);
    }
  }
  return output;
}

function read(file) {
  return fs.readFileSync(file, 'utf8');
}

function rel(file) {
  return path.relative(repoRoot, file).split(path.sep).join('/');
}

function lineOf(source, offset) {
  return source.slice(0, offset).split('\n').length;
}

function routeFromWebFile(file) {
  const appDir = path.join(webRoot, 'app');
  if (!file.startsWith(appDir)) return null;
  const relDir = path.relative(appDir, path.dirname(file));
  if (path.basename(file) !== 'page.tsx' && path.basename(file) !== 'page.ts') return null;
  if (!relDir) return '/';
  return `/${relDir.split(path.sep).join('/')}`;
}

function firstLiteralProp(snippet, prop) {
  return snippet.match(new RegExp(`${prop}\\s*=\\s*["']([^"']+)["']`))?.[1] ?? '';
}

function balancedSnippet(source, start, openChar = '(', closeChar = ')') {
  const open = source.indexOf(openChar, start);
  if (open < 0) return '';
  let depth = 0;
  let quote = '';
  let escaped = false;
  for (let index = open; index < source.length; index += 1) {
    const ch = source[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = '';
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
      continue;
    }
    if (ch === openChar) depth += 1;
    if (ch === closeChar) depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  return source.slice(start);
}

function firstCallArgument(callSnippet) {
  const open = callSnippet.indexOf('(');
  if (open < 0) return '';
  let depth = 0;
  let quote = '';
  let escaped = false;
  for (let index = open + 1; index < callSnippet.length; index += 1) {
    const ch = callSnippet[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = '';
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch;
      continue;
    }
    if (ch === '(' || ch === '{' || ch === '[') depth += 1;
    if (ch === ')' || ch === '}' || ch === ']') depth -= 1;
    if (depth === 0 && ch === ',') return callSnippet.slice(open + 1, index).trim();
  }
  return callSnippet.slice(open + 1, -1).trim();
}

function compactSnippet(snippet, max = 220) {
  const oneLine = snippet.replace(/\s+/g, ' ').trim();
  return oneLine.length > max ? `${oneLine.slice(0, max - 1)}...` : oneLine;
}

function collectMatches(source, re) {
  return [...source.matchAll(re)].map((match) => match[1]).filter(Boolean);
}

function scanWeb() {
  const roots = ['app', 'components', 'hooks', 'lib', 'store'].map((item) => path.join(webRoot, item));
  const files = roots.flatMap((root) => walk(root, (file) => SOURCE_EXT_RE.test(file))).sort();
  const banners = [];
  const states = [];
  const queries = [];
  const mutations = [];
  const rejectUsages = [];
  const parserGuards = [];

  for (const file of files) {
    const source = read(file);
    const route = routeFromWebFile(file);
    for (const match of source.matchAll(/<DataQualityBanner\b[\s\S]*?\/>/g)) {
      const snippet = match[0];
      banners.push({
        file: rel(file),
        line: lineOf(source, match.index ?? 0),
        route,
        title: firstLiteralProp(snippet, 'title') || '数据源降级',
        trustExpression: snippet.match(/trust=\{([^}]+)\}/)?.[1]?.trim() ?? '',
      });
    }
    for (const component of ['ErrorState', 'EmptyState', 'UnavailableState', 'PageStatusCard']) {
      const re = new RegExp(`<${component}\\b[\\s\\S]*?(?:/>|</${component}>)`, 'g');
      for (const match of source.matchAll(re)) {
        const snippet = match[0];
        states.push({
          component,
          file: rel(file),
          line: lineOf(source, match.index ?? 0),
          route,
          text: firstLiteralProp(snippet, 'text') || firstLiteralProp(snippet, 'title') || '',
          hint: firstLiteralProp(snippet, 'hint') || '',
        });
      }
    }
    for (const match of source.matchAll(/\buseApiQuery(?:<[^>]+>)?\s*\(/g)) {
      const snippet = balancedSnippet(source, match.index ?? 0);
      queries.push({
        file: rel(file),
        line: lineOf(source, match.index ?? 0),
        route,
        pathExpression: compactSnippet(firstCallArgument(snippet), 180),
        critical: /\bcritical\s*:\s*true\b/.test(snippet),
        nonFatal: /\bnonFatal\s*:\s*true\b/.test(snippet),
        hasFallbackData: /\bfallbackData\s*:/.test(snippet),
        hasReject: /\breject\s*:/.test(snippet),
        timeoutMs: snippet.match(/\btimeoutMs\s*:\s*([0-9_]+)/)?.[1]?.replace(/_/g, '') ?? '',
        parseLabels: [
          ...collectMatches(snippet, /ensureRecord(?:OrArray|)\([^,]+,\s*['"]([^'"]+)['"]/g),
          ...collectMatches(snippet, /ensureArray\([^,]+,\s*['"]([^'"]+)['"]/g),
        ],
      });
    }
    for (const match of source.matchAll(/\buseApiMutation(?:<[^>]+>)?\s*\(/g)) {
      const snippet = balancedSnippet(source, match.index ?? 0);
      mutations.push({
        file: rel(file),
        line: lineOf(source, match.index ?? 0),
        route,
        critical: /\bcritical\s*:\s*true\b/.test(snippet),
        parseLabels: collectMatches(snippet, /ensureRecord(?:OrArray|)\([^,]+,\s*['"]([^'"]+)['"]/g),
      });
    }
    for (const match of source.matchAll(/\brejectFallbackPayload\b/g)) {
      rejectUsages.push({
        file: rel(file),
        line: lineOf(source, match.index ?? 0),
        route,
      });
    }
    for (const match of source.matchAll(/\bensure(?:RecordOrArray|Record|Array)\([^,]+,\s*['"]([^'"]+)['"]/g)) {
      parserGuards.push({
        file: rel(file),
        line: lineOf(source, match.index ?? 0),
        route,
        label: match[1],
      });
    }
  }

  return {
    filesScanned: files.length,
    banners,
    states,
    queries,
    mutations,
    rejectUsages,
    parserGuards,
    counts: {
      dataQualityBanners: banners.length,
      statusStates: states.length,
      apiQueries: queries.length,
      criticalQueries: queries.filter((item) => item.critical).length,
      nonFatalQueries: queries.filter((item) => item.nonFatal).length,
      criticalMutations: mutations.filter((item) => item.critical).length,
      rejectFallbackUsages: rejectUsages.length,
      parserGuards: parserGuards.length,
    },
  };
}

function scanBff() {
  const controllerFiles = walk(path.join(bffRoot, 'src'), (file) => /\.controller\.ts$/.test(file)).sort();
  const srcFiles = walk(path.join(bffRoot, 'src'), (file) => /\.ts$/.test(file)).sort();
  const endpoints = [];
  const qualitySites = [];
  const tools = [];

  for (const file of controllerFiles) {
    const source = read(file);
    const prefix = source.match(/@Controller\(\s*['"]([^'"]+)['"]\s*\)/)?.[1] ?? '';
    for (const match of source.matchAll(/@(Get|Post|Put|Delete|Patch)\(\s*(?:['"]([^'"]*)['"])?\s*\)\s*[\s\S]*?(?:async\s+)?(\w+)\s*\(/g)) {
      const method = match[1].toUpperCase();
      const routePath = [prefix, match[2] ?? ''].filter(Boolean).join('/');
      const start = match.index ?? 0;
      const end = source.indexOf('\n  @', start + 1);
      const snippet = source.slice(start, end > start ? end : start + 900);
      endpoints.push({
        method,
        path: `/api/${routePath}`.replace(/\/+/g, '/'),
        handler: match[3],
        file: rel(file),
        line: lineOf(source, start),
        serviceCall: snippet.match(/this\.[A-Za-z0-9_]+\.([A-Za-z0-9_]+)\(/)?.[1] ?? '',
      });
    }
  }

  for (const file of srcFiles) {
    const source = read(file);
    const interestingLineRe = /(data_quality|result_contract|acceptanceStatus|fallback_used|local_fallback_used|unavailableDataQuality|degradedDataQuality|trustedDataQuality|buildDataQuality|buildMcpTransportFailureDetail)/g;
    for (const match of source.matchAll(interestingLineRe)) {
      const offset = match.index ?? 0;
      const lineStart = source.lastIndexOf('\n', offset) + 1;
      const lineEnd = source.indexOf('\n', offset);
      qualitySites.push({
        file: rel(file),
        line: lineOf(source, offset),
        signal: match[1],
        snippet: compactSnippet(source.slice(lineStart, lineEnd > lineStart ? lineEnd : lineStart + 220), 180),
      });
    }
    for (const match of source.matchAll(/\b(?:callTool|callWithArgs|callToolWithContract)\(\s*['"]([^'"]+)['"]/g)) {
      tools.push({
        file: rel(file),
        line: lineOf(source, match.index ?? 0),
        tool: match[1],
      });
    }
  }

  return {
    endpoints,
    qualitySites,
    tools,
    counts: {
      endpoints: endpoints.length,
      qualitySites: qualitySites.length,
      tools: tools.length,
      unavailableQualitySites: qualitySites.filter((item) => item.signal === 'unavailableDataQuality').length,
      degradedQualitySites: qualitySites.filter((item) => item.signal === 'degradedDataQuality').length,
      resultContractSites: qualitySites.filter((item) => item.signal === 'result_contract').length,
    },
  };
}

function splitSetCookie(header) {
  if (!header) return [];
  return String(header).split(/,(?=\s*[^;,=\s]+=[^;,]+)/g).map((item) => item.trim()).filter(Boolean);
}

function cookiePair(setCookie) {
  return String(setCookie).split(';')[0]?.trim() ?? '';
}

function pickSetCookies(headers) {
  if (typeof headers.getSetCookie === 'function') return headers.getSetCookie();
  return splitSetCookie(headers.get('set-cookie'));
}

async function fetchJson(url, options = {}, timeoutMs = 10_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const startedAt = Date.now();
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const text = await response.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { nonJsonBody: text.slice(0, 500) };
    }
    return {
      ok: response.ok,
      status: response.status,
      headers: response.headers,
      body,
      durationMs: Date.now() - startedAt,
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      headers: null,
      body: null,
      durationMs: Date.now() - startedAt,
      fetchError: error instanceof Error ? error.message : String(error),
    };
  } finally {
    clearTimeout(timer);
  }
}

function isRecord(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function unwrapEnvelope(body) {
  if (isRecord(body) && Object.prototype.hasOwnProperty.call(body, 'data')) return body.data;
  return body;
}

function findRecordWithKey(value, key, seen = new Set(), depth = 0) {
  if (!isRecord(value) || seen.has(value) || depth > 8) return null;
  seen.add(value);
  if (isRecord(value[key])) return value[key];
  for (const nested of Object.values(value)) {
    if (!nested || typeof nested !== 'object') continue;
    if (Array.isArray(nested)) {
      for (const item of nested) {
        const hit = findRecordWithKey(item, key, seen, depth + 1);
        if (hit) return hit;
      }
    } else {
      const hit = findRecordWithKey(nested, key, seen, depth + 1);
      if (hit) return hit;
    }
  }
  return null;
}

function findAny(value, predicate, seen = new Set(), depth = 0) {
  if (!isRecord(value) || seen.has(value) || depth > 8) return null;
  seen.add(value);
  if (predicate(value)) return value;
  for (const nested of Object.values(value)) {
    if (!nested || typeof nested !== 'object') continue;
    if (Array.isArray(nested)) {
      for (const item of nested) {
        const hit = findAny(item, predicate, seen, depth + 1);
        if (hit) return hit;
      }
    } else {
      const hit = findAny(nested, predicate, seen, depth + 1);
      if (hit) return hit;
    }
  }
  return null;
}

function firstArrayLength(...values) {
  for (const value of values) {
    if (Array.isArray(value)) return value.length;
  }
  return null;
}

function meaningfulObjectValueCount(record) {
  if (!isRecord(record)) return 0;
  return Object.entries(record)
    .filter(([key]) => !TRUST_META_KEYS.has(key))
    .filter(([, value]) => value != null && value !== '' && !(Array.isArray(value) && value.length === 0))
    .length;
}

function deriveSampleCount(data) {
  if (!isRecord(data)) return Array.isArray(data) ? data.length : 0;
  const directCount = Number(data.count ?? data.total ?? data.peerCount ?? data.peer_count);
  if (Number.isFinite(directCount) && directCount >= 0) return directCount;
  const nestedData = isRecord(data.data) ? data.data : {};
  const arrays = firstArrayLength(
    data.kline,
    data.points,
    data.reports,
    data.notices,
    data.items,
    data.blocks,
    data.stocks,
    data.flows,
    data.trades,
    data.peers,
    nestedData.flows,
    nestedData.items,
    nestedData.stocks,
  );
  if (arrays != null) return arrays;
  if (isRecord(data.orderBook)) {
    return (Array.isArray(data.orderBook.bids) ? data.orderBook.bids.length : 0)
      + (Array.isArray(data.orderBook.asks) ? data.orderBook.asks.length : 0);
  }
  if (isRecord(data.quote)) {
    const quote = data.quote;
    return [quote.price, quote.last, quote.changePercent, quote.volume].some((item) => item != null && item !== '') ? 1 : 0;
  }
  return meaningfulObjectValueCount(data);
}

function extractProbeSignals(body) {
  const data = unwrapEnvelope(body);
  const dataQuality = findRecordWithKey(data, 'data_quality') || (isRecord(data) ? data.data_quality : null);
  const resultContract = findRecordWithKey(data, 'result_contract') || (isRecord(data) ? data.result_contract : null);
  const fallbackNode = findAny(data, (record) =>
    record.fallback_used === true
    || record.local_fallback_used === true
    || record.degraded === true
    || record.fallback_reason != null,
  );
  const platformMeta = isRecord(resultContract?.platformMeta)
    ? resultContract.platformMeta
    : null;

  return {
    traceId: isRecord(body) && typeof body.traceId === 'string' ? body.traceId : '',
    acceptanceStatus: isRecord(body) && typeof body.acceptanceStatus === 'string' ? body.acceptanceStatus : '',
    dataQuality: dataQuality ? {
      status: String(dataQuality.status ?? ''),
      reasons: Array.isArray(dataQuality.reasons) ? dataQuality.reasons.map(String) : [],
      qualityFlags: Array.isArray(dataQuality.quality_flags) ? dataQuality.quality_flags.map(String) : [],
      emptyReason: String(dataQuality.empty_reason ?? ''),
      sources: Array.isArray(dataQuality.sources) ? dataQuality.sources : [],
    } : null,
    resultContract: resultContract ? {
      status: String(resultContract.status ?? ''),
      summary: String(resultContract.summary ?? ''),
      riskNotes: Array.isArray(resultContract.riskNotes) ? resultContract.riskNotes.map(String) : [],
      fallbackReason: Array.isArray(platformMeta?.fallbackReason) ? platformMeta.fallbackReason.map(String) : [],
      degraded: platformMeta?.degraded === true,
      sourceTool: String(platformMeta?.sourceTool ?? ''),
    } : null,
    fallback: fallbackNode ? {
      degraded: fallbackNode.degraded === true,
      fallbackUsed: fallbackNode.fallback_used === true,
      localFallbackUsed: fallbackNode.local_fallback_used === true,
      fallbackReason: Array.isArray(fallbackNode.fallback_reason)
        ? fallbackNode.fallback_reason.map(String)
        : fallbackNode.fallback_reason != null
          ? [String(fallbackNode.fallback_reason)]
          : [],
    } : null,
    sampleCount: deriveSampleCount(data),
  };
}

function classifyProbe(probe) {
  const dqStatus = probe.signals?.dataQuality?.status ?? '';
  const rcStatus = probe.signals?.resultContract?.status ?? '';
  const fallback = probe.signals?.fallback;
  const sampleCount = probe.signals?.sampleCount ?? 0;

  if (/abort/i.test(String(probe.fetchError ?? ''))) return 'probe_timeout_bff_or_upstream_slow';
  if (probe.fetchError) return 'bff_unreachable';
  if (probe.status === 401 || probe.status === 403) return 'auth_required';
  if (probe.status >= 500) return probe.signals?.acceptanceStatus ? 'mcp_transport_unavailable' : 'bff_server_error';
  if (dqStatus === 'unavailable') return 'upstream_unavailable';
  if (dqStatus === 'empty') return 'upstream_empty_or_valid_empty';
  if (fallback?.fallbackUsed || fallback?.localFallbackUsed) return sampleCount > 0 ? 'fallback_with_business_data' : 'fallback_only_empty';
  if (dqStatus === 'degraded' || rcStatus === 'degraded' || fallback?.degraded) return sampleCount > 0 ? 'degraded_with_business_data' : 'degraded_empty';
  if (dqStatus === 'partial') return sampleCount > 0 ? 'partial_valid_data_display_policy' : 'partial_without_samples';
  if (sampleCount === 0 && probe.ok) return 'empty_payload_without_quality_contract';
  return 'trusted_or_unclassified';
}

function buildProbeDefinitions(codes) {
  const stockEndpoints = [
    { id: 'quote', page: '/stock,/market', method: 'GET', path: (code) => `/market/quote?code=${code}` },
    { id: 'kline_daily', page: '/stock,/market', method: 'GET', path: (code) => `/market/kline?code=${code}&period=daily&limit=250` },
    { id: 'order_book', page: '/stock,/market', method: 'GET', path: (code) => `/market/order-book?code=${code}` },
    { id: 'stock_fund_flow', page: '/stock,/fund-flow', method: 'GET', path: (code) => `/fund-flow/stock?code=${code}` },
    { id: 'fundamental_overview', page: '/stock,/fundamental', method: 'GET', path: (code) => `/fundamental/overview?code=${code}` },
    { id: 'research_list', page: '/research', method: 'GET', path: (code) => `/research/list?code=${code}&days=30&limit=20` },
    { id: 'stock_news', page: '/stock,/research', method: 'GET', path: (code) => `/research/stock-news?code=${code}&limit=10` },
    { id: 'sentiment_stock', page: '/stock,/sentiment', method: 'GET', path: (code) => `/sentiment/stock?code=${code}` },
    {
      id: 'technical_indicators',
      page: '/stock,/technical',
      method: 'POST',
      path: () => '/technical/indicators',
      body: (code) => ({ code, indicators: ['RSI', 'MACD', 'KDJ'], period: 'daily', limit: 120 }),
    },
  ];
  const sharedEndpoints = [
    { id: 'health_ready', page: 'system', method: 'GET', path: () => '/health/ready', public: true },
    { id: 'market_blocks', page: '/,/market', method: 'GET', path: () => '/market/blocks?blockType=industry&limit=20' },
    { id: 'limit_up_stats', page: '/,/market', method: 'GET', path: () => '/market/limit-up-stats' },
    { id: 'sector_fund_flow', page: '/,/fund-flow', method: 'GET', path: () => '/fund-flow/sector' },
    { id: 'north_fund', page: '/,/fund-flow', method: 'GET', path: () => '/fund-flow/north' },
    { id: 'fear_greed', page: '/,/sentiment', method: 'GET', path: () => '/sentiment/fear-greed' },
  ];
  return [
    ...sharedEndpoints.map((endpoint) => ({ ...endpoint, code: '' })),
    ...codes.flatMap((code) => stockEndpoints.map((endpoint) => ({ ...endpoint, code }))),
  ];
}

async function runWithConcurrency(items, concurrency, worker) {
  const output = [];
  let next = 0;
  async function runOne() {
    while (next < items.length) {
      const current = next;
      next += 1;
      output[current] = await worker(items[current], current);
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, concurrency) }, runOne));
  return output;
}

async function runProbes(options) {
  const notes = [];
  const cookieJar = new Map();
  const setCookies = (headers) => {
    if (!headers) return;
    for (const cookie of pickSetCookies(headers)) {
      const pair = cookiePair(cookie);
      const name = pair.split('=')[0];
      if (name) cookieJar.set(name, pair);
    }
  };
  const cookieHeader = () => [...cookieJar.values()].join('; ');
  const request = async (probe) => {
    const url = `${options.bffBaseUrl}${probe.path(probe.code)}`;
    const headers = { 'content-type': 'application/json' };
    const cookies = cookieHeader();
    if (cookies) headers.cookie = cookies;
    const result = await fetchJson(
      url,
      {
        method: probe.method,
        headers,
        ...(probe.body ? { body: JSON.stringify(probe.body(probe.code)) } : {}),
      },
      options.timeoutMs,
    );
    setCookies(result.headers);
    const signals = result.body ? extractProbeSignals(result.body) : null;
    const row = {
      id: probe.id,
      page: probe.page,
      code: probe.code,
      method: probe.method,
      path: probe.path(probe.code),
      ok: result.ok,
      status: result.status,
      durationMs: result.durationMs,
      fetchError: result.fetchError ?? '',
      signals,
    };
    return { ...row, classification: classifyProbe(row) };
  };

  const health = await request({
    id: 'health_ready',
    page: 'system',
    code: '',
    method: 'GET',
    path: () => '/health/ready',
  });

  let auth = { attempted: false, ok: false, status: null, note: 'no credentials provided' };
  if (options.username && options.password && !health.fetchError) {
    auth = { attempted: true, ok: false, status: null, note: '' };
    const login = await fetchJson(`${options.bffBaseUrl}/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username: options.username, password: options.password }),
    }, options.timeoutMs);
    setCookies(login.headers);
    auth.status = login.status;
    auth.ok = login.ok;
    auth.note = login.ok ? 'login succeeded' : `login failed (${login.status || login.fetchError || 'unknown'})`;
  } else if (health.fetchError) {
    auth.note = 'BFF unreachable; login skipped';
  }
  notes.push(auth.note);

  const definitions = buildProbeDefinitions(options.codes)
    .filter((probe) => probe.id !== 'health_ready');
  const probes = [health, ...await runWithConcurrency(definitions, 3, request)];
  const countsByClassification = probes.reduce((acc, probe) => {
    acc[probe.classification] = (acc[probe.classification] ?? 0) + 1;
    return acc;
  }, {});

  return {
    bffBaseUrl: options.bffBaseUrl,
    codes: options.codes,
    timeoutMs: options.timeoutMs,
    auth,
    notes,
    probes,
    countsByClassification,
  };
}

function table(headers, rows) {
  const escape = (value) => String(value ?? '').replace(/\|/g, '\\|').replace(/\n/g, '<br>');
  return [
    `| ${headers.map(escape).join(' | ')} |`,
    `| ${headers.map(() => '---').join(' | ')} |`,
    ...rows.map((row) => `| ${row.map(escape).join(' | ')} |`),
  ].join('\n');
}

function csvEscape(value) {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function writeCsv(file, headers, rows) {
  const content = [
    headers.map(csvEscape).join(','),
    ...rows.map((row) => row.map(csvEscape).join(',')),
  ].join('\n');
  fs.writeFileSync(file, `${content}\n`);
}

function topRows(items, limit = 40) {
  return items.slice(0, limit);
}

function reasonText(probe) {
  const signals = probe.signals ?? {};
  const dq = signals.dataQuality;
  const rc = signals.resultContract;
  const fb = signals.fallback;
  return [
    dq?.reasons?.join('; '),
    dq?.emptyReason,
    dq?.qualityFlags?.join('; '),
    rc?.riskNotes?.join('; '),
    rc?.fallbackReason?.join('; '),
    fb?.fallbackReason?.join('; '),
    probe.fetchError,
  ].filter(Boolean).join(' / ');
}

function renderReport({ web, bff, probes }, generatedAt) {
  const probeRows = probes?.probes ?? [];
  const severeProbes = probeRows.filter((probe) => ![
    'trusted_or_unclassified',
    'partial_valid_data_display_policy',
    'degraded_with_business_data',
    'fallback_with_business_data',
    'upstream_empty_or_valid_empty',
  ].includes(probe.classification));
  const validEmptyRows = probeRows.filter((probe) => probe.classification === 'upstream_empty_or_valid_empty');
  const partialRows = probeRows.filter((probe) => [
    'partial_valid_data_display_policy',
    'degraded_with_business_data',
    'fallback_with_business_data',
  ].includes(probe.classification));
  const focusedBffEndpoints = bff.endpoints.filter((item) =>
    /^\/api\/(?:market|fund-flow|fundamental|research|technical|sentiment|valuation|health)\b/.test(item.path),
  );

  const sections = [];
  sections.push(`# 前端数据异常诊断报告\n\n生成时间：${generatedAt}\n`);
  sections.push(`## 摘要\n\n- 前端扫描文件：${web.filesScanned} 个；关键查询：${web.counts.criticalQueries}/${web.counts.apiQueries}；数据质量横幅：${web.counts.dataQualityBanners}；parser guard：${web.counts.parserGuards}。\n- BFF 扫描接口：${bff.counts.endpoints} 个；质量契约信号：${bff.counts.qualitySites} 处；MCP/工具调用信号：${bff.counts.tools} 处。\n- API 探针：${probeRows.length} 条；分类：${Object.entries(probes?.countsByClassification ?? {}).map(([key, value]) => `${key}=${value}`).join('，') || '未运行'}。\n`);

  sections.push(`## 当前结论\n\n- 前端的“数据异常”首先由信任门禁触发：\`critical: true\` 查询会拒绝 fallback、空壳、不可用结果，避免把占位值当真实行情。\n- BFF 已广泛写入 \`data_quality\` 与 \`result_contract\`，真实问题需要按接口追溯到 MCP/AKShare、DB fallback、缓存和前端 parser。\n- 若分类为 \`probe_timeout_bff_or_upstream_slow\`，说明探针在前端常见超时窗口内未等到 BFF 响应；BFF 日志或 trace 需要继续确认是否为 MCP/AKShare 慢响应、连接池自愈或工具层阻塞。\n- 若分类为 \`partial_valid_data_display_policy\`、\`degraded_with_business_data\` 或 \`fallback_with_business_data\`，说明可能存在“有业务样本但页面策略隐藏/泛化提示”的后续修复空间。\n`);

  sections.push(`## 前端关键查询样本\n\n${table(
    ['Route', 'File', 'Line', 'Critical', 'NonFatal', 'Path/Expr', 'Parser'],
    topRows(web.queries.filter((item) => item.critical || item.nonFatal), 60).map((item) => [
      item.route ?? '',
      item.file,
      item.line,
      item.critical ? 'yes' : '',
      item.nonFatal ? 'yes' : '',
      item.pathExpression,
      item.parseLabels.join(', '),
    ]),
  )}\n`);

  sections.push(`## 数据质量横幅样本\n\n${table(
    ['Route', 'File', 'Line', 'Title', 'Trust'],
    topRows(web.banners, 60).map((item) => [item.route ?? '', item.file, item.line, item.title, item.trustExpression]),
  )}\n`);

  sections.push(`## BFF 接口与服务调用样本\n\n${table(
    ['Method', 'Path', 'Handler', 'Service Call', 'File', 'Line'],
    topRows(focusedBffEndpoints, 80).map((item) => [item.method, item.path, item.handler, item.serviceCall, item.file, item.line]),
  )}\n`);

  if (probeRows.length > 0) {
    sections.push(`## API 探针环境\n\n- BFF：${probes.bffBaseUrl}\n- 代码：${probes.codes.join(', ')}\n- 登录：${probes.auth.attempted ? probes.auth.note : '未提供登录凭据'}\n- 超时：${probes.timeoutMs}ms\n`);
    sections.push(`## API 探针结果\n\n${table(
      ['Page', 'Endpoint', 'Code', 'HTTP', 'Class', 'DQ', 'RC', 'Samples', 'Reason'],
      probeRows.map((probe) => [
        probe.page,
        `${probe.method} ${probe.path}`,
        probe.code,
        probe.status,
        probe.classification,
        probe.signals?.dataQuality?.status ?? '',
        probe.signals?.resultContract?.status ?? '',
        probe.signals?.sampleCount ?? '',
        reasonText(probe).slice(0, 220),
      ]),
    )}\n`);
    sections.push(`## 需要优先排查的探针\n\n${severeProbes.length ? table(
      ['Endpoint', 'Code', 'Class', 'HTTP', 'Reason'],
      severeProbes.map((probe) => [`${probe.method} ${probe.path}`, probe.code, probe.classification, probe.status, reasonText(probe).slice(0, 260)]),
    ) : '当前探针没有发现 fallback-only、不可用或空壳类阻断。'}\n`);
    sections.push(`## 有效空结果\n\n${validEmptyRows.length ? table(
      ['Endpoint', 'Code', 'DQ', 'RC', 'Reason'],
      validEmptyRows.map((probe) => [`${probe.method} ${probe.path}`, probe.code, probe.signals?.dataQuality?.status ?? '', probe.signals?.resultContract?.status ?? '', reasonText(probe).slice(0, 260)]),
    ) : '当前探针没有发现已标注的有效空结果。'}\n`);
    sections.push(`## 可能被显示策略误伤的数据\n\n${partialRows.length ? table(
      ['Endpoint', 'Code', 'Class', 'DQ', 'Samples', 'Reason'],
      partialRows.map((probe) => [`${probe.method} ${probe.path}`, probe.code, probe.classification, probe.signals?.dataQuality?.status ?? '', probe.signals?.sampleCount ?? '', reasonText(probe).slice(0, 260)]),
    ) : '当前探针没有发现“有业务样本但降级/部分可用”的结果。'}\n`);
  } else {
    sections.push('## API 探针结果\n\n本次使用 `--skip-probes`，只生成静态诊断。\n');
  }

  sections.push(`## 后续修复建议\n\n- 对 \`probe_timeout_bff_or_upstream_slow\`：先查 BFF audit trace、MCP pool 自愈日志和对应工具耗时，再决定是提高页面超时、加缓存预热，还是把慢接口改为可解释的异步/部分结果。\n- 对 \`upstream_unavailable\` 和 \`mcp_transport_unavailable\`：先查 MCP/AKShare 链路、工具参数和上游超时，再决定是否做本地 DB 预热。\n- 对 \`fallback_only_empty\` 和 \`upstream_empty_or_valid_empty\`：确认是否交易时段/节假日正常空值；否则补充 empty reason 与来源样本。\n- 对 \`partial_valid_data_display_policy\`：前端应展示可验证样本并给出精确质量提示，避免统一变成“数据异常”。\n- 对 parser guard 报错：以 BFF DTO/result contract 为准修对齐，不在页面里吞掉结构错误。\n`);

  return sections.join('\n');
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const generatedAt = new Date().toISOString();
  fs.mkdirSync(options.outDir, { recursive: true });

  const web = scanWeb();
  const bff = scanBff();
  const probes = options.skipProbes
    ? { probes: [], countsByClassification: {}, bffBaseUrl: options.bffBaseUrl, codes: options.codes, timeoutMs: options.timeoutMs, auth: { attempted: false, note: 'skipped' } }
    : await runProbes(options);

  const payload = { generatedAt, options: { ...options, password: options.password ? '[redacted]' : '' }, web, bff, probes };
  const jsonPath = path.join(options.outDir, 'data-quality-diagnosis.json');
  const reportPath = path.join(options.outDir, 'data-quality-diagnosis.md');
  const webCsvPath = path.join(options.outDir, 'frontend-query-matrix.csv');
  const bffCsvPath = path.join(options.outDir, 'bff-data-contract-matrix.csv');
  const probeCsvPath = path.join(options.outDir, 'api-probe-matrix.csv');
  fs.writeFileSync(jsonPath, `${JSON.stringify(payload, null, 2)}\n`);
  fs.writeFileSync(reportPath, renderReport({ web, bff, probes }, generatedAt));
  writeCsv(
    webCsvPath,
    ['route', 'file', 'line', 'critical', 'nonFatal', 'pathExpression', 'parserLabels'],
    web.queries.map((item) => [
      item.route ?? '',
      item.file,
      item.line,
      item.critical ? 'yes' : 'no',
      item.nonFatal ? 'yes' : 'no',
      item.pathExpression,
      item.parseLabels.join('; '),
    ]),
  );
  writeCsv(
    bffCsvPath,
    ['method', 'path', 'handler', 'serviceCall', 'file', 'line'],
    bff.endpoints.map((item) => [item.method, item.path, item.handler, item.serviceCall, item.file, item.line]),
  );
  writeCsv(
    probeCsvPath,
    ['page', 'method', 'path', 'code', 'httpStatus', 'classification', 'durationMs', 'dataQualityStatus', 'resultContractStatus', 'sampleCount', 'reason'],
    probes.probes.map((probe) => [
      probe.page,
      probe.method,
      probe.path,
      probe.code,
      probe.status,
      probe.classification,
      probe.durationMs,
      probe.signals?.dataQuality?.status ?? '',
      probe.signals?.resultContract?.status ?? '',
      probe.signals?.sampleCount ?? '',
      reasonText(probe),
    ]),
  );

  console.log(`Data quality diagnosis written:`);
  console.log(`- ${path.relative(repoRoot, reportPath)}`);
  console.log(`- ${path.relative(repoRoot, jsonPath)}`);
  console.log(`- ${path.relative(repoRoot, webCsvPath)}`);
  console.log(`- ${path.relative(repoRoot, bffCsvPath)}`);
  console.log(`- ${path.relative(repoRoot, probeCsvPath)}`);
  console.log(`Static: critical queries=${web.counts.criticalQueries}, banners=${web.counts.dataQualityBanners}, BFF quality sites=${bff.counts.qualitySites}`);
  if (probes.probes.length > 0) {
    console.log(`Probes: ${Object.entries(probes.countsByClassification).map(([key, value]) => `${key}=${value}`).join(', ')}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
