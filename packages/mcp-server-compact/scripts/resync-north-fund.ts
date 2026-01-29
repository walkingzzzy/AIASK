#!/usr/bin/env node
/**
 * 北向资金清理与重同步脚本
 * 统一存储单位为“元”，并写入 north_fund 表
 */

import { adapterManager, cache } from '../src/adapters/index.js';
import { timescaleDB } from '../src/storage/timescaledb.js';

async function main() {
    const args = process.argv.slice(2);
    const days = parseInt(args[0] || '365', 10);

    console.log('='.repeat(70));
    console.log('北向资金清理与重同步');
    console.log('='.repeat(70));
    console.log(`回溯天数: ${days}`);

    await timescaleDB.initialize();
    cache.clear();

    console.log('清空 north_fund 表...');
    await timescaleDB.query('TRUNCATE TABLE north_fund');

    console.log('获取北向资金数据...');
    const res = await adapterManager.getNorthFund(days);
    if (!res.success || !res.data || res.data.length === 0) {
        console.error(`❌ 获取失败: ${res.error || '无数据'}`);
        await timescaleDB.close();
        process.exit(1);
    }

    console.log(`写入 ${res.data.length} 条记录 (source=${res.source})...`);
    for (const item of res.data) {
        await timescaleDB.query(
            `INSERT INTO north_fund (date, hk_to_sh, hk_to_sz, total, hk_to_sh_balance, hk_to_sz_balance)
             VALUES ($1, $2, $3, $4, $5, $6)
             ON CONFLICT (date) DO UPDATE SET
             hk_to_sh = EXCLUDED.hk_to_sh,
             hk_to_sz = EXCLUDED.hk_to_sz,
             total = EXCLUDED.total,
             hk_to_sh_balance = EXCLUDED.hk_to_sh_balance,
             hk_to_sz_balance = EXCLUDED.hk_to_sz_balance`,
            [
                item.date,
                item.shConnect,
                item.szConnect,
                item.total,
                item.cumulative ?? null,
                item.cumulative ?? null,
            ]
        );
    }

    console.log('✅ 北向资金重同步完成');
    await timescaleDB.close();
    process.exit(0);
}

main().catch(error => {
    console.error('❌ 重同步失败:', error);
    process.exit(1);
});
