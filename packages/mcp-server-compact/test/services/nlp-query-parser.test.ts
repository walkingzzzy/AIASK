/**
 * NLP查询解析单元测试
 */

import { describe, it, expect } from 'vitest';
import { NLPQueryParser } from '../../src/services/nlp-query-parser.js';

describe('NLPQueryParser', () => {
    const parser = new NLPQueryParser();

    it('should parse exclude flags and sorting', () => {
        const result = parser.parseQuery('非ST 非科创 成交额由小到大');
        const fields = result.conditions.map(c => c.field);

        expect(fields).toContain('exclude_st');
        expect(fields).toContain('exclude_star');
        expect(result.sortBy).toBeDefined();
        expect(result.sortBy?.field).toBe('amount');
        expect(result.sortBy?.order).toBe('asc');
    });

    it('should parse amount condition', () => {
        const result = parser.parseQuery('成交额大于100');
        const amountCond = result.conditions.find(c => c.field === 'amount');
        expect(amountCond).toBeDefined();
        expect(amountCond?.operator).toBe('>');
        expect(amountCond?.value).toBe(100);
    });
});
