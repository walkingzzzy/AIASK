/**
 * technical_analysis_manager 工具测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
vi.mock('../../src/adapters/index.js', () => ({
    adapterManager: {
        getKline: vi.fn(),
    },
}));

function generateKlines(days: number) {
    const klines: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }> = [];
    const start = new Date('2024-01-01');
    let price = 100;

    for (let i = 0; i < days; i++) {
        price += 1;
        const date = new Date(start);
        date.setDate(start.getDate() + i);
        const close = price;
        klines.push({
            date: date.toISOString().slice(0, 10),
            open: close,
            high: close,
            low: close * 0.98,
            close,
            volume: 1000000,
        });
    }

    return klines;
}

describe('technical_analysis_manager', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('should return macd signal payload', async () => {
        const klines = generateKlines(60);
        const { adapterManager } = await import('../../src/adapters/index.js');
        (adapterManager.getKline as any).mockResolvedValue({ success: true, data: klines });

        const { technicalAnalysisManagerHandler } = await import('../../src/tools/handlers/technical-analysis.js');
        const result = await technicalAnalysisManagerHandler({
            action: 'check_macd_signal',
            code: '000001',
        });

        expect(result.success).toBe(true);
        expect(result.data).toBeDefined();

        const closes = klines.map(k => k.close);
        const TechnicalServices = await import('../../src/services/technical-analysis.js');
        const macd = TechnicalServices.calculateMACD(closes);
        const lastHist = macd.histogram[macd.histogram.length - 1];
        const prevHist = macd.histogram[macd.histogram.length - 2];
        const expectedSignal = lastHist > 0 && prevHist <= 0 ? 'buy' : 'hold';

        expect((result.data as any).signal).toBe(expectedSignal);
        expect((result.data as any).macdSignal).toBeDefined();
    });

    it('should return kdj overbought signal', async () => {
        const klines = generateKlines(30);
        const { adapterManager } = await import('../../src/adapters/index.js');
        (adapterManager.getKline as any).mockResolvedValue({ success: true, data: klines });

        const { technicalAnalysisManagerHandler } = await import('../../src/tools/handlers/technical-analysis.js');
        const result = await technicalAnalysisManagerHandler({
            action: 'check_kdj_signal',
            code: '000001',
        });

        expect(result.success).toBe(true);
        expect(result.data).toBeDefined();
        expect((result.data as any).signal).toBe('sell');
        expect((result.data as any).overbought).toBe(true);
    });
});
