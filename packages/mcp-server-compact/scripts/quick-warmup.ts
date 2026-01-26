#!/usr/bin/env node
/**
 * 快速预热脚本
 * 仅预热少量核心股票，用于快速测试
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { warmupCoreStocks } from '../src/services/data-warmup.js';

async function quickWarmup() {
    console.log('🚀 快速预热模式（仅预热 3 只股票）');
    console.log();

    try {
        // 初始化数据库
        await timescaleDB.initialize();
        console.log('✅ 数据库已初始化');
        console.log();

        // 仅预热 3 只核心股票
        const result = await warmupCoreStocks({
            stocks: ['000001', '600000', '600519'], // 平安银行、浦发银行、贵州茅台
            lookbackDays: 60, // 仅 60 天数据
            forceUpdate: true,
            includeFinancials: false, // 不包含财务数据
        });

        console.log();
        console.log('预热完成:');
        console.log(`  ✅ 成功: ${result.stocksProcessed} 只`);
        console.log(`  📈 K线: ${result.klineRecords} 条`);
        console.log(`  ⏱️  耗时: ${(result.duration / 1000).toFixed(2)} 秒`);
        console.log();

        if (result.success) {
            console.log('✨ 快速预热成功！可以开始测试了。');
        } else {
            console.log('⚠️  部分失败，但可以继续测试。');
        }

    } catch (error) {
        console.error('❌ 快速预热失败:', error);
        process.exit(1);
    } finally {
        await timescaleDB.close();
    }
}

quickWarmup().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
