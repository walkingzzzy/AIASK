import { BadGatewayException } from '@nestjs/common';
import type { ResultContractAliasHit, ResultContractMeta } from '@aiask/shared-types';

export const TOOL_CONTRACT_VERSION = '2026-04-22.v1';

type ToolCaller = (name: string, args: Record<string, unknown>) => Promise<unknown>;

type ToolAttemptTemplate = Record<string, string>;

type ToolContractDefinition = {
  canonicalTool: string;
  fallbackTools?: string[];
  aliases?: Record<string, string[]>;
  attempts?: ToolAttemptTemplate[];
};

type ToolContractInput = Record<string, unknown> | Array<Record<string, unknown>>;

export type ToolContractCallResult = {
  payload: unknown;
  argsMatched: Record<string, unknown>;
  canonicalArgs: Record<string, unknown>;
  aliasHits: ResultContractAliasHit[];
  canonicalTool: string;
  toolUsed: string;
  contractVersion: string;
};

const TOOL_CONTRACTS: Record<string, ToolContractDefinition> = {
  get_stock_research: {
    canonicalTool: 'get_stock_research',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code', limit: 'limit' }, { code: 'stock_code', limit: 'limit' }, { code: 'symbol', limit: 'limit' }],
  },
  get_stock_notices: {
    canonicalTool: 'get_stock_notices',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [
      { code: 'code', start_date: 'start_date', end_date: 'end_date', types: 'types' },
      { code: 'stock_code', start_date: 'start_date', end_date: 'end_date', types: 'types' },
      { code: 'symbol', start_date: 'start_date', end_date: 'end_date', types: 'types' },
    ],
  },
  get_stock_news: {
    canonicalTool: 'get_stock_news',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code', limit: 'limit' }, { code: 'stock_code', limit: 'limit' }, { code: 'symbol', limit: 'limit' }],
  },
  get_profit_forecast: {
    canonicalTool: 'get_profit_forecast',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_realtime_quote: {
    canonicalTool: 'get_realtime_quote',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_order_book: {
    canonicalTool: 'get_order_book',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_kline_data: {
    canonicalTool: 'get_kline_data',
    fallbackTools: ['get_kline'],
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [
      { code: 'code', period: 'period', limit: 'limit', start_date: 'start_date', end_date: 'end_date', adjust: 'adjust' },
      { code: 'stock_code', period: 'period', limit: 'limit', start_date: 'start_date', end_date: 'end_date', adjust: 'adjust' },
    ],
  },
  get_minute_kline: {
    canonicalTool: 'get_minute_kline',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code', period: 'period', limit: 'limit' }, { code: 'stock_code', period: 'period', limit: 'limit' }],
  },
  get_trade_details: {
    canonicalTool: 'get_trade_details',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code', limit: 'limit' }, { code: 'stock_code', limit: 'limit' }],
  },
  get_financials: {
    canonicalTool: 'get_financials',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_valuation_metrics: {
    canonicalTool: 'get_valuation_metrics',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_historical_valuation: {
    canonicalTool: 'get_historical_valuation',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code', days: 'days' }, { code: 'stock_code', days: 'days' }, { code: 'symbol', days: 'days' }],
  },
  get_stock_capital: {
    canonicalTool: 'get_stock_capital',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  relative_valuation: {
    canonicalTool: 'relative_valuation',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code', metrics: 'metrics' }, { code: 'stock_code', metrics: 'metrics' }, { code: 'symbol', metrics: 'metrics' }],
  },
  get_stock_info: {
    canonicalTool: 'get_stock_info',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_stock_fund_flow: {
    canonicalTool: 'get_stock_fund_flow',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  get_north_fund_holding: {
    canonicalTool: 'get_north_fund_holding',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  smart_stock_diagnosis: {
    canonicalTool: 'smart_stock_diagnosis',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  should_i_buy: {
    canonicalTool: 'should_i_buy',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [{ code: 'code' }, { code: 'stock_code' }, { code: 'symbol' }],
  },
  should_i_sell: {
    canonicalTool: 'should_i_sell',
    aliases: { code: ['stock_code', 'symbol'] },
    attempts: [
      { code: 'code', buy_price: 'buy_price', holding_days: 'holding_days' },
      { code: 'stock_code', buy_price: 'buy_price', holding_days: 'holding_days' },
    ],
  },
};

function stableStringify(value: Record<string, unknown>) {
  return JSON.stringify(
    Object.keys(value)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = value[key];
        return acc;
      }, {}),
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function definedEntries(value: Record<string, unknown>) {
  return Object.entries(value).filter(([, item]) => item !== undefined);
}

function inferCanonicalArgs(definition: ToolContractDefinition, input: ToolContractInput) {
  const attempts = Array.isArray(input) ? input : [input];
  const canonicalArgs: Record<string, unknown> = {};
  const aliasLookup = new Map<string, string>();
  for (const [canonical, aliases] of Object.entries(definition.aliases ?? {})) {
    aliasLookup.set(canonical, canonical);
    for (const alias of aliases) {
      aliasLookup.set(alias, canonical);
    }
  }

  for (const attempt of attempts) {
    for (const [key, value] of Object.entries(asRecord(attempt))) {
      if (value === undefined) continue;
      const canonicalKey = aliasLookup.get(key) ?? key;
      if (!(canonicalKey in canonicalArgs)) {
        canonicalArgs[canonicalKey] = value;
      }
    }
  }

  return Object.fromEntries(definedEntries(canonicalArgs));
}

function buildAttempts(definition: ToolContractDefinition, canonicalArgs: Record<string, unknown>) {
  if (definition.attempts?.length) {
    const mapped = definition.attempts
      .map((template) => {
        const attempt: Record<string, unknown> = {};
        for (const [canonicalKey, matchedKey] of Object.entries(template)) {
          if (canonicalArgs[canonicalKey] !== undefined) {
            attempt[matchedKey] = canonicalArgs[canonicalKey];
          }
        }
        return attempt;
      })
      .filter((attempt) => Object.keys(attempt).length > 0);
    return dedupeAttempts(mapped);
  }

  const attempts: Array<Record<string, unknown>> = [{ ...canonicalArgs }];
  for (const [canonicalKey, aliases] of Object.entries(definition.aliases ?? {})) {
    if (canonicalArgs[canonicalKey] === undefined) continue;
    for (const alias of aliases) {
      const attempt = { ...canonicalArgs };
      delete attempt[canonicalKey];
      attempt[alias] = canonicalArgs[canonicalKey];
      attempts.push(attempt);
    }
  }
  return dedupeAttempts(attempts);
}

function dedupeAttempts(attempts: Array<Record<string, unknown>>) {
  const seen = new Set<string>();
  return attempts.filter((attempt) => {
    const normalized = Object.fromEntries(definedEntries(attempt));
    const key = stableStringify(normalized);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function buildAliasHits(
  definition: ToolContractDefinition,
  argsMatched: Record<string, unknown>,
): ResultContractAliasHit[] {
  const hits: ResultContractAliasHit[] = [];
  const matchedKeys = new Set(Object.keys(argsMatched));
  for (const [canonical, aliases] of Object.entries(definition.aliases ?? {})) {
    for (const alias of aliases) {
      if (matchedKeys.has(alias)) {
        hits.push({ canonical, matched: alias, deprecated: true });
      }
    }
    if (matchedKeys.has(canonical)) {
      hits.push({ canonical, matched: canonical, deprecated: false });
    }
  }
  return hits;
}

export function buildResultContractMeta(input: Omit<ResultContractMeta, 'contractVersion'>): ResultContractMeta {
  return {
    ...input,
    contractVersion: TOOL_CONTRACT_VERSION,
  };
}

export async function callToolWithContract(
  primaryTool: string,
  input: ToolContractInput,
  callTool: ToolCaller,
  extraFallbackTools: string[] = [],
): Promise<ToolContractCallResult> {
  const definition = TOOL_CONTRACTS[primaryTool] ?? { canonicalTool: primaryTool };
  const canonicalArgs = inferCanonicalArgs(definition, input);
  const attempts = buildAttempts(definition, canonicalArgs);
  const tools = [primaryTool, ...(definition.fallbackTools ?? []), ...extraFallbackTools].filter(Boolean);
  let lastError: unknown = null;

  for (const tool of tools) {
    for (const args of attempts) {
      try {
        const payload = await callTool(tool, args);
        return {
          payload,
          argsMatched: args,
          canonicalArgs,
          aliasHits: buildAliasHits(definition, args),
          canonicalTool: definition.canonicalTool,
          toolUsed: tool,
          contractVersion: TOOL_CONTRACT_VERSION,
        };
      } catch (error) {
        lastError = error;
      }
    }
  }

  throw new BadGatewayException({
    success: false,
    message: `调用 MCP ${primaryTool} 失败`,
    detail: lastError instanceof Error ? lastError.message : String(lastError),
  });
}
