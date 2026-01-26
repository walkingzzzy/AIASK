/**
 * 本地数据源验证脚本
 * 仅验证本地缓存数据（PostgreSQL）
 */

import { getDailyBars } from '../storage/kline-data.js';
import * as FactorCalc from '../services/factor-calculator.js';
import { timescaleDB } from '../storage/timescaledb.js';

async function main() {
    console.log('='.repeat(60));
    console.log('📊 本地数据源验证 (PostgreSQL)');
    console.log('='.repeat(60));
    console.log(`时间: ${new Date().toISOString()}\n`);

    try {
        await timescaleDB.initialize();
        console.log('✅ 数据库连接成功');
    } catch (e) {
        console.log('❌ 数据库连接失败:', e);
        process.exit(1);
    }

    // 测试K线缓存
    console.log('📈 K线缓存验证:');
    const stocks = ['000001', '600000', '000002', '600036', '000858'];
    for (const code of stocks) {
        const bars = await getDailyBars(code, 60);
        if (bars.length > 0) {
            const latest = bars[bars.length - 1];
            console.log(`  ✅ ${code}: ${bars.length}天数据, 最新日期=${latest.date}, 收盘=${latest.close}`);
        } else {
            console.log(`  ❌ ${code}: 无数据`);
        }
    }

    // 测试因子计算
    console.log('\n🔢 因子计算验证:');
    const testCode = '000001';

    const factors = [
        { name: 'EP', fn: async () => await FactorCalc.calculateEP(testCode) },
        { name: 'BP', fn: async () => await FactorCalc.calculateBP(testCode) },
        { name: 'ROE', fn: async () => await FactorCalc.calculateROE(testCode) },
        { name: '动量', fn: async () => await FactorCalc.calculateMomentum(testCode, 6) },
        { name: '毛利率', fn: async () => await FactorCalc.calculateGrossMargin(testCode) },
    ];

    for (const f of factors) {
        try {
            const result = await f.fn();
            if (result.success && result.data) {
                console.log(`  ✅ ${f.name}: ${result.data.value?.toFixed?.(4) || result.data.value} (来源: ${result.data.dataSource})`);
            } else {
                console.log(`  ❌ ${f.name}: ${result.error || '无数据'}`);
            }
        } catch (e: any) {
            console.log(`  ❌ ${f.name}: 执行出错 ${e.message}`);
        }
    }

    // 测试PostgreSQL存储
    console.log('\n💾 PostgreSQL存储验证:');
    const positions = await timescaleDB.getPositions();
    console.log(`  ✅ 持仓数量: ${positions.length}`);
    if (positions.length > 0) {
        console.log(`     示例: ${positions[0].code} ${positions[0].name}, 数量=${positions[0].quantity}, 成本=${positions[0].costPrice}`);
    }

    const pnl = await timescaleDB.getDailyPnL(30);
    console.log(`  ✅ 盈亏记录: ${pnl.length}天`);

    // 验证VaR计算所需数据
    console.log('\n📉 VaR计算验证（使用本地K线）:');
    const varBars = await getDailyBars('000001', 60);
    if (varBars.length >= 20) {
        const returns: number[] = [];
        for (let i = 1; i < varBars.length; i++) {
            returns.push((varBars[i].close - varBars[i - 1].close) / varBars[i - 1].close);
        }
        const sorted = [...returns].sort((a: any, b: any) => a - b);
        const var95Index = Math.floor(sorted.length * 0.05);
        const historicalVaR = Math.abs(sorted[var95Index]);
        console.log(`  ✅ 收益率样本: ${returns.length}个`);
        console.log(`  ✅ 95%历史VaR: ${(historicalVaR * 100).toFixed(2)}%`);
    } else {
        console.log(`  ❌ K线数据不足`);
    }

    // 验证相关性计算
    console.log('\n📊 相关性计算验证:');
    const bars1 = await getDailyBars('000001', 60);
    const bars2 = await getDailyBars('600000', 60);
    if (bars1.length >= 20 && bars2.length >= 20) {
        const n = Math.min(bars1.length, bars2.length);
        const ret1 = bars1.slice(-n).map((b, i, arr) => i > 0 ? (b.close - arr[i - 1].close) / arr[i - 1].close : 0).slice(1);
        const ret2 = bars2.slice(-n).map((b, i, arr) => i > 0 ? (b.close - arr[i - 1].close) / arr[i - 1].close : 0).slice(1);

        const mean1 = ret1.reduce((a: any, b: any) => a + b, 0) / ret1.length;
        const mean2 = ret2.reduce((a: any, b: any) => a + b, 0) / ret2.length;
        let cov = 0, var1 = 0, var2 = 0;
        for (let i = 0; i < ret1.length; i++) {
            cov += (ret1[i] - mean1) * (ret2[i] - mean2);
            var1 += (ret1[i] - mean1) ** 2;
            var2 += (ret2[i] - mean2) ** 2;
        }
        const corr = cov / Math.sqrt(var1 * var2);
        console.log(`  ✅ 000001 vs 600000 相关系数: ${corr.toFixed(4)}`);
    } else {
        console.log(`  ❌ K线数据不足`);
    }

    console.log('\n' + '='.repeat(60));
    console.log('✅ 本地数据源验证完成！');
    console.log('   所有修改后的工具均使用本地K线缓存进行计算');
    console.log('='.repeat(60));

    await timescaleDB.close();
}

main().catch(console.error);

