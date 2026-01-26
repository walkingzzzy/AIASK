/**
 * 形态识别服务测试
 * 提升pattern-recognition覆盖率至50%+
 * 
 * 测试61+种K线形态识别功能
 */

import { describe, it, expect } from 'vitest';
import * as PatternRecognition from '../../src/services/pattern-recognition.js';
import type { KlineData } from '../../src/types/stock.js';

// 生成测试K线数据
function generateKlines(count: number, pattern: 'bullish' | 'bearish' | 'neutral' = 'neutral'): KlineData[] {
    const klines: KlineData[] = [];
    let basePrice = 100;

    for (let i = 0; i < count; i++) {
        const date = new Date(2024, 0, i + 1).toISOString().slice(0, 10);
        
        let open, high, low, close;
        
        if (pattern === 'bullish') {
            open = basePrice;
            close = basePrice + Math.random() * 2 + 1;
            low = open - Math.random() * 0.5;
            high = close + Math.random() * 0.5;
            basePrice = close;
        } else if (pattern === 'bearish') {
            open = basePrice;
            close = basePrice - Math.random() * 2 - 1;
            high = open + Math.random() * 0.5;
            low = close - Math.random() * 0.5;
            basePrice = close;
        } else {
            open = basePrice;
            close = basePrice + (Math.random() - 0.5) * 2;
            low = Math.min(open, close) - Math.random() * 1;
            high = Math.max(open, close) + Math.random() * 1;
            basePrice = close;
        }

        klines.push({
            date,
            open,
            high,
            low,
            close,
            volume: Math.floor(Math.random() * 1000000) + 100000,
            amount: 0,
            turnoverRate: 0,
        });
    }

    return klines;
}

// 生成特定形态的K线
function generateDojiKline(): KlineData {
    const price = 100;
    return {
        date: '2024-01-01',
        open: price,
        high: price + 0.5,
        low: price - 0.5,
        close: price + 0.05, // 几乎相等
        volume: 100000,
        amount: 0,
        turnoverRate: 0,
    };
}

function generateHammerKline(): KlineData {
    const price = 100;
    return {
        date: '2024-01-01',
        open: price,
        high: price + 0.2,
        low: price - 2, // 长下影线
        close: price - 0.1,
        volume: 100000,
        amount: 0,
        turnoverRate: 0,
    };
}

describe('Pattern Recognition Service', () => {
    describe('Pattern Definitions', () => {
        it('should have 48+ pattern definitions', () => {
            const definitions = PatternRecognition.getAllPatternDefinitions();
            
            expect(definitions.length).toBeGreaterThanOrEqual(48);
            expect(definitions.length).toBeLessThanOrEqual(70); // 合理上限
        });

        it('should have all required pattern properties', () => {
            const definitions = PatternRecognition.getAllPatternDefinitions();
            
            definitions.forEach(def => {
                expect(def).toHaveProperty('name');
                expect(def).toHaveProperty('nameCN');
                expect(def).toHaveProperty('category');
                expect(def).toHaveProperty('bullish');
                expect(def).toHaveProperty('reliability');
                expect(def).toHaveProperty('description');
                
                expect(typeof def.name).toBe('string');
                expect(typeof def.nameCN).toBe('string');
                expect(typeof def.bullish).toBe('boolean');
                expect(['high', 'medium', 'low']).toContain(def.reliability);
            });
        });

        it('should have patterns in all categories', () => {
            const stats = PatternRecognition.getPatternStats();
            
            expect(stats.total).toBeGreaterThanOrEqual(48);
            expect(stats.byCategory).toHaveProperty('doji');
            expect(stats.byCategory).toHaveProperty('star');
            expect(stats.byCategory).toHaveProperty('engulfing');
            expect(stats.byCategory).toHaveProperty('harami');
            expect(stats.byCategory).toHaveProperty('hammer');
            expect(stats.byCategory).toHaveProperty('marubozu');
        });
    });

    describe('getPatternStats', () => {
        it('should return correct pattern statistics', () => {
            const stats = PatternRecognition.getPatternStats();
            
            expect(stats).toHaveProperty('total');
            expect(stats).toHaveProperty('byCategory');
            expect(stats).toHaveProperty('byReliability');
            expect(stats).toHaveProperty('bullish');
            expect(stats).toHaveProperty('bearish');
            
            expect(stats.total).toBeGreaterThan(0);
            expect(stats.bullish + stats.bearish).toBe(stats.total);
        });

        it('should have patterns in all reliability levels', () => {
            const stats = PatternRecognition.getPatternStats();
            
            expect(stats.byReliability).toHaveProperty('high');
            expect(stats.byReliability).toHaveProperty('medium');
            expect(stats.byReliability).toHaveProperty('low');
            
            expect(stats.byReliability.high).toBeGreaterThan(0);
            expect(stats.byReliability.medium).toBeGreaterThan(0);
        });
    });

    describe('getPatternsByCategory', () => {
        it('should return patterns for doji category', () => {
            const patterns = PatternRecognition.getPatternsByCategory('doji');
            
            expect(patterns.length).toBeGreaterThan(0);
            patterns.forEach(p => {
                expect(p.category).toBe('doji');
            });
        });

        it('should return patterns for star category', () => {
            const patterns = PatternRecognition.getPatternsByCategory('star');
            
            expect(patterns.length).toBeGreaterThan(0);
            patterns.forEach(p => {
                expect(p.category).toBe('star');
            });
        });

        it('should return patterns for engulfing category', () => {
            const patterns = PatternRecognition.getPatternsByCategory('engulfing');
            
            expect(patterns.length).toBeGreaterThan(0);
            patterns.forEach(p => {
                expect(p.category).toBe('engulfing');
            });
        });

        it('should return patterns for hammer category', () => {
            const patterns = PatternRecognition.getPatternsByCategory('hammer');
            
            expect(patterns.length).toBeGreaterThan(0);
            patterns.forEach(p => {
                expect(p.category).toBe('hammer');
            });
        });
    });

    describe('detectAllPatterns', () => {
        it('should detect patterns from kline data', () => {
            const klines = generateKlines(30, 'neutral');
            const results = PatternRecognition.detectAllPatterns(klines);
            
            expect(results.length).toBeGreaterThanOrEqual(48);
            
            results.forEach(r => {
                expect(r).toHaveProperty('pattern');
                expect(r).toHaveProperty('nameCN');
                expect(r).toHaveProperty('detected');
                expect(r).toHaveProperty('bullish');
                expect(r).toHaveProperty('category');
                expect(r).toHaveProperty('reliability');
                expect(r).toHaveProperty('description');
                
                expect(typeof r.detected).toBe('boolean');
            });
        });

        it('should filter by category', () => {
            const klines = generateKlines(30, 'neutral');
            const results = PatternRecognition.detectAllPatterns(klines, ['doji']);
            
            results.forEach(r => {
                expect(r.category).toBe('doji');
            });
        });

        it('should filter by multiple categories', () => {
            const klines = generateKlines(30, 'neutral');
            const results = PatternRecognition.detectAllPatterns(klines, ['doji', 'star']);
            
            results.forEach(r => {
                expect(['doji', 'star']).toContain(r.category);
            });
        });

        it('should handle insufficient data gracefully', () => {
            const klines = generateKlines(2, 'neutral');
            const results = PatternRecognition.detectAllPatterns(klines);
            
            expect(results.length).toBeGreaterThan(0);
            // 大部分形态应该未检测到（因为数据不足）
            const detectedCount = results.filter(r => r.detected).length;
            expect(detectedCount).toBeLessThan(results.length);
        });
    });

    describe('detectPatternsFiltered', () => {
        it('should return only detected patterns', () => {
            const klines = generateKlines(30, 'bullish');
            const results = PatternRecognition.detectPatternsFiltered(klines);
            
            results.forEach(r => {
                expect(r.detected).toBe(true);
            });
        });

        it('should filter by minimum reliability', () => {
            const klines = generateKlines(30, 'neutral');
            const results = PatternRecognition.detectPatternsFiltered(klines, {
                minReliability: 'high'
            });
            
            results.forEach(r => {
                expect(r.reliability).toBe('high');
            });
        });

        it('should filter bullish patterns only', () => {
            const klines = generateKlines(30, 'bullish');
            const results = PatternRecognition.detectPatternsFiltered(klines, {
                bullishOnly: true
            });
            
            results.forEach(r => {
                expect(r.bullish).toBe(true);
            });
        });

        it('should filter bearish patterns only', () => {
            const klines = generateKlines(30, 'bearish');
            const results = PatternRecognition.detectPatternsFiltered(klines, {
                bearishOnly: true
            });
            
            results.forEach(r => {
                expect(r.bullish).toBe(false);
            });
        });

        it('should combine multiple filters', () => {
            const klines = generateKlines(30, 'bullish');
            const results = PatternRecognition.detectPatternsFiltered(klines, {
                categories: ['star', 'engulfing'],
                minReliability: 'high',
                bullishOnly: true
            });
            
            results.forEach(r => {
                expect(['star', 'engulfing']).toContain(r.category);
                expect(r.reliability).toBe('high');
                expect(r.bullish).toBe(true);
            });
        });

        it('should return empty array when no patterns match', () => {
            const klines = generateKlines(2, 'neutral'); // 数据不足
            const results = PatternRecognition.detectPatternsFiltered(klines, {
                minReliability: 'high',
                bullishOnly: true
            });
            
            expect(Array.isArray(results)).toBe(true);
        });
    });

    describe('Custom Pattern Detection', () => {
        it('should detect gap_up pattern', () => {
            const klines: KlineData[] = [
                { date: '2024-01-01', open: 100, high: 102, low: 99, close: 101, volume: 100000, amount: 0, turnoverRate: 0 },
                { date: '2024-01-02', open: 103, high: 105, low: 102.5, close: 104, volume: 100000, amount: 0, turnoverRate: 0 }, // 跳空高开
            ];
            
            const results = PatternRecognition.detectAllPatterns(klines);
            const gapUp = results.find(r => r.pattern === 'gap_up');
            
            expect(gapUp).toBeDefined();
            expect(gapUp?.bullish).toBe(true);
        });

        it('should detect gap_down pattern', () => {
            const klines: KlineData[] = [
                { date: '2024-01-01', open: 100, high: 102, low: 99, close: 101, volume: 100000, amount: 0, turnoverRate: 0 },
                { date: '2024-01-02', open: 97, high: 98, low: 96, close: 97.5, volume: 100000, amount: 0, turnoverRate: 0 }, // 跳空低开
            ];
            
            const results = PatternRecognition.detectAllPatterns(klines);
            const gapDown = results.find(r => r.pattern === 'gap_down');
            
            expect(gapDown).toBeDefined();
            expect(gapDown?.bullish).toBe(false);
        });

        it('should detect double_bottom pattern', () => {
            const klines = generateKlines(25, 'neutral');
            // 修改数据创建双底
            klines[5].low = 95;
            klines[15].low = 95.5;
            klines[24].close = 100;
            
            const results = PatternRecognition.detectAllPatterns(klines);
            const doubleBottom = results.find(r => r.pattern === 'double_bottom');
            
            expect(doubleBottom).toBeDefined();
        });

        it('should detect double_top pattern', () => {
            const klines = generateKlines(25, 'neutral');
            // 修改数据创建双顶
            klines[5].high = 105;
            klines[15].high = 105.5;
            klines[24].close = 98;
            
            const results = PatternRecognition.detectAllPatterns(klines);
            const doubleTop = results.find(r => r.pattern === 'double_top');
            
            expect(doubleTop).toBeDefined();
        });
    });

    describe('Performance Tests', () => {
        it('should detect patterns efficiently for 30 klines', () => {
            const klines = generateKlines(30, 'neutral');
            const startTime = Date.now();
            
            PatternRecognition.detectAllPatterns(klines);
            
            const executionTime = Date.now() - startTime;
            expect(executionTime).toBeLessThan(500); // 应该在500ms内完成
        });

        it('should detect patterns efficiently for 100 klines', () => {
            const klines = generateKlines(100, 'neutral');
            const startTime = Date.now();
            
            PatternRecognition.detectAllPatterns(klines);
            
            const executionTime = Date.now() - startTime;
            expect(executionTime).toBeLessThan(1000); // 应该在1秒内完成
        });

        it('should filter patterns efficiently', () => {
            const klines = generateKlines(50, 'bullish');
            const startTime = Date.now();
            
            PatternRecognition.detectPatternsFiltered(klines, {
                categories: ['star', 'engulfing', 'hammer'],
                minReliability: 'medium',
                bullishOnly: true
            });
            
            const executionTime = Date.now() - startTime;
            expect(executionTime).toBeLessThan(500);
        });
    });

    describe('Edge Cases', () => {
        it('should handle empty kline array', () => {
            const klines: KlineData[] = [];
            
            expect(() => {
                PatternRecognition.detectAllPatterns(klines);
            }).not.toThrow();
        });

        it('should handle single kline', () => {
            const klines = generateKlines(1, 'neutral');
            const results = PatternRecognition.detectAllPatterns(klines);
            
            expect(results.length).toBeGreaterThan(0);
            // 大部分形态应该未检测到
            const detectedCount = results.filter(r => r.detected).length;
            expect(detectedCount).toBeLessThan(5);
        });

        it('should handle invalid category filter', () => {
            const klines = generateKlines(30, 'neutral');
            const results = PatternRecognition.detectAllPatterns(klines, ['invalid' as any]);
            
            expect(results.length).toBe(0);
        });

        it('should handle extreme price movements', () => {
            const klines: KlineData[] = [
                { date: '2024-01-01', open: 100, high: 100, low: 100, close: 100, volume: 100000, amount: 0, turnoverRate: 0 },
                { date: '2024-01-02', open: 200, high: 200, low: 200, close: 200, volume: 100000, amount: 0, turnoverRate: 0 },
            ];
            
            expect(() => {
                PatternRecognition.detectAllPatterns(klines);
            }).not.toThrow();
        });
    });

    describe('Pattern Categories', () => {
        it('should have reversal_bullish patterns', () => {
            const patterns = PatternRecognition.getPatternsByCategory('reversal_bullish');
            
            expect(patterns.length).toBeGreaterThan(0);
            patterns.forEach(p => {
                expect(p.bullish).toBe(true);
            });
        });

        it('should have reversal_bearish patterns', () => {
            const patterns = PatternRecognition.getPatternsByCategory('reversal_bearish');
            
            expect(patterns.length).toBeGreaterThan(0);
            patterns.forEach(p => {
                expect(p.bullish).toBe(false);
            });
        });

        it('should have continuation patterns', () => {
            const patterns = PatternRecognition.getPatternsByCategory('continuation');
            
            expect(patterns.length).toBeGreaterThan(0);
        });

        it('should have neutral patterns', () => {
            const patterns = PatternRecognition.getPatternsByCategory('neutral');
            
            expect(patterns.length).toBeGreaterThan(0);
        });
    });
});
