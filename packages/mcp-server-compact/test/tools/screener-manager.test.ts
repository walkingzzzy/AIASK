/**
 * screener_manager 工具测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
vi.mock('../../src/adapters/index.js', () => ({
    adapterManager: {
        getLimitUpStocks: vi.fn(),
        getDragonTiger: vi.fn(),
        getBatchQuotes: vi.fn(),
    },
}));

vi.mock('../../src/storage/screener-data.js', () => ({
    screenStocks: vi.fn(),
}));

describe('screener_manager', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('should sort by amount and apply exclude filters', async () => {
        const { adapterManager } = await import('../../src/adapters/index.js');
        (adapterManager.getLimitUpStocks as any).mockResolvedValue({
            success: true,
            data: [
                { code: '688001' },
                { code: '300001' },
                { code: '600001' },
                { code: '000002' },
            ],
        });
        (adapterManager.getDragonTiger as any).mockResolvedValue({
            success: true,
            data: [
                { code: '000001' },
            ],
        });
        (adapterManager.getBatchQuotes as any).mockResolvedValue({
            success: true,
            data: [
                { code: '600001', name: 'ST测试', amount: 500, price: 10, changePercent: 1.1, turnoverRate: 2.2 },
                { code: '000001', name: '正常A', amount: 200, price: 12, changePercent: 1.5, turnoverRate: 2.4 },
                { code: '000002', name: '正常B', amount: 100, price: 11, changePercent: 0.8, turnoverRate: 2.1 },
            ],
        });

        const { screenerManagerHandler } = await import('../../src/tools/handlers/screener.js');
        const result = await screenerManagerHandler({
            action: 'screen',
            query: '非ST 非科创 非创业 成交额由小到大',
            excludeST: true,
            excludeSTAR: true,
            excludeChiNext: true,
            sortBy: 'amount',
            sortOrder: 'asc',
            limit: 10,
        });

        expect(result.success).toBe(true);
        const results = (result.data as any).results;
        expect(results.length).toBe(2);
        expect(results[0].code).toBe('000002');
        expect(results[1].code).toBe('000001');
        expect(results.find((r: any) => r.code === '600001')).toBeUndefined();
        expect(results.find((r: any) => r.code === '688001')).toBeUndefined();
        expect(results.find((r: any) => r.code === '300001')).toBeUndefined();
    });

    it('should bypass realtime when only fundamental filters exist', async () => {
        const { screenStocks } = await import('../../src/storage/screener-data.js');
        (screenStocks as any).mockResolvedValue([
            { code: '000001', name: '正常A', pe: 10, pb: 1, roe: 12, sector: '银行' },
        ]);

        const { screenerManagerHandler } = await import('../../src/tools/handlers/screener.js');
        const result = await screenerManagerHandler({
            action: 'screen',
            peMin: 5,
            peMax: 20,
            limit: 10,
        });

        expect(result.success).toBe(true);
        const { adapterManager } = await import('../../src/adapters/index.js');
        expect(adapterManager.getBatchQuotes).not.toHaveBeenCalled();
        const results = (result.data as any).results;
        expect(results.length).toBe(1);
        expect(results[0].code).toBe('000001');
    });
});
