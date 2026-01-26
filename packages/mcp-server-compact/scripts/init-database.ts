#!/usr/bin/env node
/**
 * 数据库初始化脚本 - 全量A股数据版本
 * 用于首次部署时初始化 TimescaleDB 并预热全量A股数据
 * 
 * 主要功能:
 * 1. 初始化 TimescaleDB 表结构（包括所有必需的表）
 * 2. 获取全量A股股票列表（5000+只）
 * 3. 批量下载历史K线数据（250天）
 * 4. 批量下载财务数据
 * 5. 初始化默认数据（watchlist_groups, paper_accounts等）
 * 
 * 数据表清单:
 * - stocks: 股票基础信息
 * - kline_1d: 日线数据（Hypertable）
 * - stock_quotes: 实时行情（Hypertable）
 * - financials: 财务数据
 * - positions: 持仓
 * - watchlist/watchlist_groups: 自选股
 * - paper_accounts/paper_positions/paper_trades: 模拟交易
 * - backtest_results/backtest_trades/backtest_equity: 回测结果
 * - daily_pnl: 每日盈亏
 * - stock_embeddings/pattern_vectors/vector_documents: 向量数据
 * - price_alerts/indicator_alerts/combo_alerts等: 预警系统
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { AdapterManager } from '../src/adapters/index.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';

interface StockBasicInfo {
    code: string;
    name: string;
    market: string;
    sector?: string;
    industry?: string;
    listDate?: string;
}

interface InitProgress {
    totalStocks: number;
    processedStocks: number;
    successStocks: number;
    failedStocks: string[];
    klineRecords: number;
    financialRecords: number;
    vectorRecords: number;
    startTime: number;
}

/**
 * 获取全量A股股票列表
 */
async function getAllAShareStocks(): Promise<StockBasicInfo[]> {
    console.log('📋 正在获取全量A股股票列表...');
    
    try {
        // 使用 akshare-mcp 的 get_stock_list 工具获取全市场股票列表
        const response = await callAkshareMcpTool<any>('get_stock_list', {});
        
        if (!response.success || !response.data) {
            throw new Error(`获取股票列表失败: ${response.error || '未知错误'}`);
        }

        const stocks: StockBasicInfo[] = [];
        const data = response.data;

        // 解析返回的数据
        if (Array.isArray(data)) {
            for (const item of data) {
                const code = item.code || item['代码'] || item.symbol;
                const name = item.name || item['名称'] || item['股票名称'];
                
                if (code && name) {
                    stocks.push({
                        code: normalizeStockCode(code),
                        name: name,
                        market: getMarketFromCode(code),
                        sector: item.sector || item['板块'] || item['行业'],
                        industry: item.industry || item['细分行业'],
                        listDate: item.listDate || item['上市日期']
                    });
                }
            }
        }

        console.log(`✅ 成功获取 ${stocks.length} 只A股股票`);
        return stocks;
        
    } catch (error) {
        console.error('❌ 获取股票列表失败:', error);
        
        // 降级方案：使用预定义的主要股票池
        console.log('⚠️  使用降级方案：主要股票池（约100只核心股票）');
        return getFallbackStockList();
    }
}

/**
 * 标准化股票代码格式
 */
function normalizeStockCode(code: string): string {
    // 移除可能的前缀（如 SH、SZ）
    code = code.replace(/^(SH|SZ|sh|sz)/i, '');
    // 确保6位数字
    return code.padStart(6, '0');
}

/**
 * 根据股票代码判断市场
 */
function getMarketFromCode(code: string): string {
    const normalized = normalizeStockCode(code);
    
    if (normalized.startsWith('6')) {
        return 'SH'; // 上海主板
    } else if (normalized.startsWith('00')) {
        return 'SZ'; // 深圳主板
    } else if (normalized.startsWith('30')) {
        return 'CYB'; // 创业板
    } else if (normalized.startsWith('68')) {
        return 'KCB'; // 科创板
    } else if (normalized.startsWith('8') || normalized.startsWith('4')) {
        return 'BJ'; // 北交所
    }
    
    return 'UNKNOWN';
}

/**
 * 降级方案：返回主要股票池
 * 包含：沪深300成分股 + 创业板50 + 科创50 + 热门股票
 */
function getFallbackStockList(): StockBasicInfo[] {
    // 这里可以预定义一个较大的股票池（300-500只核心股票）
    const coreStocks = [
        // 沪深300权重股
        '000001', '000002', '000333', '000858', '000876', '000895', '000938',
        '600000', '600036', '600519', '600887', '601318', '601398', '601857',
        '601988', '601166', '601288', '601628', '601668', '601818', '601888',
        
        // 创业板龙头
        '300059', '300122', '300124', '300142', '300347', '300408', '300450',
        '300498', '300750', '300760',
        
        // 科创板龙头
        '688012', '688036', '688111', '688126', '688169', '688187', '688223',
        '688303', '688396', '688561', '688599', '688981',
        
        // 新能源汽车产业链
        '002594', '002920', '300014', '300750', '600104', '600741', '601012',
        
        // 半导体产业链
        '002049', '002371', '002415', '002475', '002916', '300782', '603501',
        
        // 医药生物
        '000538', '000661', '002007', '002821', '300003', '300015', '600276',
        '600436', '600521', '603259', '688185',
    ];

    return coreStocks.map(code => ({
        code,
        name: `股票${code}`, // 实际名称需要后续查询
        market: getMarketFromCode(code),
    }));
}

/**
 * 批量下载K线数据
 */
async function downloadKlineData(
    stocks: StockBasicInfo[],
    progress: InitProgress,
    lookbackDays: number = 250
): Promise<void> {
    const adapterManager = new AdapterManager();
    const batchSize = 3; // 进一步减小批次大小，从5改为3
    const delayBetweenBatches = 5000; // 增加批次间延迟，从3秒改为5秒
    const delayBetweenStocks = 1000; // 增加股票间延迟，从500ms改为1000ms
    
    console.log(`\n📈 开始下载K线数据（回溯 ${lookbackDays} 天）...`);
    console.log(`   批次大小: ${batchSize}, 批次间延迟: ${delayBetweenBatches}ms, 股票间延迟: ${delayBetweenStocks}ms`);
    console.log(`   ⚠️  为避免IP被封，已降低请求频率\n`);
    
    for (let i = 0; i < stocks.length; i += batchSize) {
        const batch = stocks.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stocks.length / batchSize);
        
        console.log(`\n处理批次 ${batchNum}/${totalBatches} (${batch.length} 只股票)`);
        
        // 串行处理批次内的股票，避免并发过高
        for (const stock of batch) {
            await downloadSingleStockKline(stock, adapterManager, lookbackDays, progress);
            // 股票间延迟
            if (delayBetweenStocks > 0) {
                await sleep(delayBetweenStocks);
            }
        }
        
        // 显示进度
        const percent = ((progress.processedStocks / progress.totalStocks) * 100).toFixed(1);
        const elapsed = ((Date.now() - progress.startTime) / 1000).toFixed(0);
        const avgTime = progress.processedStocks > 0 ? (Date.now() - progress.startTime) / progress.processedStocks : 0;
        const remaining = Math.ceil((progress.totalStocks - progress.processedStocks) * avgTime / 1000);
        
        console.log(`进度: ${progress.processedStocks}/${progress.totalStocks} (${percent}%)`);
        console.log(`成功: ${progress.successStocks}, 失败: ${progress.failedStocks.length}`);
        console.log(`K线记录: ${progress.klineRecords}, 耗时: ${elapsed}s, 预计剩余: ${remaining}s`);
        
        // 批次间延迟，避免请求过快
        if (i + batchSize < stocks.length) {
            await sleep(delayBetweenBatches);
        }
    }
}

/**
 * 下载单只股票的K线数据（带重试机制）
 */
async function downloadSingleStockKline(
    stock: StockBasicInfo,
    adapterManager: AdapterManager,
    lookbackDays: number,
    progress: InitProgress
): Promise<void> {
    const maxRetries = 3;
    let lastError: any = null;
    
    try {
        // 检查是否已有足够的K线数据（跳过已完成的股票）
        const existingCount = await timescaleDB.query(
            'SELECT COUNT(*) as count FROM kline_1d WHERE code = $1',
            [stock.code]
        );
        
        if (existingCount.rows[0]?.count >= 200) {
            // 已有足够数据，跳过
            progress.successStocks++;
            progress.processedStocks++;
            console.log(`  ⏭️  ${stock.code} ${stock.name}: 已有 ${existingCount.rows[0].count} 条K线，跳过`);
            return;
        }
        
        // 重试机制
        for (let retry = 0; retry < maxRetries; retry++) {
            try {
                // 获取K线数据
                const klineResponse = await adapterManager.getKline(stock.code, 'daily', lookbackDays);
                
                if (!klineResponse.success || !klineResponse.data || klineResponse.data.length === 0) {
                    throw new Error(klineResponse.error || '无数据');
                }

                // 批量写入数据库
                const klineRows = klineResponse.data.map(k => ({
                    code: stock.code,
                    date: new Date(k.date),
                    open: k.open,
                    high: k.high,
                    low: k.low,
                    close: k.close,
                    volume: k.volume,
                    amount: k.amount || 0,
                    turnover: 0,
                    change_percent: 0,
                }));

                const { inserted, updated } = await timescaleDB.batchUpsertKline(klineRows);
                progress.klineRecords += inserted + updated;
                progress.successStocks++;
                
                console.log(`  ✅ ${stock.code} ${stock.name}: ${inserted + updated} 条K线`);
                return; // 成功，退出重试循环
                
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
                    console.log(`  ⚠️  ${stock.code} ${stock.name}: 网络错误，${waitTime/1000}秒后重试 (${retry + 1}/${maxRetries})`);
                    await sleep(waitTime);
                    continue;
                } else {
                    // 非网络错误或已达最大重试次数
                    throw error;
                }
            }
        }
        
        // 所有重试都失败
        throw lastError;
        
    } catch (error: any) {
        progress.failedStocks.push(stock.code);
        
        // 简化错误信息
        let errorMsg = error instanceof Error ? error.message : String(error);
        if (error.code === 'ECONNRESET') {
            errorMsg = '连接被重置';
        } else if (error.code === 'ETIMEDOUT') {
            errorMsg = '连接超时';
        } else if (errorMsg.includes('socket hang up')) {
            errorMsg = '连接中断';
        }
        
        console.log(`  ❌ ${stock.code} ${stock.name}: ${errorMsg}`);
    } finally {
        progress.processedStocks++;
    }
}

/**
 * 批量下载财务数据
 */
async function downloadFinancialData(
    stocks: StockBasicInfo[],
    progress: InitProgress
): Promise<void> {
    const adapterManager = new AdapterManager();
    const batchSize = 5; // 财务数据请求较慢，减小批次
    const delayBetweenBatches = 2000; // 批次间延迟2秒
    
    console.log(`\n💰 开始下载财务数据...`);
    progress.processedStocks = 0; // 重置进度计数
    
    for (let i = 0; i < stocks.length; i += batchSize) {
        const batch = stocks.slice(i, i + batchSize);
        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(stocks.length / batchSize);
        
        console.log(`\n处理批次 ${batchNum}/${totalBatches} (${batch.length} 只股票)`);
        
        // 并行处理批次内的股票
        const promises = batch.map(stock => downloadSingleStockFinancial(stock, adapterManager, progress));
        await Promise.allSettled(promises);
        
        // 显示进度
        const percent = ((progress.processedStocks / progress.totalStocks) * 100).toFixed(1);
        console.log(`进度: ${progress.processedStocks}/${progress.totalStocks} (${percent}%)`);
        console.log(`财务记录: ${progress.financialRecords}`);
        
        // 批次间延迟
        if (i + batchSize < stocks.length) {
            await sleep(delayBetweenBatches);
        }
    }
}

/**
 * 下载单只股票的财务数据
 */
async function downloadSingleStockFinancial(
    stock: StockBasicInfo,
    adapterManager: AdapterManager,
    progress: InitProgress
): Promise<void> {
    try {
        const financialResponse = await adapterManager.getFinancials(stock.code);
        
        if (financialResponse.success && financialResponse.data) {
            await timescaleDB.upsertFinancials({
                code: stock.code,
                report_date: financialResponse.data.reportDate,
                revenue: financialResponse.data.revenue,
                net_profit: financialResponse.data.netProfit,
                gross_margin: financialResponse.data.grossProfitMargin,
                net_margin: financialResponse.data.netProfitMargin,
                debt_ratio: financialResponse.data.debtRatio,
                current_ratio: financialResponse.data.currentRatio,
                eps: financialResponse.data.eps,
                roe: financialResponse.data.roe,
                revenue_growth: financialResponse.data.revenueGrowth,
                profit_growth: financialResponse.data.netProfitGrowth,
            });
            progress.financialRecords++;
            console.log(`  ✅ ${stock.code} ${stock.name}: 财务数据已保存`);
        }
    } catch (error) {
        // 财务数据失败不影响整体流程
        console.log(`  ⚠️  ${stock.code} ${stock.name}: 财务数据获取失败`);
    } finally {
        progress.processedStocks++;
    }
}

/**
 * 生成股票向量数据（用于相似度搜索）
 */
async function generateVectorData(
    stocks: StockBasicInfo[],
    progress: InitProgress
): Promise<void> {
    console.log(`\n🔍 生成向量数据...`);
    
    // TODO: 实现向量生成逻辑
    // 1. 基于技术指标生成技术面向量
    // 2. 基于财务指标生成基本面向量
    // 3. 基于K线形态生成形态向量
    
    console.log('⚠️  向量数据生成功能待实现，跳过此步骤');
}

/**
 * 初始化默认数据
 */
async function initializeDefaultData(): Promise<void> {
    console.log('\n💾 初始化默认数据...');
    
    try {
        // 1. 确保默认自选股分组存在（已在 initialize() 中创建）
        console.log('  ✅ 默认自选股分组已创建');
        
        // 2. 创建默认模拟交易账户（可选）
        try {
            await timescaleDB.createPaperAccount('default', '默认模拟账户', 1000000);
            console.log('  ✅ 默认模拟交易账户已创建（初始资金：100万）');
        } catch (error) {
            // 账户可能已存在
            console.log('  ℹ️  默认模拟交易账户已存在');
        }
        
        console.log('✅ 默认数据初始化完成\n');
    } catch (error) {
        console.warn('⚠️  默认数据初始化部分失败:', error);
    }
}

/**
 * 主初始化流程
 */
async function initDatabase() {
    console.log('='.repeat(80));
    console.log('数据库初始化脚本 - 全量A股数据版本');
    console.log('='.repeat(80));
    console.log();

    const progress: InitProgress = {
        totalStocks: 0,
        processedStocks: 0,
        successStocks: 0,
        failedStocks: [],
        klineRecords: 0,
        financialRecords: 0,
        vectorRecords: 0,
        startTime: Date.now(),
    };

    try {
        // 步骤 1: 初始化 TimescaleDB 表结构
        console.log('📦 步骤 1/6: 初始化 TimescaleDB 表结构...');
        await timescaleDB.initialize();
        console.log('✅ TimescaleDB 表结构初始化成功');
        console.log('   包含表: stocks, kline_1d, stock_quotes, financials, positions,');
        console.log('           watchlist, paper_accounts, backtest_results, daily_pnl,');
        console.log('           stock_embeddings, pattern_vectors, alerts 等\n');

        // 步骤 2: 初始化默认数据
        console.log('💾 步骤 2/6: 初始化默认数据...');
        await initializeDefaultData();

        // 步骤 3: 获取全量A股股票列表
        console.log('📊 步骤 3/6: 获取全量A股股票列表...');
        
        // 先尝试从数据库获取已有股票列表
        let stocks: StockBasicInfo[] = [];
        try {
            const existingStocks = await timescaleDB.query('SELECT stock_code, stock_name, market, sector, industry FROM stocks ORDER BY stock_code');
            if (existingStocks.rows.length > 0) {
                stocks = existingStocks.rows.map((row: any) => ({
                    code: row.stock_code,
                    name: row.stock_name || `股票${row.stock_code}`,
                    market: row.market || getMarketFromCode(row.stock_code),
                    sector: row.sector,
                    industry: row.industry,
                }));
                console.log(`✅ 从数据库加载 ${stocks.length} 只股票`);
            }
        } catch (error) {
            console.log('⚠️  数据库中无股票数据，尝试从API获取...');
        }
        
        // 如果数据库没有数据，从API获取
        if (stocks.length === 0) {
            stocks = await getAllAShareStocks();
        }
        
        progress.totalStocks = stocks.length;
        console.log(`✅ 获取到 ${stocks.length} 只股票\n`);

        // 步骤 4: 保存股票基础信息到数据库
        console.log('� 步骤 4/6: 保存股票基础信息...');
        let savedCount = 0;
        for (const stock of stocks) {
            try {
                await timescaleDB.upsertStock(stock);
                savedCount++;
            } catch (error) {
                console.error(`  ❌ 保存失败 ${stock.code}: ${error}`);
            }
        }
        console.log(`✅ 已保存 ${savedCount}/${stocks.length} 只股票的基础信息\n`);

        // 步骤 5: 批量下载K线数据
        console.log('� 步骤 5/6: 批量下载K线数据...');
        console.log('   这可能需要 30-60 分钟，请耐心等待...\n');
        await downloadKlineData(stocks, progress, 250);
        console.log(`\n✅ K线数据下载完成: ${progress.klineRecords} 条记录\n`);

        // 步骤 6: 批量下载财务数据
        console.log('💰 步骤 6/6: 批量下载财务数据...');
        console.log('   这可能需要 20-40 分钟，请耐心等待...\n');
        await downloadFinancialData(stocks, progress);
        console.log(`\n✅ 财务数据下载完成: ${progress.financialRecords} 条记录\n`);

        // 步骤 6: 生成向量数据（可选）
        // await generateVectorData(stocks, progress);

        // 验证数据
        console.log('🔍 验证数据完整性...');
        const stats = await timescaleDB.getDatabaseStats();
        console.log(`  股票数量: ${stats.stockCount}`);
        console.log(`  K线记录: ${stats.dailyBarRecords}`);
        console.log(`  财务记录: ${stats.financialRecords}`);
        console.log(`  行情记录: ${stats.quoteRecords}`);

        // 总结
        const totalTime = ((Date.now() - progress.startTime) / 1000 / 60).toFixed(1);
        console.log();
        console.log('='.repeat(80));
        console.log('✨ 数据库初始化完成！');
        console.log('='.repeat(80));
        console.log();
        console.log('初始化统计:');
        console.log(`  总股票数: ${progress.totalStocks}`);
        console.log(`  成功处理: ${progress.successStocks}`);
        console.log(`  失败数量: ${progress.failedStocks.length}`);
        console.log(`  K线记录: ${progress.klineRecords}`);
        console.log(`  财务记录: ${progress.financialRecords}`);
        console.log(`  总耗时: ${totalTime} 分钟`);
        console.log();

        if (progress.failedStocks.length > 0) {
            console.log('失败的股票代码:');
            console.log(`  ${progress.failedStocks.slice(0, 20).join(', ')}`);
            if (progress.failedStocks.length > 20) {
                console.log(`  ... 还有 ${progress.failedStocks.length - 20} 只`);
            }
            console.log();
        }

        console.log('下一步:');
        console.log('  1. 启动 MCP 服务: npm start');
        console.log('  2. 使用 data_warmup 工具进行增量更新');
        console.log('  3. 配置定时任务保持数据最新');
        console.log();

    } catch (error) {
        console.error();
        console.error('❌ 初始化失败:', error);
        console.error();
        console.error('可能的原因:');
        console.error('  1. TimescaleDB 未运行');
        console.error('  2. 数据库连接配置错误');
        console.error('  3. akshare-mcp 服务未启动');
        console.error('  4. 网络问题导致数据获取失败');
        console.error();
        console.error('解决方案:');
        console.error('  1. 检查 TimescaleDB: docker ps | grep timescale');
        console.error('  2. 检查环境变量: echo $DATABASE_URL');
        console.error('  3. 检查 akshare-mcp: uvx akshare-mcp');
        console.error('  4. 查看详细日志: tail -f logs/error.log');
        console.error();
        process.exit(1);
    } finally {
        await timescaleDB.close();
    }
}

/**
 * 辅助函数：延迟
 */
function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 运行初始化
initDatabase().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
