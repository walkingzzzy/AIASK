/**
 * 行业映射配置测试
 */

import { describe, it, expect } from 'vitest';
import {
    getIndustry,
    getAllSectors,
    getSubsectors,
    addIndustryMapping,
    INDUSTRY_MAPPING,
    SECTOR_HIERARCHY
} from '../../src/config/industry-mapping.js';

describe('Industry Mapping Configuration', () => {
    describe('getIndustry', () => {
        it('should return correct industry for mapped stocks', () => {
            expect(getIndustry('601398')).toBe('金融'); // 工商银行
            expect(getIndustry('600519')).toBe('消费'); // 贵州茅台
            expect(getIndustry('600276')).toBe('医药'); // 恒瑞医药
            expect(getIndustry('002415')).toBe('科技'); // 海康威视
            expect(getIndustry('300750')).toBe('新能源'); // 宁德时代
        });

        it('should infer industry from stock code prefix', () => {
            expect(getIndustry('688001')).toBe('科技'); // 科创板
            expect(getIndustry('300001')).toBe('科技'); // 创业板
            expect(getIndustry('601001')).toBe('金融'); // 上交所主板
            expect(getIndustry('000001')).toBe('消费'); // 深交所主板
            expect(getIndustry('002001')).toBe('制造'); // 中小板
        });

        it('should return "其他" for unknown codes', () => {
            expect(getIndustry('999999')).toBe('其他');
        });
    });

    describe('getAllSectors', () => {
        it('should return all sector names', () => {
            const sectors = getAllSectors();
            expect(sectors).toContain('金融');
            expect(sectors).toContain('消费');
            expect(sectors).toContain('医药');
            expect(sectors).toContain('科技');
            expect(sectors).toContain('新能源');
            expect(sectors.length).toBeGreaterThan(5);
        });
    });

    describe('getSubsectors', () => {
        it('should return subsectors for valid sector', () => {
            const financialSubs = getSubsectors('金融');
            expect(financialSubs).toContain('银行');
            expect(financialSubs).toContain('证券');
            expect(financialSubs).toContain('保险');
        });

        it('should return empty array for invalid sector', () => {
            expect(getSubsectors('不存在的行业')).toEqual([]);
        });
    });

    describe('addIndustryMapping', () => {
        it('should add new industry mapping', () => {
            addIndustryMapping('999888', '测试行业');
            expect(getIndustry('999888')).toBe('测试行业');
        });

        it('should override existing mapping', () => {
            addIndustryMapping('601398', '测试覆盖');
            expect(getIndustry('601398')).toBe('测试覆盖');
            // 恢复原值
            addIndustryMapping('601398', '金融');
        });
    });

    describe('SECTOR_HIERARCHY', () => {
        it('should have valid structure', () => {
            expect(SECTOR_HIERARCHY['金融']).toBeDefined();
            expect(SECTOR_HIERARCHY['金融'].name).toBe('金融');
            expect(Array.isArray(SECTOR_HIERARCHY['金融'].subsectors)).toBe(true);
        });

        it('should have all major sectors', () => {
            const sectors = Object.keys(SECTOR_HIERARCHY);
            expect(sectors).toContain('金融');
            expect(sectors).toContain('消费');
            expect(sectors).toContain('医药');
            expect(sectors).toContain('科技');
            expect(sectors).toContain('新能源');
        });
    });
});
