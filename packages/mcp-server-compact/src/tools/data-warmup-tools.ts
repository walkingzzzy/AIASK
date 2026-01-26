/**
 * 数据预热工具
 */

import { z } from 'zod';
import { ToolRegistryItem } from '../types/tools.js';
import { handleDataWarmup } from './handlers/data-warmup.js';

const dataWarmupSchema = z.object({
    action: z.enum(['warmup', 'warmup_core', 'incremental_update', 'update', 'start_scheduler', 'schedule'])
        .default('warmup')
        .describe('操作类型：warmup=预热核心股票, incremental_update=增量更新, start_scheduler=启动定时任务'),
    stocks: z.array(z.string())
        .optional()
        .describe('股票代码列表（可选，默认使用核心股票池）'),
    lookbackDays: z.number()
        .default(250)
        .describe('回溯天数（默认250天）'),
    forceUpdate: z.boolean()
        .default(false)
        .describe('是否强制更新（默认false，仅更新过期数据）'),
    includeFinancials: z.boolean()
        .default(true)
        .describe('是否包含财务数据（默认true）'),
    hoursOld: z.number()
        .default(24)
        .describe('增量更新：查找多少小时前的数据（默认24小时）'),
    intervalHours: z.number()
        .default(24)
        .describe('定时任务：执行间隔（小时，默认24小时）'),
});

export const dataWarmupTools: ToolRegistryItem[] = [
    {
        definition: {
            name: 'data_warmup',
            description: '数据预热：主动预加载核心股票数据到本地数据库，提升查询性能。支持全量预热、增量更新、定时任务等功能。',
            category: 'data_management',
            inputSchema: dataWarmupSchema,
            tags: ['data', 'performance'],
            priority: 5,
            dataSource: 'real',
        },
        handler: handleDataWarmup,
    },
];
