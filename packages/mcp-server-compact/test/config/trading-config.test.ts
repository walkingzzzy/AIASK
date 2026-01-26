/**
 * 交易配置测试
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
    getTradingConfig,
    setTradingConfig,
    resetTradingConfig,
    useTradingPreset,
    calculateTradingCost,
    isInTradingHours,
    isPriceLimited,
    DEFAULT_TRADING_CONFIG,
    CONSERVATIVE_CONFIG,
    AGGRESSIVE_CONFIG
} from '../../src/config/trading-config.js';

describe('Trading Configuration', () => {
    beforeEach(() => {
        resetTradingConfig();
    });

    describe('getTradingConfig', () => {
        it('should return default config initially', () => {
            const config = getTradingConfig();
            expect(config.commission).toBe(DEFAULT_TRADING_CONFIG.commission);
            expect(config.slippage).toBe(DEFAULT_TRADING_CONFIG.slippage);
        });

        it('should return a copy of config', () => {
            const config1 = getTradingConfig();
            const config2 = getTradingConfig();
            expect(config1).not.toBe(config2); // Different objects
            expect(config1).toEqual(config2); // Same values
        });
    });

    describe('setTradingConfig', () => {
        it('should update config partially', () => {
            setTradingConfig({ commission: 0.0005 });
            const config = getTradingConfig();
            expect(config.commission).toBe(0.0005);
            expect(config.slippage).toBe(DEFAULT_TRADING_CONFIG.slippage); // Unchanged
        });

        it('should update multiple fields', () => {
            setTradingConfig({
                commission: 0.0005,
                slippage: 0.002,
                maxSinglePosition: 0.15
            });
            const config = getTradingConfig();
            expect(config.commission).toBe(0.0005);
            expect(config.slippage).toBe(0.002);
            expect(config.maxSinglePosition).toBe(0.15);
        });
    });

    describe('resetTradingConfig', () => {
        it('should reset to default config', () => {
            setTradingConfig({ commission: 0.0005 });
            resetTradingConfig();
            const config = getTradingConfig();
            expect(config.commission).toBe(DEFAULT_TRADING_CONFIG.commission);
        });
    });

    describe('useTradingPreset', () => {
        it('should use conservative preset', () => {
            useTradingPreset('conservative');
            const config = getTradingConfig();
            expect(config.maxSinglePosition).toBe(CONSERVATIVE_CONFIG.maxSinglePosition);
            expect(config.stopLoss).toBe(CONSERVATIVE_CONFIG.stopLoss);
        });

        it('should use aggressive preset', () => {
            useTradingPreset('aggressive');
            const config = getTradingConfig();
            expect(config.maxSinglePosition).toBe(AGGRESSIVE_CONFIG.maxSinglePosition);
            expect(config.stopLoss).toBe(AGGRESSIVE_CONFIG.stopLoss);
        });

        it('should use default preset', () => {
            useTradingPreset('conservative');
            useTradingPreset('default');
            const config = getTradingConfig();
            expect(config.maxSinglePosition).toBe(DEFAULT_TRADING_CONFIG.maxSinglePosition);
        });
    });

    describe('calculateTradingCost', () => {
        it('should calculate buy cost correctly', () => {
            const cost = calculateTradingCost(10000, 'buy');
            expect(cost.commission).toBeGreaterThan(0);
            expect(cost.stampDuty).toBe(0); // No stamp duty on buy
            expect(cost.total).toBe(cost.commission);
        });

        it('should calculate sell cost correctly', () => {
            const cost = calculateTradingCost(10000, 'sell');
            expect(cost.commission).toBeGreaterThan(0);
            expect(cost.stampDuty).toBeGreaterThan(0); // Stamp duty on sell
            expect(cost.total).toBe(cost.commission + cost.stampDuty);
        });

        it('should apply minimum commission', () => {
            const cost = calculateTradingCost(100, 'buy'); // Very small amount
            expect(cost.commission).toBe(DEFAULT_TRADING_CONFIG.minCommission);
        });

        it('should use custom config', () => {
            const customConfig = {
                ...DEFAULT_TRADING_CONFIG,
                commission: 0.001,
                minCommission: 1
            };
            const cost = calculateTradingCost(10000, 'buy', customConfig);
            expect(cost.commission).toBe(10); // 10000 * 0.001
        });
    });

    describe('isInTradingHours', () => {
        it('should return true for morning trading hours', () => {
            const morningTime = new Date('2024-01-01 10:00:00');
            expect(isInTradingHours(morningTime)).toBe(true);
        });

        it('should return true for afternoon trading hours', () => {
            const afternoonTime = new Date('2024-01-01 14:00:00');
            expect(isInTradingHours(afternoonTime)).toBe(true);
        });

        it('should return false for lunch break', () => {
            const lunchTime = new Date('2024-01-01 12:00:00');
            expect(isInTradingHours(lunchTime)).toBe(false);
        });

        it('should return false for after hours', () => {
            const afterHours = new Date('2024-01-01 16:00:00');
            expect(isInTradingHours(afterHours)).toBe(false);
        });

        it('should return false for before market open', () => {
            const beforeOpen = new Date('2024-01-01 09:00:00');
            expect(isInTradingHours(beforeOpen)).toBe(false);
        });
    });

    describe('isPriceLimited', () => {
        it('should detect limit up', () => {
            const result = isPriceLimited(110, 100, false);
            expect(result.isLimitUp).toBe(true);
            expect(result.isLimitDown).toBe(false);
            expect(result.limitUpPrice).toBeCloseTo(110, 2);
        });

        it('should detect limit down', () => {
            const result = isPriceLimited(90, 100, false);
            expect(result.isLimitUp).toBe(false);
            expect(result.isLimitDown).toBe(true);
            expect(result.limitDownPrice).toBeCloseTo(90, 2);
        });

        it('should use ST limit for ST stocks', () => {
            const result = isPriceLimited(105, 100, true);
            expect(result.isLimitUp).toBe(true);
            expect(result.limitUpPrice).toBeCloseTo(105, 2);
        });

        it('should return false for normal price', () => {
            const result = isPriceLimited(105, 100, false);
            expect(result.isLimitUp).toBe(false);
            expect(result.isLimitDown).toBe(false);
        });
    });

    describe('Preset Configurations', () => {
        it('conservative should be more restrictive than default', () => {
            expect(CONSERVATIVE_CONFIG.maxSinglePosition).toBeLessThan(DEFAULT_TRADING_CONFIG.maxSinglePosition);
            expect(CONSERVATIVE_CONFIG.maxDrawdown).toBeLessThan(DEFAULT_TRADING_CONFIG.maxDrawdown);
            expect(CONSERVATIVE_CONFIG.stopLoss).toBeLessThan(DEFAULT_TRADING_CONFIG.stopLoss);
        });

        it('aggressive should be less restrictive than default', () => {
            expect(AGGRESSIVE_CONFIG.maxSinglePosition).toBeGreaterThan(DEFAULT_TRADING_CONFIG.maxSinglePosition);
            expect(AGGRESSIVE_CONFIG.maxDrawdown).toBeGreaterThan(DEFAULT_TRADING_CONFIG.maxDrawdown);
            expect(AGGRESSIVE_CONFIG.stopLoss).toBeGreaterThan(DEFAULT_TRADING_CONFIG.stopLoss);
        });
    });
});
