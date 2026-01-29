#!/usr/bin/env node
/**
 * 同步缺失数据脚本
 * 用于补充数据库中缺失的财务数据和行情数据
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { AdapterManager } from '../src/adapters/index.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';

interface SyncProgress {
    total: number;
    processed: number;
    success: number;
    failed: string[];
    startTime: number;
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 同步财务数据 - 使用 akshare-mcp
 */
async function syncFinancials(stockCodes: string[], progress: SyncProgress): Promise<void> {
    const batchSize = 3;
    const delayBetweenBatches = 2000;
    const delayBetweenStocks = 1500;

    console.log(`\n💰 开始同步财务数据 (${stockCodes.length} 只股票)...`);
    console.log(`   使用 akshare-mcp 获取数据`);
    console.log(`   批次大小: ${batchSize}, 批次间延迟: ${delayBetweenBatches}ms\n`);

    for (let i = 0; i < stockCodes.length; i += batchSize) {
        const batch = stockCodes.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stockCodes.length / batchSize);

        console.log(`处理批次 ${batchNum}/${totalBatches}`);

        for (const code of batch) {
            try {
                // 使用 akshare-mcp 获取财务数据
                const res = await callAkshareMcpTool<any>('get_financials', { stock_code: code });

                if (res.success && res.data) {
                    const data = res.data;
                    await timescaleDB.upsertFinancials({
                        code: data.code || code,
                        report_date: data.reportDate || data.report_date || new Date().toISOString().split('T')[0],
                        revenue: data.revenue ?? null,
                        net_profit: data.netProfit ?? null,
                        gross_margin: data.grossProfitMargin ?? null,
                        net_margin: data.netProfitMargin ?? null,
                        debt_ratio: data.debtRatio ?? null,
                        current_ratio: data.currentRatio ?? null,
                        eps: data.eps ?? null,
                        roe: data.roe ?? null,
                        bvps: data.bvps ?? null,
                        roa: data.roa ?? null,
                        revenue_growth: data.revenueGrowth ?? null,
                        profit_growth: data.netProfitGrowth ?? data.profitGrowth ?? null,
                    });
                    progress.success++;
                    console.log(`  ✅ ${code}: 财务数据已保存 (${data.reportDate || 'N/A'})`);
                } else {
                    progress.failed.push(code);
                    console.log(`  ⚠️  ${code}: ${res.error || '无数据'}`);
                }
            } catch (error: any) {
                progress.failed.push(code);
                console.log(`  ❌ ${code}: ${error.message || error}`);
            }

            progress.processed++;
            await sleep(delayBetweenStocks);
        }

        // 显示进度
        const percent = ((progress.processed / progress.total) * 100).toFixed(1);
        const elapsed = ((Date.now() - progress.startTime) / 1000).toFixed(0);
        console.log(`进度: ${progress.processed}/${progress.total} (${percent}%), 成功: ${progress.success}, 耗时: ${elapsed}s\n`);

        if (i + batchSize < stockCodes.length) {
            await sleep(delayBetweenBatches);
        }
    }
}

/**
 * 同步实时行情数据
 */
async function syncQuotes(stockCodes: string[], progress: SyncProgress): Promise<void> {
    const adapterManager = new AdapterManager();
    const batchSize = 50; // 行情可以批量获取
    const delayBetweenBatches = 2000;

    console.log(`\n📊 开始同步实时行情数据 (${stockCodes.length} 只股票)...`);
    console.log(`   批次大小: ${batchSize}, 批次间延迟: ${delayBetweenBatches}ms\n`);

    // 确保唯一索引存在
    try {
        await timescaleDB.query(`
            CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_quotes_time_code 
            ON stock_quotes (time, code);
        `);
        console.log('✅ 确认 stock_quotes 唯一索引存在\n');
    } catch (e) {
        console.log('⚠️  唯一索引可能已存在\n');
    }

    for (let i = 0; i < stockCodes.length; i += batchSize) {
        const batch = stockCodes.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stockCodes.length / batchSize);

        console.log(`处理批次 ${batchNum}/${totalBatches} (${batch.length} 只股票)`);

        try {
            const res = await adapterManager.getBatchQuotes(batch);

            if (res.success && res.data && res.data.length > 0) {
                let batchSuccess = 0;
                let batchFailed = 0;
                const now = new Date();
                
                // 批量写入行情数据
                for (const quote of res.data) {
                    try {
                        await timescaleDB.query(`
                            INSERT INTO stock_quotes (time, code, name, price, change_pct, change_amt, open, high, low, prev_close, volume, amount, pe, pb, mkt_cap)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                            ON CONFLICT (time, code) DO UPDATE SET
                                price = EXCLUDED.price,
                                change_pct = EXCLUDED.change_pct,
                                volume = EXCLUDED.volume,
                                amount = EXCLUDED.amount,
                                updated_at = NOW()
                        `, [
                            now,
                            quote.code,
                            quote.name || '',
                            quote.price,
                            quote.changePercent,
                            quote.change,
                            quote.open,
                            quote.high,
                            quote.low,
                            quote.preClose,
                            quote.volume,
                            quote.amount,
                            (quote as any).pe || null,
                            (quote as any).pb || null,
                            (quote as any).marketCap || null
                        ]);
                        progress.success++;
                        batchSuccess++;
                    } catch (e: any) {
                        progress.failed.push(quote.code);
                        batchFailed++;
                        if (batchFailed <= 3) {
                            console.log(`    ❌ ${quote.code}: ${e.message}`);
                        }
                    }
                }
                console.log(`  ✅ 批次完成: 成功 ${batchSuccess}, 失败 ${batchFailed}`);
            } else {
                batch.forEach(code => progress.failed.push(code));
                console.log(`  ⚠️  批次失败: ${res.error || '无数据'}`);
            }
        } catch (error: any) {
            batch.forEach(code => progress.failed.push(code));
            console.log(`  ❌ 批次异常: ${error.message || error}`);
        }

        progress.processed += batch.length;

        // 显示进度
        const percent = ((progress.processed / progress.total) * 100).toFixed(1);
        const elapsed = ((Date.now() - progress.startTime) / 1000).toFixed(0);
        console.log(`进度: ${progress.processed}/${progress.total} (${percent}%), 成功: ${progress.success}, 耗时: ${elapsed}s\n`);

        if (i + batchSize < stockCodes.length) {
            await sleep(delayBetweenBatches);
        }
    }
}

/**
 * 主函数
 */
async function main() {
    console.log('='.repeat(70));
    console.log('缺失数据同步脚本');
    console.log('='.repeat(70));

    const args = process.argv.slice(2);
    const syncType = args[0] || 'all'; // 'financials', 'quotes', 'all'
    const limit = parseInt(args[1] || '100', 10); // 限制同步数量

    try {
        // 初始化数据库
        await timescaleDB.initialize();
        console.log('✅ 数据库已连接\n');

        // 获取所有股票代码
        const stocksResult = await timescaleDB.query('SELECT stock_code FROM stocks ORDER BY stock_code LIMIT $1', [limit]);
        const stockCodes = stocksResult.rows.map((r: any) => r.stock_code);
        console.log(`📋 获取到 ${stockCodes.length} 只股票\n`);

        if (syncType === 'financials' || syncType === 'all') {
            // 检查哪些股票缺少财务数据
            const financialsResult = await timescaleDB.query('SELECT DISTINCT code FROM financials');
            const existingFinancials = new Set(financialsResult.rows.map((r: any) => r.code));
            const missingFinancials = stockCodes.filter((code: string) => !existingFinancials.has(code));

            console.log(`💰 财务数据: 已有 ${existingFinancials.size} 只, 缺失 ${missingFinancials.length} 只`);

            if (missingFinancials.length > 0) {
                const progress: SyncProgress = {
                    total: missingFinancials.length,
                    processed: 0,
                    success: 0,
                    failed: [],
                    startTime: Date.now()
                };
                await syncFinancials(missingFinancials.slice(0, limit), progress);
                console.log(`\n财务数据同步完成: 成功 ${progress.success}, 失败 ${progress.failed.length}`);
            }
        }

        if (syncType === 'quotes' || syncType === 'all') {
            // 检查哪些股票缺少行情数据
            const quotesResult = await timescaleDB.query('SELECT DISTINCT code FROM stock_quotes');
            const existingQuotes = new Set(quotesResult.rows.map((r: any) => r.code));
            const missingQuotes = stockCodes.filter((code: string) => !existingQuotes.has(code));

            console.log(`\n📊 行情数据: 已有 ${existingQuotes.size} 只, 缺失 ${missingQuotes.length} 只`);

            if (missingQuotes.length > 0) {
                const progress: SyncProgress = {
                    total: missingQuotes.length,
                    processed: 0,
                    success: 0,
                    failed: [],
                    startTime: Date.now()
                };
                await syncQuotes(missingQuotes.slice(0, limit), progress);
                console.log(`\n行情数据同步完成: 成功 ${progress.success}, 失败 ${progress.failed.length}`);
            }
        }

        // 最终统计
        console.log('\n' + '='.repeat(70));
        console.log('同步完成！');
        
        const finalStats = await timescaleDB.query(`
            SELECT 
                (SELECT COUNT(*) FROM stocks) as stocks,
                (SELECT COUNT(*) FROM financials) as financials,
                (SELECT COUNT(DISTINCT code) FROM financials) as financials_stocks,
                (SELECT COUNT(*) FROM stock_quotes) as quotes,
                (SELECT COUNT(DISTINCT code) FROM stock_quotes) as quotes_stocks
        `);
        const stats = finalStats.rows[0];
        console.log(`\n当前数据库状态:`);
        console.log(`  股票总数: ${stats.stocks}`);
        console.log(`  财务数据: ${stats.financials} 条 (覆盖 ${stats.financials_stocks} 只股票)`);
        console.log(`  行情数据: ${stats.quotes} 条 (覆盖 ${stats.quotes_stocks} 只股票)`);
        console.log('='.repeat(70));

    } catch (error) {
        console.error('❌ 同步失败:', error);
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
