/**
 * 诊断脚本：检查实时行情数据源和数据库连接
 */

import { timescaleDB } from '../src/storage/timescaledb.js';
import { callAkshareMcpTool } from '../src/adapters/akshare-mcp-client.js';
import { akShareAdapter } from '../src/adapters/akshare-adapter.js';

interface DiagnosticResult {
    category: string;
    item: string;
    status: 'success' | 'error' | 'warning';
    message: string;
    details?: any;
}

const results: DiagnosticResult[] = [];

function addResult(category: string, item: string, status: 'success' | 'error' | 'warning', message: string, details?: any) {
    results.push({ category, item, status, message, details });
}

async function checkDatabaseConnection() {
    console.log('\n📊 检查数据库连接...');
    
    try {
        // 检查环境变量
        const dbHost = process.env.DB_HOST || 'localhost';
        const dbPort = process.env.DB_PORT || '5432';
        const dbName = process.env.DB_NAME || 'postgres';
        const dbUser = process.env.DB_USER || 'postgres';
        
        addResult('数据库', '环境变量', 'success', 
            `配置: ${dbHost}:${dbPort}/${dbName} (用户: ${dbUser})`,
            { DB_HOST: dbHost, DB_PORT: dbPort, DB_NAME: dbName, DB_USER: dbUser }
        );
        
        // 尝试连接数据库
        try {
            await timescaleDB.initialize();
            addResult('数据库', '连接测试', 'success', 'TimescaleDB 连接成功');
            
            // 测试查询
            try {
                const stats = await timescaleDB.getDatabaseStats();
                addResult('数据库', '查询测试', 'success', 
                    `数据库统计: ${stats.totalStocks} 只股票, ${stats.totalKlines} 条K线`,
                    stats
                );
            } catch (err) {
                addResult('数据库', '查询测试', 'warning', 
                    `连接成功但查询失败: ${err instanceof Error ? err.message : String(err)}`,
                    err
                );
            }
        } catch (err) {
            addResult('数据库', '连接测试', 'error', 
                `连接失败: ${err instanceof Error ? err.message : String(err)}`,
                err
            );
        }
    } catch (err) {
        addResult('数据库', '检查过程', 'error', 
            `检查过程出错: ${err instanceof Error ? err.message : String(err)}`,
            err
        );
    }
}

async function checkAkshareMcpConnection() {
    console.log('\n🔌 检查 akshare-mcp 服务连接...');
    
    try {
        // 检查环境变量
        const mcpCommand = process.env.AKSHARE_MCP_COMMAND || '默认';
        const mcpArgs = process.env.AKSHARE_MCP_ARGS || '默认';
        const mcpTimeout = process.env.AKSHARE_MCP_REQUEST_TIMEOUT_MS || '60000';
        
        addResult('akshare-mcp', '环境变量', 'success',
            `配置: 命令=${mcpCommand}, 超时=${mcpTimeout}ms`,
            { 
                AKSHARE_MCP_COMMAND: mcpCommand,
                AKSHARE_MCP_ARGS: mcpArgs,
                AKSHARE_MCP_REQUEST_TIMEOUT_MS: mcpTimeout
            }
        );
        
        // 测试基本连接（通过 listTools）
        try {
            const healthResult = await akShareAdapter.isAvailable();
            if (healthResult) {
                addResult('akshare-mcp', '健康检查', 'success', 'akshare-mcp 服务可用');
            } else {
                addResult('akshare-mcp', '健康检查', 'error', 'akshare-mcp 服务不可用');
            }
        } catch (err) {
            addResult('akshare-mcp', '健康检查', 'error',
                `健康检查失败: ${err instanceof Error ? err.message : String(err)}`,
                err
            );
        }
        
        // 测试获取指数行情（用于健康检查）
        try {
            const indexResult = await callAkshareMcpTool('get_index_quote', { index_code: '000001' });
            if (indexResult.success) {
                addResult('akshare-mcp', '指数行情测试', 'success', 
                    '成功获取指数行情（上证指数）',
                    indexResult.data
                );
            } else {
                addResult('akshare-mcp', '指数行情测试', 'error',
                    `获取指数行情失败: ${indexResult.error || '未知错误'}`,
                    indexResult
                );
            }
        } catch (err) {
            addResult('akshare-mcp', '指数行情测试', 'error',
                `指数行情测试异常: ${err instanceof Error ? err.message : String(err)}`,
                err
            );
        }
        
    } catch (err) {
        addResult('akshare-mcp', '检查过程', 'error',
            `检查过程出错: ${err instanceof Error ? err.message : String(err)}`,
            err
        );
    }
}

async function checkRealtimeQuoteSources() {
    console.log('\n📈 检查实时行情数据源...');
    
    const testCodes = ['000001', '600519'];
    
    for (const code of testCodes) {
        try {
            // 测试通过 akshare-mcp 获取实时行情
            const result = await callAkshareMcpTool('get_realtime_quote', { stock_code: code });
            
            if (result.success && result.data) {
                addResult('实时行情', `${code} (akshare-mcp)`, 'success',
                    `成功获取 ${code} 的实时行情`,
                    {
                        price: result.data.price,
                        change: result.data.change,
                        source: result.source
                    }
                );
            } else {
                addResult('实时行情', `${code} (akshare-mcp)`, 'error',
                    `获取 ${code} 实时行情失败: ${result.error || '未知错误'}`,
                    result
                );
            }
        } catch (err) {
            addResult('实时行情', `${code} (akshare-mcp)`, 'error',
                `获取 ${code} 实时行情异常: ${err instanceof Error ? err.message : String(err)}`,
                err
            );
        }
        
        // 测试通过适配器获取实时行情
        try {
            const quote = await akShareAdapter.getRealtimeQuote(code);
            addResult('实时行情', `${code} (适配器)`, 'success',
                `通过适配器成功获取 ${code} 的实时行情`,
                {
                    price: quote.price,
                    change: quote.change,
                    timestamp: quote.timestamp
                }
            );
        } catch (err) {
            addResult('实时行情', `${code} (适配器)`, 'error',
                `通过适配器获取 ${code} 实时行情失败: ${err instanceof Error ? err.message : String(err)}`,
                err
            );
        }
    }
}

async function checkNetworkConnectivity() {
    console.log('\n🌐 检查网络连接...');
    
    // 检查关键数据源URL的可达性
    const testUrls = [
        { name: 'Sina 行情接口', url: 'http://hq.sinajs.cn/list=sh000001' },
        { name: 'Tencent 行情接口', url: 'http://qt.gtimg.cn/q=sh000001' },
    ];
    
    for (const { name, url } of testUrls) {
        try {
            const response = await fetch(url, { 
                method: 'GET',
                headers: { 'Referer': 'https://finance.sina.com.cn/' },
                signal: AbortSignal.timeout(5000)
            });
            
            if (response.ok) {
                const text = await response.text();
                if (text && text.length > 0) {
                    addResult('网络连接', name, 'success', 
                        `成功访问 ${url}`,
                        { status: response.status, contentLength: text.length }
                    );
                } else {
                    addResult('网络连接', name, 'warning',
                        `访问成功但返回内容为空`,
                        { status: response.status }
                    );
                }
            } else {
                addResult('网络连接', name, 'error',
                    `HTTP ${response.status}: ${response.statusText}`,
                    { status: response.status, url }
                );
            }
        } catch (err) {
            addResult('网络连接', name, 'error',
                `网络请求失败: ${err instanceof Error ? err.message : String(err)}`,
                { url, error: err }
            );
        }
    }
}

function printSummary() {
    console.log('\n' + '='.repeat(60));
    console.log('📋 诊断结果汇总');
    console.log('='.repeat(60));
    
    const categories = new Set(results.map(r => r.category));
    
    for (const category of categories) {
        console.log(`\n【${category}】`);
        const categoryResults = results.filter(r => r.category === category);
        
        for (const result of categoryResults) {
            const icon = result.status === 'success' ? '✅' : result.status === 'error' ? '❌' : '⚠️';
            console.log(`  ${icon} ${result.item}: ${result.message}`);
            if (result.details && process.env.DEBUG) {
                console.log(`     详情:`, JSON.stringify(result.details, null, 2));
            }
        }
    }
    
    const successCount = results.filter(r => r.status === 'success').length;
    const errorCount = results.filter(r => r.status === 'error').length;
    const warningCount = results.filter(r => r.status === 'warning').length;
    
    console.log('\n' + '='.repeat(60));
    console.log(`总计: ✅ ${successCount} | ❌ ${errorCount} | ⚠️ ${warningCount}`);
    console.log('='.repeat(60));
}

async function main() {
    console.log('🔍 开始诊断实时行情数据源和数据库连接...\n');
    
    try {
        await checkDatabaseConnection();
        await checkAkshareMcpConnection();
        await checkRealtimeQuoteSources();
        await checkNetworkConnectivity();
        
        printSummary();
        
        // 关闭数据库连接
        try {
            await timescaleDB.close();
        } catch (err) {
            // 忽略关闭错误
        }
        
    } catch (err) {
        console.error('\n❌ 诊断过程出错:', err);
        process.exit(1);
    }
}

main().catch(console.error);

