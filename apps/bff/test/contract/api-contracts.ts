/**
 * T-045: API Contract Test
 * Validates BFF ↔ MCP interface contracts using JSON Schema.
 */
import Ajv from 'ajv';

const ajv = new Ajv({ allErrors: true });

// ── Schema Definitions ──

const QuoteSchema = {
    type: 'object',
    properties: {
        code: { type: 'string' },
        name: { type: 'string' },
        price: { type: 'number' },
        open: { type: 'number' },
        high: { type: 'number' },
        low: { type: 'number' },
        close: { type: 'number' },
        volume: { type: 'number' },
        change: { type: 'number' },
        changePct: { type: 'number' },
    },
    required: ['code'],
};

const KlineSchema = {
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
        required: ['date', 'open', 'high', 'low', 'close'],
    },
};

const BacktestResultSchema = {
    type: 'object',
    properties: {
        totalReturn: { type: 'number' },
        annualReturn: { type: 'number' },
        maxDrawdown: { type: 'number' },
        sharpeRatio: { type: 'number' },
        winRate: { type: 'number' },
        trades: { type: 'number' },
    },
};

const PortfolioSchema = {
    type: 'object',
    properties: {
        totalValue: { type: 'number' },
        totalCost: { type: 'number' },
        totalPnl: { type: 'number' },
        positions: {
            type: 'array',
            items: {
                type: 'object',
                properties: {
                    code: { type: 'string' },
                    name: { type: 'string' },
                    quantity: { type: 'number' },
                    avgCost: { type: 'number' },
                    marketValue: { type: 'number' },
                },
                required: ['code'],
            },
        },
    },
};

// ── Contract Definitions ──

export const CONTRACTS = {
    'GET /api/market/quote': {
        name: 'Quote',
        responseSchema: QuoteSchema,
    },
    'GET /api/market/kline': {
        name: 'Kline',
        responseSchema: KlineSchema,
    },
    'POST /api/backtest/run': {
        name: 'Backtest Result',
        responseSchema: BacktestResultSchema,
    },
    'GET /api/portfolio/list': {
        name: 'Portfolio',
        responseSchema: PortfolioSchema,
    },
};

/**
 * Validate a response against its contract schema.
 * Returns { valid: true } or { valid: false, errors: [...] }
 */
export function validateContract(
    endpoint: keyof typeof CONTRACTS,
    data: unknown,
): { valid: boolean; errors?: string[] } {
    const contract = CONTRACTS[endpoint];
    if (!contract) return { valid: false, errors: [`Unknown endpoint: ${endpoint}`] };

    const validate = ajv.compile(contract.responseSchema);
    const valid = validate(data);

    if (!valid) {
        return {
            valid: false,
            errors: validate.errors?.map((e) => `${e.instancePath} ${e.message}`) ?? ['Unknown validation error'],
        };
    }

    return { valid: true };
}

/**
 * Run all contract validations against sample data.
 */
export async function runContractTests(
    fetchFn: (endpoint: string) => Promise<unknown>,
): Promise<{ endpoint: string; name: string; valid: boolean; errors?: string[] }[]> {
    const results = [];

    for (const [endpoint, contract] of Object.entries(CONTRACTS)) {
        try {
            const data = await fetchFn(endpoint);
            const result = validateContract(endpoint as keyof typeof CONTRACTS, data);
            results.push({ endpoint, name: contract.name, ...result });
        } catch (e) {
            results.push({
                endpoint,
                name: contract.name,
                valid: false,
                errors: [`Fetch error: ${e instanceof Error ? e.message : String(e)}`],
            });
        }
    }

    return results;
}
