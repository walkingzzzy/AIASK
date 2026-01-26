/**
 * 数据源验证脚本 v2
 * 验证所有真实数据源是否可用
 * 区分网络数据源和本地数据源
 */

import { adapterManager } from '../adapters/index.js';
import { getDailyBars } from '../storage/kline-data.js';
import * as FactorCalc from '../services/factor-calculator.js';
import { timescaleDB } from '../storage/timescaledb.js';

interface ValidationResult {
    category: 'network' | 'local';
    source: string;
    test: string;
    success: boolean;
    dataAvailable: boolean;
    data?: any;
    error?: string;
    latency?: number;
}

const results: ValidationResult[] = [];

async function validateSource(
    category: 'network' | 'local',
    source: string,
    test: string,
    fn: () => Promise<any> | any
): Promise<ValidationResult> {
    const start = Date.now();
    try {
        const data = await fn();
        const latency = Date.now() - start;

        // 判断数据是否真正可用（不仅仅是调用成功）
        let dataAvailable = true;
        if (typeof data === 'object' && data !== null) {
            if (data.success === false) {
                dataAvailable = false;
            } else if (data.count !== undefined && data.count === 0) {
                dataAvailable = false;
            }
        }

        const result: ValidationResult = {
            category,
            source,
            test,
            success: true,
            dataAvailable,
            latency,
            data: typeof data === 'object' ? data : { value: data }
        };
        results.push(result);
        return result;
    } catch (err: any) {
        const latency = Date.now() - start;
        const result: ValidationResult = {
            category,
            source,
            test,
            success: false,
            dataAvailable: false,
            latency,
            error: err.message || String(err)
        };
        results.push(result);
        return result;
    }
}

async function main() {
    console.log('='.repeat(70));
    console.log('📊 数据源验证脚本 v2 (PostgreSQL版)');
    console.log('='.repeat(70));
    console.log(`开始时间: ${new Date().toISOString()}\n`);

    // 初始化数据库
    try {
        await timescaleDB.initialize();
        console.log('✅ 数据库连接成功');
    } catch (e) {
        console.log('❌ 数据库连接失败:', e);
        process.exit(1);
    }

    // =============== 本地数据源 ===============
    console.log('🏠 【本地数据源验证】\n');

    // K线缓存
    await validateSource('local', 'KlineStorage', '平安银行K线缓存(60天)', async () => {
        const bars = await getDailyBars('000001', 60);
        return { success: bars.length > 0, count: bars.length, sample: bars.slice(-3) };
    });

    await validateSource('local', 'KlineStorage', '招商银行K线缓存(30天)', async () => {
        const bars = await getDailyBars('600036', 30);
        return { success: bars.length > 0, count: bars.length };
    });

    // 因子计算（依赖本地数据）
    await validateSource('local', 'FactorCalculator', 'EP因子计算', async () => {
        return await FactorCalc.calculateEP('000001');
    });

    await validateSource('local', 'FactorCalculator', 'BP因子计算', async () => {
        return await FactorCalc.calculateBP('000001');
    });

    await validateSource('local', 'FactorCalculator', '动量因子计算(6个月)', async () => {
        return await FactorCalc.calculateMomentum('000001', 6);
    });

    await validateSource('local', 'FactorCalculator', 'ROE因子计算', async () => {
        return await FactorCalc.calculateROE('000001');
    });

    await validateSource('local', 'FactorCalculator', '毛利率因子计算', async () => {
        return await FactorCalc.calculateGrossMargin('000001');
    });

    // PostgreSQL存储
    await validateSource('local', 'TimescaleDB', '持仓列表', async () => {
        const positions = await timescaleDB.getPositions();
        return { success: true, count: positions.length, positions: positions.slice(0, 3) };
    });

    await validateSource('local', 'TimescaleDB', '每日盈亏记录', async () => {
        const pnl = await timescaleDB.getDailyPnL(30);
        return { success: true, count: pnl.length };
    });

    // =============== 网络数据源 ===============
    console.log('\n🌐 【网络数据源验证】\n');

    await validateSource('network', 'AdapterManager', '平安银行实时行情', async () => {
        return await adapterManager.getRealtimeQuote('000001');
    });

    await validateSource('network', 'AdapterManager', '批量行情(3股)', async () => {
        return await adapterManager.getBatchQuotes(['000001', '600000', '000002']);
    });

    await validateSource('network', 'AdapterManager', '日K线数据(30天)', async () => {
        return await adapterManager.getKline('000001', '101', 30);
    });

    await validateSource('network', 'AdapterManager', '个股资金流向', async () => {
        return await adapterManager.getFundFlow('000001');
    });

    await validateSource('network', 'AdapterManager', '沪深300指数K线', async () => {
        // Index code normalization might vary
        return await adapterManager.getKline('000300', '101', 20);
    });

    // =============== 结果汇总 ===============
    console.log('\n' + '='.repeat(70));
    console.log('📋 验证结果汇总');
    console.log('='.repeat(70));

    const localResults = results.filter((r: any) => r.category === 'local');
    const networkResults = results.filter((r: any) => r.category === 'network');

    const localAvailable = localResults.filter((r: any) => r.dataAvailable);
    const networkAvailable = networkResults.filter((r: any) => r.dataAvailable);

    console.log('\n🏠 本地数据源:');
    console.log(`   ✅ 可用: ${localAvailable.length}/${localResults.length}`);
    for (const r of localResults) {
        const status = r.dataAvailable ? '✅' : '❌';
        const latency = r.latency ? `(${r.latency}ms)` : '';
        console.log(`   ${status} [${r.source}] ${r.test} ${latency}`);
        if (r.dataAvailable && r.data) {
            if (r.data.count !== undefined) {
                console.log(`      → 数据量: ${r.data.count} 条`);
            }
            if (r.data.data?.value !== undefined) {
                console.log(`      → 值: ${r.data.data.value}`);
            }
        }
    }

    console.log('\n🌐 网络数据源:');
    console.log(`   ✅ 可用: ${networkAvailable.length}/${networkResults.length}`);
    for (const r of networkResults) {
        const status = r.dataAvailable ? '✅' : '⚠️';
        const latency = r.latency ? `(${r.latency}ms)` : '';
        console.log(`   ${status} [${r.source}] ${r.test} ${latency}`);
        if (!r.dataAvailable && r.data?.error) {
            const errMsg = r.data.error.slice(0, 60);
            console.log(`      → 错误: ${errMsg}...`);
        }
    }

    // 结论
    console.log('\n' + '='.repeat(70));
    console.log('📊 结论:');
    console.log('='.repeat(70));

    if (localAvailable.length === localResults.length) {
        console.log('✅ 本地数据源: 全部可用');
        console.log('   - K线缓存数据完整');
        console.log('   - 因子计算功能正常');
        console.log('   - TimescaleDB存储可用');
    } else {
        console.log(`⚠️ 本地数据源: ${localResults.length - localAvailable.length} 项不可用`);
    }

    if (networkAvailable.length === networkResults.length) {
        console.log('✅ 网络数据源: 全部可用');
    } else if (networkAvailable.length > 0) {
        console.log(`⚠️ 网络数据源: ${networkAvailable.length}/${networkResults.length} 可用`);
    } else {
        console.log('❌ 网络数据源: 全部不可用（网络问题或API限制）');
        console.log('   ⓘ 这不影响使用本地缓存的K线数据进行计算');
        console.log('   ⓘ VaR/相关性/因子等计算使用本地K线缓存');
    }

    console.log('\n💡 说明:');
    console.log('   - 已修改的工具优先使用本地K线缓存进行计算');
    console.log('   - 当网络可用时，会自动从API获取最新数据');
    console.log('   - 网络不可用时，回退到本地缓存数据');
    console.log('='.repeat(70));

    await timescaleDB.close();

    return {
        local: { available: localAvailable.length, total: localResults.length },
        network: { available: networkAvailable.length, total: networkResults.length }
    };
}

main().catch(console.error);
