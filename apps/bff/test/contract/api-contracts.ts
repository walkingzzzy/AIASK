/**
 * API contract smoke definitions for key BFF endpoints.
 *
 * These schemas intentionally follow the real frontend-consumed envelope:
 * { success, data, traceId? }.
 */
import Ajv from 'ajv';

const ajv = new Ajv({ allErrors: true });

const cacheMetaSchema = {
  type: 'object',
  properties: {
    fetchedAt: { type: 'string' },
    cache: {
      type: 'object',
      properties: {
        hit: { type: 'boolean' },
        backend: { type: 'string' },
        ttlSeconds: { type: 'number' },
      },
      required: ['hit'],
    },
  },
};

const envelope = (dataSchema: Record<string, unknown>) => ({
  type: 'object',
  properties: {
    success: { type: 'boolean' },
    data: dataSchema,
    traceId: { type: 'string' },
  },
  required: ['success', 'data'],
});

const nullableNumber = { type: ['number', 'null'] };

const quoteSchema = envelope({
  type: 'object',
  properties: {
    quote: {
      type: 'object',
      properties: {
        code: { type: 'string' },
        name: { type: 'string' },
        price: nullableNumber,
        changePercent: nullableNumber,
        volume: nullableNumber,
      },
      required: ['code', 'name'],
    },
    tool: { type: 'string' },
    meta: cacheMetaSchema,
  },
  required: ['quote', 'tool', 'meta'],
});

const klineSchema = envelope({
  type: 'object',
  properties: {
    kline: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          date: { type: 'string' },
          open: { type: 'number' },
          high: { type: 'number' },
          low: { type: 'number' },
          close: { type: 'number' },
          volume: { type: 'number' },
        },
        required: ['date', 'open', 'high', 'low', 'close', 'volume'],
      },
    },
    tool: { type: 'string' },
    meta: cacheMetaSchema,
  },
  required: ['kline', 'tool', 'meta'],
});

const alertsSchema = envelope({
  type: 'object',
  properties: {
    status: { type: 'string' },
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          code: { type: 'string' },
          indicator: { type: 'string' },
          condition: { type: 'string' },
          value: nullableNumber,
        },
        required: ['id', 'code', 'indicator', 'condition'],
      },
    },
    meta: cacheMetaSchema,
  },
  required: ['status', 'items', 'meta'],
});

const riskSummarySchema = envelope({
  type: 'object',
  properties: {
    portfolioId: { type: ['number', 'null'] },
    lookbackDays: { type: 'number' },
    degraded: { type: 'boolean' },
    empty: { type: 'boolean' },
    sourceContext: {
      type: 'object',
      properties: {
        mode: { type: 'string' },
      },
      required: ['mode'],
    },
    moduleStatus: {
      type: 'object',
      properties: {
        var: { type: 'object' },
        stress: { type: 'object' },
        exposure: { type: 'object' },
      },
      required: ['var', 'stress', 'exposure'],
    },
    meta: cacheMetaSchema,
  },
  required: ['portfolioId', 'lookbackDays', 'degraded', 'empty', 'sourceContext', 'moduleStatus', 'meta'],
});

const notificationsSchema = envelope({
  type: 'object',
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          type: { type: 'string' },
          level: { type: 'string' },
          title: { type: 'string' },
          body: { type: 'string' },
          read: { type: 'boolean' },
          createdAt: { type: 'string' },
        },
        required: ['id', 'type', 'level', 'title', 'body', 'read', 'createdAt'],
      },
    },
    total: { type: 'number' },
    unread: { type: 'number' },
  },
  required: ['items', 'total', 'unread'],
});

const portfolioRiskSchema = envelope({
  type: 'object',
  properties: {
    riskMetrics: {
      type: 'object',
      properties: {
        var95: nullableNumber,
        var99: nullableNumber,
        cvar: nullableNumber,
        beta: nullableNumber,
        volatility: nullableNumber,
        riskContribution: {
          type: 'object',
          additionalProperties: { type: 'number' },
        },
      },
      required: ['riskContribution'],
    },
  },
  required: ['riskMetrics'],
});

export const CONTRACTS = {
  'GET /market/quote': {
    name: 'Quote Envelope',
    responseSchema: quoteSchema,
  },
  'GET /market/kline': {
    name: 'Kline Envelope',
    responseSchema: klineSchema,
  },
  'GET /alerts/list': {
    name: 'Alerts Envelope',
    responseSchema: alertsSchema,
  },
  'GET /risk/summary': {
    name: 'Risk Summary Envelope',
    responseSchema: riskSummarySchema,
  },
  'GET /notifications/list': {
    name: 'Notifications Envelope',
    responseSchema: notificationsSchema,
  },
  'POST /portfolio/risk-analysis': {
    name: 'Portfolio Risk Envelope',
    responseSchema: portfolioRiskSchema,
  },
} as const;

export function validateContract(
  endpoint: keyof typeof CONTRACTS,
  data: unknown,
): { valid: boolean; errors?: string[] } {
  const contract = CONTRACTS[endpoint];
  if (!contract) {
    return { valid: false, errors: [`Unknown endpoint: ${endpoint}`] };
  }

  const validate = ajv.compile(contract.responseSchema);
  const valid = validate(data);

  if (!valid) {
    return {
      valid: false,
      errors: validate.errors?.map((error) => `${error.instancePath} ${error.message}`) ?? ['Unknown validation error'],
    };
  }

  return { valid: true };
}

export async function runContractTests(
  fetchFn: (endpoint: string) => Promise<unknown>,
): Promise<{ endpoint: string; name: string; valid: boolean; errors?: string[] }[]> {
  const results: Array<{ endpoint: string; name: string; valid: boolean; errors?: string[] }> = [];

  for (const [endpoint, contract] of Object.entries(CONTRACTS)) {
    try {
      const data = await fetchFn(endpoint);
      const result = validateContract(endpoint as keyof typeof CONTRACTS, data);
      results.push({ endpoint, name: contract.name, ...result });
    } catch (error) {
      results.push({
        endpoint,
        name: contract.name,
        valid: false,
        errors: [`Fetch error: ${error instanceof Error ? error.message : String(error)}`],
      });
    }
  }

  return results;
}
