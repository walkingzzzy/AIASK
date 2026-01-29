#!/usr/bin/env node
/**
 * 数据源和数据库审查脚本
 * 任务1: 测试 AKShare MCP 各数据源的可用性
 * 任务2: 审查数据库中的实际数据情况
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';
import { AdapterManager } from '../src/adapters/index.js';

interface TestResult {
    tool: string;
    success: boolean;
    error?: string;
    dataCount?: number;
    sampleData?: any;
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 任务1: 测试 AKShare MCP 数据源
 */
async function auditAkshareMcp(): Promise<void> {
    console.log('='.repeat(80));
    console.log('任务1: AKShare MCP 数据源可用性测试');
    console.log('='.repeat(80));
    console.log();

    const tests: TestResult[] = [];

    // 测试用的股票代码
    const testCode = '600000'; // 浦发银行
    const testDate = '2024-12-20'; // 使用一个确定有数据的历史日期

    // 1. 测试股票列表
    console.log('📋 测试1: 获取股票列表 (get_stock_list)...');
    try {
        const res = await callAkshareMcpTool<any>('get_stock_list', {});
        if (res.success && res.data && Array.isArray(res.data)) {
            tests.push({
                tool: 'get_stock_list',
                success: true,
                dataCount: res.data.length,
                sampleData: res.data.slice(0, 2)
            });
            console.log(`  ✅ 成功 - 获取到 ${res.data.length} 只股票`);
            console.log(`  样本: ${JSON.stringify(res.data.slice(0, 2), null, 2)}`);
        } else {
            tests.push({ tool: 'get_stock_list', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_stock_list', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }
    await sleep(1000);

    // 2. 测试K线数据
    console.log('\n📈 测试2: 获取K线数据 (get_kline)...');
    try {
        const res = await callAkshareMcpTool<any>('get_kline', {
            stock_code: testCode,
            period: 'daily',
            start_date: '2024-12-01',
            end_date: '2024-12-31'
        });
        if (res.success && res.data && Array.isArray(res.data)) {
            tests.push({
                tool: 'get_kline',
                success: true,
                dataCount: res.data.length,
                sampleData: res.data[0]
            });
            console.log(`  ✅ 成功 - 获取到 ${res.data.length} 条K线`);
            console.log(`  样本: ${JSON.stringify(res.data[0], null, 2)}`);
        } else {
            tests.push({ tool: 'get_kline', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_kline', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }
    await sleep(1000);

    // 3. 测试实时行情
    console.log('\n💹 测试3: 获取实时行情 (get_batch_quotes)...');
    try {
        const res = await callAkshareMcpTool<any>('get_batch_quotes', {
            stock_codes: [testCode, '600036']
        });
        if (res.success && res.data) {
            tests.push({
                tool: 'get_batch_quotes',
                success: true,
                dataCount: Array.isArray(res.data) ? res.data.length : 1,
                sampleData: Array.isArray(res.data) ? res.data[0] : res.data
            });
            console.log(`  ✅ 成功`);
            console.log(`  样本: ${JSON.stringify(Array.isArray(res.data) ? res.data[0] : res.data, null, 2)}`);
        } else {
            tests.push({ tool: 'get_batch_quotes', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_batch_quotes', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }
    await sleep(1000);

    // 4. 测试财务数据
    console.log('\n💰 测试4: 获取财务数据 (get_financials)...');
    try {
        const res = await callAkshareMcpTool<any>('get_financials', {
            stock_code: testCode
        });
        if (res.success && res.data) {
            tests.push({
                tool: 'get_financials',
                success: true,
                sampleData: res.data
            });
            console.log(`  ✅ 成功`);
            console.log(`  样本: ${JSON.stringify(res.data, null, 2)}`);
        } else {
            tests.push({ tool: 'get_financials', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_financials', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }
    await sleep(1000);

    // 5. 测试龙虎榜
    console.log('\n🐉 测试5: 获取龙虎榜 (get_dragon_tiger)...');
    try {
        const res = await callAkshareMcpTool<any>('get_dragon_tiger', {
            date: testDate
        });
        if (res.success && res.data && Array.isArray(res.data)) {
            tests.push({
                tool: 'get_dragon_tiger',
                success: true,
                dataCount: res.data.length,
                sampleData: res.data[0]
            });
            console.log(`  ✅ 成功 - 获取到 ${res.data.length} 条记录`);
            console.log(`  样本: ${JSON.stringify(res.data[0], null, 2)}`);
        } else {
            tests.push({ tool: 'get_dragon_tiger', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_dragon_tiger', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }
    await sleep(1000);

    // 6. 测试北向资金
    console.log('\n🌏 测试6: 获取北向资金 (get_north_fund)...');
    try {
        const res = await callAkshareMcpTool<any>('get_north_fund', {
            days: 30
        });
        const items = Array.isArray(res.data) ? res.data : res.data?.items;
        if (res.success && items && Array.isArray(items)) {
            tests.push({
                tool: 'get_north_fund',
                success: true,
                dataCount: items.length,
                sampleData: items[0]
            });
            console.log(`  ✅ 成功 - 获取到 ${items.length} 条记录`);
            console.log(`  样本: ${JSON.stringify(items[0], null, 2)}`);
        } else {
            tests.push({ tool: 'get_north_fund', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_north_fund', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }
    await sleep(1000);

    // 7. 测试融资融券
    console.log('\n💳 测试7: 获取融资融券 (get_margin_data)...');
    try {
        const res = await callAkshareMcpTool<any>('get_margin_data', {
            date: testDate
        });
        if (res.success && res.data && Array.isArray(res.data)) {
            tests.push({
                tool: 'get_margin_data',
                success: true,
                dataCount: res.data.length,
                sampleData: res.data[0]
            });
            console.log(`  ✅ 成功 - 获取到 ${res.data.length} 条记录`);
            console.log(`  样本: ${JSON.stringify(res.data[0], null, 2)}`);
        } else {
            tests.push({ tool: 'get_margin_data', success: false, error: res.error || '无数据' });
            console.log(`  ❌ 失败 - ${res.error || '无数据'}`);
        }
    } catch (e: any) {
        tests.push({ tool: 'get_margin_data', success: false, error: e.message });
        console.log(`  ❌ 异常 - ${e.message}`);
    }

    // 汇总
    console.log('\n' + '='.repeat(80));
    console.log('AKShare MCP 测试汇总:');
    console.log('='.repeat(80));
    const successCount = tests.filter(t => t.success).length;
    const failCount = tests.filter(t => !t.success).length;
    console.log(`✅ 成功: ${successCount} 个`);
    console.log(`❌ 失败: ${failCount} 个`);
    console.log();
    
    if (failCount > 0) {
        console.log('失败的工具:');
        tests.filter(t => !t.success).forEach(t => {
            console.log(`  - ${t.tool}: ${t.error}`);
        });
    }
    console.log();
}

/**
 * 任务2: 审查数据库数据
 */
async function auditDatabase(): Promise<void> {
    console.log('='.repeat(80));
    console.log('任务2: 数据库实际数据审查');
    console.log('='.repeat(80));
    console.log();

    // 1. 股票基础数据
    console.log('📊 1. 股票基础数据 (stocks)');
    const stocksStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT market) as markets,
            COUNT(DISTINCT sector) as sectors,
            COUNT(DISTINCT industry) as industries
        FROM stocks
    `);
    console.log(`  总数: ${stocksStats.rows[0].total}`);
    console.log(`  市场: ${stocksStats.rows[0].markets} 个`);
    console.log(`  板块: ${stocksStats.rows[0].sectors} 个`);
    console.log(`  行业: ${stocksStats.rows[0].industries} 个`);

    const stocksSample = await timescaleDB.query('SELECT * FROM stocks LIMIT 3');
    console.log(`  样本数据:`);
    stocksSample.rows.forEach((row: any) => {
        console.log(`    ${row.stock_code} ${row.stock_name} [${row.market}] ${row.sector || 'N/A'}`);
    });
    console.log();

    // 2. K线数据
    console.log('📈 2. K线数据 (kline_1d)');
    const klineStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT code) as stocks,
            MIN(time) as earliest,
            MAX(time) as latest
        FROM kline_1d
    `);
    console.log(`  总记录: ${klineStats.rows[0].total}`);
    console.log(`  覆盖股票: ${klineStats.rows[0].stocks} 只`);
    console.log(`  时间范围: ${klineStats.rows[0].earliest?.toISOString().split('T')[0]} 至 ${klineStats.rows[0].latest?.toISOString().split('T')[0]}`);

    const klineSample = await timescaleDB.query('SELECT * FROM kline_1d ORDER BY time DESC LIMIT 3');
    console.log(`  最新数据样本:`);
    klineSample.rows.forEach((row: any) => {
        console.log(`    ${row.time.toISOString().split('T')[0]} ${row.code}: 开${row.open} 高${row.high} 低${row.low} 收${row.close} 量${row.volume}`);
    });
    console.log();

    // 3. 财务数据
    console.log('💰 3. 财务数据 (financials)');
    const financialsStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT code) as stocks,
            MIN(report_date) as earliest,
            MAX(report_date) as latest
        FROM financials
    `);
    console.log(`  总记录: ${financialsStats.rows[0].total}`);
    console.log(`  覆盖股票: ${financialsStats.rows[0].stocks} 只`);
    console.log(`  报告期范围: ${financialsStats.rows[0].earliest} 至 ${financialsStats.rows[0].latest}`);

    const financialsSample = await timescaleDB.query('SELECT * FROM financials ORDER BY report_date DESC LIMIT 3');
    console.log(`  最新数据样本:`);
    financialsSample.rows.forEach((row: any) => {
        console.log(`    ${row.code} ${row.report_date}: 营收${row.revenue} 净利${row.net_profit} ROE${row.roe}%`);
    });
    console.log();

    // 4. 实时行情
    console.log('💹 4. 实时行情 (stock_quotes)');
    const quotesStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT code) as stocks,
            MIN(time) as earliest,
            MAX(time) as latest
        FROM stock_quotes
    `);
    console.log(`  总记录: ${quotesStats.rows[0].total}`);
    console.log(`  覆盖股票: ${quotesStats.rows[0].stocks} 只`);
    console.log(`  时间范围: ${quotesStats.rows[0].earliest?.toISOString().split('T')[0]} 至 ${quotesStats.rows[0].latest?.toISOString().split('T')[0]}`);

    const quotesSample = await timescaleDB.query('SELECT * FROM stock_quotes ORDER BY time DESC LIMIT 3');
    console.log(`  最新数据样本:`);
    quotesSample.rows.forEach((row: any) => {
        console.log(`    ${row.code} ${row.name}: 价格${row.price} 涨跌${row.change_pct}% PE${row.pe} PB${row.pb}`);
    });
    console.log();

    // 5. 龙虎榜
    console.log('🐉 5. 龙虎榜数据 (dragon_tiger)');
    const dragonStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT code) as stocks,
            MIN(date) as earliest,
            MAX(date) as latest
        FROM dragon_tiger
    `);
    console.log(`  总记录: ${dragonStats.rows[0].total}`);
    console.log(`  涉及股票: ${dragonStats.rows[0].stocks} 只`);
    console.log(`  日期范围: ${dragonStats.rows[0].earliest} 至 ${dragonStats.rows[0].latest}`);
    console.log();

    // 6. 北向资金
    console.log('🌏 6. 北向资金 (north_fund)');
    const northStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            MIN(date) as earliest,
            MAX(date) as latest,
            SUM(total) as total_net
        FROM north_fund
    `);
    console.log(`  总记录: ${northStats.rows[0].total}`);
    console.log(`  日期范围: ${northStats.rows[0].earliest} 至 ${northStats.rows[0].latest}`);
    console.log(`  累计净流入: ${northStats.rows[0].total_net ? (northStats.rows[0].total_net / 100000000).toFixed(2) + ' 亿元' : 'N/A'}`);
    console.log();

    // 7. 融资融券
    console.log('💳 7. 融资融券 (margin_data)');
    const marginStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT code) as stocks,
            MIN(date) as earliest,
            MAX(date) as latest
        FROM margin_data
    `);
    console.log(`  总记录: ${marginStats.rows[0].total}`);
    console.log(`  涉及股票: ${marginStats.rows[0].stocks} 只`);
    console.log(`  日期范围: ${marginStats.rows[0].earliest} 至 ${marginStats.rows[0].latest}`);
    console.log();

    // 8. 大宗交易
    console.log('📦 8. 大宗交易 (block_trades)');
    const blockStats = await timescaleDB.query(`
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT code) as stocks,
            MIN(date) as earliest,
            MAX(date) as latest
        FROM block_trades
    `);
    console.log(`  总记录: ${blockStats.rows[0].total}`);
    console.log(`  涉及股票: ${blockStats.rows[0].stocks} 只`);
    console.log(`  日期范围: ${blockStats.rows[0].earliest || 'N/A'} 至 ${blockStats.rows[0].latest || 'N/A'}`);
    console.log();

    // 汇总
    console.log('='.repeat(80));
    console.log('数据库审查汇总:');
    console.log('='.repeat(80));
    console.log(`✅ 股票基础数据: ${stocksStats.rows[0].total} 只`);
    console.log(`✅ K线数据: ${klineStats.rows[0].total} 条 (${klineStats.rows[0].stocks} 只股票)`);
    console.log(`✅ 财务数据: ${financialsStats.rows[0].total} 条 (${financialsStats.rows[0].stocks} 只股票)`);
    console.log(`✅ 实时行情: ${quotesStats.rows[0].total} 条 (${quotesStats.rows[0].stocks} 只股票)`);
    console.log(`✅ 龙虎榜: ${dragonStats.rows[0].total} 条`);
    console.log(`✅ 北向资金: ${northStats.rows[0].total} 条`);
    console.log(`✅ 融资融券: ${marginStats.rows[0].total} 条`);
    console.log(`✅ 大宗交易: ${blockStats.rows[0].total} 条`);
    console.log('='.repeat(80));
}

/**
 * 主函数
 */
async function main() {
    console.log('\n');
    console.log('█'.repeat(80));
    console.log('█' + ' '.repeat(78) + '█');
    console.log('█' + ' '.repeat(20) + '数据源和数据库综合审查报告' + ' '.repeat(20) + '█');
    console.log('█' + ' '.repeat(78) + '█');
    console.log('█'.repeat(80));
    console.log('\n');

    try {
        // 初始化数据库
        await timescaleDB.initialize();

        // 任务1: 测试 AKShare MCP
        await auditAkshareMcp();

        // 任务2: 审查数据库
        await auditDatabase();

        console.log('\n✅ 审查完成！\n');

    } catch (error) {
        console.error('❌ 审查失败:', error);
        process.exit(1);
    } finally {
        await timescaleDB.close();
        process.exit(0);
    }
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
