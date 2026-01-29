#!/usr/bin/env node
/**
 * 完整数据库初始化脚本 - 包含所有高级数据
 * 
 * 下载内容：
 * 1. 基础数据：股票列表、日线K线、财务数据（由 init-database.ts 完成）
 * 2. 分钟K线：1m, 5m, 15m, 30m, 60m（最近30天）
 * 3. 龙虎榜：最近90天
 * 4. 北向资金：最近365天
 * 5. 融资融券：最近90天
 * 6. 大宗交易：最近90天
 * 7. 新闻资讯：每只股票最近20条
 * 
 * 注意：
 * - 实时数据（行情、盘口、分时）不需要预下载，使用时实时获取
 * - 期权数据需要单独实现适配器
 * - 向量数据需要单独的生成流程
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { adapterManager } from '../src/adapters/index.js';

interface FullInitProgress {
    totalStocks: number;
    processedStocks: number;
    
    // 分钟K线
    minuteKlineStocks: number;
    minuteKlineRecords: number;
    
    // 龙虎榜
    dragonTigerDays: number;
    dragonTigerRecords: number;
    
    // 北向资金
    northFundDays: number;
    northFundRecords: number;
    
    // 融资融券
    marginStocks: number;
    marginRecords: number;
    
    // 大宗交易
    blockTradeDays: number;
    blockTradeRecords: number;
    
    // 新闻
    newsStocks: number;
    newsRecords: number;
    
    errors: string[];
    startTime: number;
}

/**
 * 通用重试函数
 */
async function retryWithBackoff<T>(
    fn: () => Promise<T>,
    maxRetries: number = 3,
    context: string = ''
): Promise<T> {
    let lastError: any = null;
    
    for (let retry = 0; retry < maxRetries; retry++) {
        try {
            return await fn();
        } catch (error: any) {
            lastError = error;
            
            // 判断是否是网络错误
            const isNetworkError = error.code === 'ECONNRESET' || 
                                  error.code === 'ETIMEDOUT' || 
                                  error.code === 'ECONNREFUSED' ||
                                  error.message?.includes('socket hang up') ||
                                  error.message?.includes('timeout');
            
            if (isNetworkError && retry < maxRetries - 1) {
                // 网络错误，等待后重试
                const waitTime = (retry + 1) * 2000; // 递增等待时间：2s, 4s, 6s
                console.log(`    ⚠️  ${context}: 网络错误，${waitTime/1000}秒后重试 (${retry + 1}/${maxRetries})`);
                await sleep(waitTime);
                continue;
            } else {
                // 非网络错误或已达最大重试次数
                throw error;
            }
        }
    }
    
    throw lastError;
}

/**
 * 下载分钟级K线数据（直接使用新浪接口）
 */
async function downloadMinuteKlines(
    stocks: string[],
    progress: FullInitProgress
): Promise<void> {
    console.log('\n📊 步骤 1/6: 下载分钟级K线数据...');
    console.log('   周期: 5m, 15m, 30m, 60m');
    console.log('   数据源: akshare-mcp (统一数据出口)\n');
    
    const periods = [5, 15, 30, 60]; // 分钟周期
    
    for (const period of periods) {
        console.log(`\n处理 ${period}分钟 K线...`);
        let periodRecords = 0;
        let processed = 0;
        const concurrency = 20; // 并发数
        
        for (let i = 0; i < stocks.length; i += concurrency) {
            const batch = stocks.slice(i, i + concurrency);
            
            // 并行处理
            const results = await Promise.all(batch.map(async (code) => {
                try {
                    const tableName = `kline_${period}m`;
                    const existingCount = await timescaleDB.query(
                        `SELECT COUNT(*) as count FROM ${tableName} WHERE code = $1`,
                        [code]
                    );
                    
                    if (parseInt(existingCount.rows[0]?.count || '0') > 50) {
                        return 0;
                    }
                    
                    const res = await adapterManager.getKline(code, `${period}m` as any, 300);
                    if (!res.success || !res.data || res.data.length === 0) return 0;
                    const klines = res.data;
                    
                    // 批量插入
                    const values: any[] = [];
                    const placeholders: string[] = [];
                    let idx = 1;
                    
                    for (const k of klines) {
                        placeholders.push(`($${idx}, $${idx+1}, $${idx+2}, $${idx+3}, $${idx+4}, $${idx+5}, $${idx+6}, 0, 0, 0)`);
                        values.push(code, new Date(k.date), k.open, k.high, k.low, k.close, k.volume);
                        idx += 7;
                    }
                    
                    if (placeholders.length > 0) {
                        await timescaleDB.query(
                            `INSERT INTO ${tableName} (code, time, open, high, low, close, volume, amount, turnover, change_percent)
                             VALUES ${placeholders.join(',')}
                             ON CONFLICT (code, time) DO NOTHING`,
                            values
                        );
                    }
                    
                    return klines.length;
                } catch {
                    return 0;
                }
            }));
            
            const batchRecords = results.reduce((a, b) => a + b, 0);
            periodRecords += batchRecords;
            processed += batch.length;
            progress.minuteKlineRecords += batchRecords;
            
            if (processed % 200 < concurrency) {
                const percent = (processed / stocks.length * 100).toFixed(1);
                console.log(`  ${processed}/${stocks.length} (${percent}%) | 本周期: ${periodRecords} 条`);
            }
            
            await sleep(500); // 减少延迟
        }
        
        console.log(`✅ ${period}分钟 K线完成: ${periodRecords} 条`);
    }
}

/**
 * 下载龙虎榜数据
 */
async function downloadDragonTiger(
    progress: FullInitProgress,
    days: number = 90
): Promise<void> {
    console.log('\n🐉 步骤 2/6: 下载龙虎榜数据...');
    console.log(`   回溯: 最近${days}天\n`);
    
    const today = new Date();
    
    for (let i = 0; i < days; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];
        
        try {
            const response = await adapterManager.getDragonTiger(dateStr);
            
            if (!response.success || !response.data || response.data.length === 0) {
                if (i % 10 === 0) {
                    console.log(`  ${dateStr}: 无数据`);
                }
                continue;
            }
            
            // 保存到数据库
            for (const item of response.data) {
                await timescaleDB.query(
                    `INSERT INTO dragon_tiger (date, code, name, reason, buy_amount, sell_amount, net_amount, total_amount)
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                     ON CONFLICT (date, code) DO UPDATE SET
                     name = EXCLUDED.name, reason = EXCLUDED.reason,
                     buy_amount = EXCLUDED.buy_amount, sell_amount = EXCLUDED.sell_amount,
                     net_amount = EXCLUDED.net_amount, total_amount = EXCLUDED.total_amount`,
                    [
                        item.date,
                        item.code,
                        item.name,
                        item.reason,
                        item.buyAmount,
                        item.sellAmount,
                        item.netAmount,
                        item.buyAmount + item.sellAmount // totalAmount = buyAmount + sellAmount
                    ]
                );
            }
            
            progress.dragonTigerRecords += response.data.length;
            progress.dragonTigerDays++;
            
            if (i % 10 === 0 || response.data.length > 0) {
                console.log(`  ✅ ${dateStr}: ${response.data.length} 条记录`);
            }
            
        } catch (error) {
            progress.errors.push(`龙虎榜 ${dateStr}: ${error}`);
        }
        
        await sleep(1000); // 每天延迟1秒
    }
    
    console.log(`✅ 龙虎榜完成: ${progress.dragonTigerDays} 天, ${progress.dragonTigerRecords} 条记录`);
}

/**
 * 下载北向资金数据
 */
async function downloadNorthFund(
    progress: FullInitProgress,
    days: number = 365
): Promise<void> {
    console.log('\n💰 步骤 3/6: 下载北向资金数据...');
    console.log(`   回溯: 最近${days}天\n`);
    
    try {
        const response = await adapterManager.getNorthFund(days);
        
        if (!response.success || !response.data || response.data.length === 0) {
            console.log('  ❌ 获取北向资金数据失败');
            progress.errors.push(`北向资金: ${response.error || '无数据'}`);
            return;
        }
        
        // 保存到数据库
        for (const item of response.data) {
            await timescaleDB.query(
                `INSERT INTO north_fund (date, hk_to_sh, hk_to_sz, total, hk_to_sh_balance, hk_to_sz_balance)
                 VALUES ($1, $2, $3, $4, $5, $6)
                 ON CONFLICT (date) DO UPDATE SET
                 hk_to_sh = EXCLUDED.hk_to_sh, hk_to_sz = EXCLUDED.hk_to_sz,
                 total = EXCLUDED.total, hk_to_sh_balance = EXCLUDED.hk_to_sh_balance,
                 hk_to_sz_balance = EXCLUDED.hk_to_sz_balance`,
                [
                    item.date,
                    item.shConnect,
                    item.szConnect,
                    item.total,
                    item.cumulative, // 使用 cumulative 作为余额
                    item.cumulative  // 使用 cumulative 作为余额
                ]
            );
        }
        
        progress.northFundRecords = response.data.length;
        progress.northFundDays = days;
        
        console.log(`✅ 北向资金完成: ${response.data.length} 条记录`);
        
    } catch (error) {
        progress.errors.push(`北向资金: ${error}`);
        console.log(`  ❌ 北向资金失败: ${error}`);
    }
}

/**
 * 下载融资融券数据
 */
async function downloadMarginData(
    stocks: string[],
    progress: FullInitProgress
): Promise<void> {
    console.log('\n📈 步骤 4/6: 下载融资融券数据...');
    console.log('   范围: 全市场融资融券标的\n');
    
    const batchSize = 20;
    const delayBetweenBatches = 3000;
    
    for (let i = 0; i < stocks.length; i += batchSize) {
        const batch = stocks.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stocks.length / batchSize);
        
        console.log(`  批次 ${batchNum}/${totalBatches}`);
        
        for (const code of batch) {
            try {
                const response = await adapterManager.getMarginData(code);
                
                if (!response.success || !response.data || response.data.length === 0) {
                    continue;
                }
                
                // 保存最近的融资融券数据
                for (const item of response.data.slice(0, 90)) { // 最近90天
                    await timescaleDB.query(
                        `INSERT INTO margin_data (date, code, margin_balance, margin_buy, margin_sell, short_balance, short_sell, short_cover, total_balance)
                         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                         ON CONFLICT (date, code) DO UPDATE SET
                         margin_balance = EXCLUDED.margin_balance, margin_buy = EXCLUDED.margin_buy,
                         margin_sell = EXCLUDED.margin_sell, short_balance = EXCLUDED.short_balance,
                         short_sell = EXCLUDED.short_sell, short_cover = EXCLUDED.short_cover,
                         total_balance = EXCLUDED.total_balance`,
                        [
                            item.date,
                            item.code,
                            item.marginBalance,
                            item.marginBuy,
                            item.marginRepay, // marginRepay 对应 margin_sell
                            item.shortBalance,
                            item.shortSell,
                            item.shortRepay, // shortRepay 对应 short_cover
                            item.totalBalance
                        ]
                    );
                }
                
                progress.marginRecords += response.data.length;
                progress.marginStocks++;
                
                if (progress.marginStocks % 50 === 0) {
                    console.log(`    已处理 ${progress.marginStocks} 只股票`);
                }
                
            } catch (error) {
                // 融资融券数据不是所有股票都有，失败是正常的
            }
            
            await sleep(200);
        }
        
        if (i + batchSize < stocks.length) {
            await sleep(delayBetweenBatches);
        }
    }
    
    console.log(`✅ 融资融券完成: ${progress.marginStocks} 只股票, ${progress.marginRecords} 条记录`);
}

/**
 * 下载大宗交易数据
 */
async function downloadBlockTrades(
    progress: FullInitProgress,
    days: number = 90
): Promise<void> {
    console.log('\n📦 步骤 5/6: 下载大宗交易数据...');
    console.log(`   回溯: 最近${days}天\n`);
    
    const today = new Date();
    
    for (let i = 0; i < days; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];
        
        try {
            const response = await adapterManager.getBlockTrades(dateStr);
            
            if (!response.success || !response.data || response.data.length === 0) {
                continue;
            }
            
            // 保存到数据库
            for (const item of response.data) {
                await timescaleDB.query(
                    `INSERT INTO block_trades (date, code, name, price, volume, amount, buyer, seller, premium_rate)
                     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                     ON CONFLICT (date, code, buyer, seller) DO UPDATE SET
                     name = EXCLUDED.name, price = EXCLUDED.price, volume = EXCLUDED.volume,
                     amount = EXCLUDED.amount, premium_rate = EXCLUDED.premium_rate`,
                    [
                        item.date,
                        item.code,
                        item.name,
                        item.price,
                        item.volume,
                        item.amount,
                        item.buyer,
                        item.seller,
                        item.premium // premium 对应 premium_rate
                    ]
                );
            }
            
            progress.blockTradeRecords += response.data.length;
            progress.blockTradeDays++;
            
            if (i % 10 === 0 || response.data.length > 0) {
                console.log(`  ✅ ${dateStr}: ${response.data.length} 条记录`);
            }
            
        } catch (error) {
            progress.errors.push(`大宗交易 ${dateStr}: ${error}`);
        }
        
        await sleep(1000);
    }
    
    console.log(`✅ 大宗交易完成: ${progress.blockTradeDays} 天, ${progress.blockTradeRecords} 条记录`);
}

/**
 * 下载新闻资讯
 */
async function downloadStockNews(
    stocks: string[],
    progress: FullInitProgress
): Promise<void> {
    console.log('\n📰 步骤 6/6: 下载新闻资讯...');
    console.log('   每只股票: 最近20条新闻\n');
    
    const batchSize = 10;
    const delayBetweenBatches = 3000;
    const newsPerStock = 20;
    
    for (let i = 0; i < stocks.length; i += batchSize) {
        const batch = stocks.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stocks.length / batchSize);
        
        console.log(`  批次 ${batchNum}/${totalBatches}`);
        
        for (const code of batch) {
            try {
                const response = await adapterManager.getStockNews(code, newsPerStock);
                
                if (!response.success || !response.data || response.data.length === 0) {
                    continue;
                }
                
                // 保存到数据库
                for (const item of response.data) {
                    await timescaleDB.query(
                        `INSERT INTO stock_news (code, title, time, source, url, content)
                         VALUES ($1, $2, $3, $4, $5, $6)
                         ON CONFLICT (code, title, time) DO NOTHING`,
                        [
                            code,
                            item.title,
                            item.time,
                            item.source,
                            item.url,
                            '' // content 字段暂时为空
                        ]
                    );
                }
                
                progress.newsRecords += response.data.length;
                progress.newsStocks++;
                
                if (progress.newsStocks % 100 === 0) {
                    console.log(`    已处理 ${progress.newsStocks} 只股票`);
                }
                
            } catch (error) {
                // 新闻数据失败不影响整体流程
            }
            
            await sleep(500);
        }
        
        if (i + batchSize < stocks.length) {
            await sleep(delayBetweenBatches);
        }
    }
    
    console.log(`✅ 新闻资讯完成: ${progress.newsStocks} 只股票, ${progress.newsRecords} 条记录`);
}

/**
 * 主流程
 */
async function initFullDatabase() {
    console.log('='.repeat(80));
    console.log('完整数据库初始化脚本 - 高级数据下载');
    console.log('='.repeat(80));
    console.log();
    console.log('⚠️  注意：');
    console.log('   1. 请先运行 init-database.ts 完成基础数据初始化');
    console.log('   2. 本脚本下载高级数据，预计需要数小时');
    console.log('   3. 实时数据（行情、盘口）不需要预下载');
    console.log('   4. 期权数据需要单独实现');
    console.log();

    const progress: FullInitProgress = {
        totalStocks: 0,
        processedStocks: 0,
        minuteKlineStocks: 0,
        minuteKlineRecords: 0,
        dragonTigerDays: 0,
        dragonTigerRecords: 0,
        northFundDays: 0,
        northFundRecords: 0,
        marginStocks: 0,
        marginRecords: 0,
        blockTradeDays: 0,
        blockTradeRecords: 0,
        newsStocks: 0,
        newsRecords: 0,
        errors: [],
        startTime: Date.now(),
    };

    try {
        // 获取股票列表
        console.log('📋 获取股票列表...');
        const stocksResult = await timescaleDB.query('SELECT stock_code FROM stocks ORDER BY stock_code');
        const stocks = stocksResult.rows.map((row: any) => row.stock_code);
        progress.totalStocks = stocks.length;
        console.log(`✅ 获取到 ${stocks.length} 只股票\n`);

        // 下载各类高级数据
        await downloadMinuteKlines(stocks, progress);
        await downloadDragonTiger(progress);
        await downloadNorthFund(progress);
        await downloadMarginData(stocks, progress);
        await downloadBlockTrades(progress);
        await downloadStockNews(stocks, progress);

        // 总结
        const totalTime = ((Date.now() - progress.startTime) / 1000 / 60).toFixed(1);
        console.log();
        console.log('='.repeat(80));
        console.log('✨ 高级数据下载完成！');
        console.log('='.repeat(80));
        console.log();
        console.log('下载统计:');
        console.log(`  分钟K线: ${progress.minuteKlineStocks} 只股票, ${progress.minuteKlineRecords} 条记录`);
        console.log(`  龙虎榜: ${progress.dragonTigerDays} 天, ${progress.dragonTigerRecords} 条记录`);
        console.log(`  北向资金: ${progress.northFundDays} 天, ${progress.northFundRecords} 条记录`);
        console.log(`  融资融券: ${progress.marginStocks} 只股票, ${progress.marginRecords} 条记录`);
        console.log(`  大宗交易: ${progress.blockTradeDays} 天, ${progress.blockTradeRecords} 条记录`);
        console.log(`  新闻资讯: ${progress.newsStocks} 只股票, ${progress.newsRecords} 条记录`);
        console.log(`  总耗时: ${totalTime} 分钟`);
        console.log();

        if (progress.errors.length > 0) {
            console.log(`错误数量: ${progress.errors.length}`);
            console.log('前10个错误:');
            progress.errors.slice(0, 10).forEach(err => console.log(`  - ${err}`));
            console.log();
        }

        console.log('✅ 数据库已完整初始化，可以开始使用！');
        console.log();

    } catch (error) {
        console.error();
        console.error('❌ 初始化失败:', error);
        console.error();
        process.exit(1);
    } finally {
        await timescaleDB.close();
    }
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 运行
initFullDatabase().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
