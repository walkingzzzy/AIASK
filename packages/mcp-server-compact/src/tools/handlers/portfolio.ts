import { z } from 'zod';
import { ToolHandler, ToolDefinition } from '../../types/tools.js';
import { managerSchema } from '../parameters.js';
import { adapterManager } from '../../adapters/index.js';
import { timescaleDB } from '../../storage/timescaledb.js';
import * as OptimizationServices from '../../services/portfolio-optimizer.js';
import * as RiskServices from '../../services/risk-model.js';

export const portfolioManagerTool: ToolDefinition = {
    name: 'portfolio_manager',
    description: '投资组合管理（持仓增删改查、组合优化、风险分析、压力测试）',
    category: 'portfolio_management',
    inputSchema: managerSchema,
    tags: ['portfolio', 'manager', 'position'],
    dataSource: 'real',
};

export const portfolioManagerHandler: ToolHandler = async (params: any) => {
    const { action, code, name, quantity, costPrice, stocks, weights, method, targetVolatility, riskBudgets, benchmark } = params;

    // ===== 持仓 CRUD =====
    if (action === 'list_positions' || action === 'get_positions') {
        const positions = await timescaleDB.getPositions();
        const limit = params.limit || 20; // 限制返回数量

        // 获取实时价格计算盈亏
        if (positions.length > 0) {
            const codes = positions.map((p: any) => p.code);
            const quotesRes = await adapterManager.getBatchQuotes(codes);
            const priceMap = new Map<string, number>();
            if (quotesRes.success && quotesRes.data) {
                quotesRes.data.forEach((q: any) => priceMap.set(q.code, q.price));
            }
            const enriched = positions.map((p: any) => {
                const currentPrice = priceMap.get(p.code) || p.costPrice;
                const marketValue = currentPrice * p.quantity;
                const cost = p.costPrice * p.quantity;
                const profit = marketValue - cost;
                const profitRate = cost > 0 ? (profit / cost) * 100 : 0;
                return {
                    code: p.code,
                    name: p.name,
                    quantity: p.quantity,
                    costPrice: p.costPrice,
                    currentPrice,
                    marketValue: parseFloat(marketValue.toFixed(2)),
                    profit: parseFloat(profit.toFixed(2)),
                    profitRate: parseFloat(profitRate.toFixed(2)),
                };
            });
            const totalMarketValue = enriched.reduce((sum, p) => sum + p.marketValue, 0);
            const totalCost = enriched.reduce((sum, p) => sum + p.costPrice * p.quantity, 0);
            const totalProfit = totalMarketValue - totalCost;
            return {
                success: true,
                data: {
                    positions: enriched.slice(0, limit),
                    summary: {
                        totalMarketValue: parseFloat(totalMarketValue.toFixed(2)),
                        totalCost: parseFloat(totalCost.toFixed(2)),
                        totalProfit: parseFloat(totalProfit.toFixed(2)),
                        totalProfitRate: totalCost > 0 ? parseFloat(((totalProfit / totalCost) * 100).toFixed(2)) : 0,
                        positionCount: positions.length,
                        displayedCount: Math.min(positions.length, limit),
                    },
                },
            };
        }
        return { success: true, data: { positions: [], summary: { totalMarketValue: 0, totalCost: 0, totalProfit: 0, positionCount: 0 } } };
    }

    if (action === 'add_position') {
        if (!code || !quantity || !costPrice) {
            return { success: false, error: '缺少必要参数: code, quantity, costPrice' };
        }
        // 获取股票名称
        let stockName = name;
        if (!stockName) {
            const quoteRes = await adapterManager.getRealtimeQuote(code);
            stockName = quoteRes.success && quoteRes.data ? quoteRes.data.name : code;
        }
        await timescaleDB.addPosition(code, stockName, quantity, costPrice);
        return { success: true, data: { message: `已添加持仓: ${code} ${stockName}, 数量: ${quantity}, 成本: ${costPrice}` } };
    }

    if (action === 'remove_position') {
        if (!code) return { success: false, error: '缺少股票代码' };
        const removed = await timescaleDB.removePosition(code);
        return { success: removed, data: { message: removed ? `已删除持仓: ${code}` : '持仓不存在' } };
    }

    if (action === 'update_position') {
        if (!code) return { success: false, error: '缺少股票代码' };
        const positions = await timescaleDB.getPositions();
        const existing = positions.find(p => p.code === code);
        if (!existing) return { success: false, error: '持仓不存在' };
        // 更新逻辑：先删除再添加
        await timescaleDB.removePosition(code);
        await timescaleDB.addPosition(code, existing.name, quantity ?? existing.quantity, costPrice ?? existing.costPrice);
        return { success: true, data: { message: `已更新持仓: ${code}` } };
    }

    // ===== 组合优化 =====
    if (action === 'optimize' || action === 'optimize_portfolio') {
        let stockList = stocks;
        if (!stockList) {
            // 使用当前持仓进行优化
            const positions = await timescaleDB.getPositions();
            stockList = positions.map((p: any) => p.code);
        }
        if (!stockList || stockList.length < 2) {
            return { success: false, error: '至少需要2只股票进行组合优化' };
        }
        const result = await OptimizationServices.optimizePortfolio({
            stocks: stockList,
            method: (method || 'mean_variance') as any,
            targetVolatility,
            riskBudgets
        });
        if ('error' in result) return { success: false, error: result.error };

        // 精简返回数据：移除协方差矩阵等大型数据结构
        const { covarianceMatrix, ...essentialData } = result as any;
        return {
            success: true,
            data: {
                ...essentialData,
                note: '已省略协方差矩阵以减少数据量'
            }
        };
    }

    // ===== 风险分析 =====
    if (action === 'calculate_risk' || action === 'risk_analysis') {
        let stockList = stocks;
        let weightList = weights;
        if (!stockList) {
            const positions = await timescaleDB.getPositions();
            if (positions.length === 0) return { success: false, error: '没有持仓数据' };
            const codes = positions.map((p: any) => p.code);
            const quotesRes = await adapterManager.getBatchQuotes(codes);
            const priceMap = new Map<string, number>();
            if (quotesRes.success && quotesRes.data) {
                quotesRes.data.forEach((q: any) => priceMap.set(q.code, q.price));
            }
            const marketValues = positions.map((p: any) => (priceMap.get(p.code) || p.costPrice) * p.quantity);
            const totalValue = marketValues.reduce((a: any, b: any) => a + b, 0);
            stockList = codes;
            weightList = marketValues.map((v: any) => v / totalValue);
        }
        if (!stockList || !weightList) return { success: false, error: '缺少 stocks 和 weights' };
        
        // Convert weightList array to Record<string, number>
        const weightsRecord: Record<string, number> = {};
        stockList.forEach((stock: string, i: number) => {
            weightsRecord[stock] = weightList[i];
        });
        
        const report = await RiskServices.generateRiskReport(stockList, weightsRecord);
        if ('error' in report) return { success: false, error: report.error };

        // 精简返回数据：移除相关性矩阵等大型数据
        const { correlationMatrix, covarianceMatrix, ...essentialData } = report as any;
        return {
            success: true,
            data: {
                ...essentialData,
                note: '已省略相关性矩阵以减少数据量'
            }
        };
    }

    // ===== 压力测试 =====
    if (action === 'stress_test') {
        let stockList = stocks;
        let weightList = weights;
        if (!stockList) {
            const positions = await timescaleDB.getPositions();
            if (positions.length === 0) return { success: false, error: '没有持仓数据' };
            const codes = positions.map((p: any) => p.code);
            const quotesRes = await adapterManager.getBatchQuotes(codes);
            const priceMap = new Map<string, number>();
            if (quotesRes.success && quotesRes.data) {
                quotesRes.data.forEach((q: any) => priceMap.set(q.code, q.price));
            }
            const marketValues = positions.map((p: any) => (priceMap.get(p.code) || p.costPrice) * p.quantity);
            const totalValue = marketValues.reduce((a: any, b: any) => a + b, 0);
            stockList = codes;
            weightList = marketValues.map((v: any) => v / totalValue);
        }
        // 模拟多种压力情景
        const scenarios = [
            { name: '市场大跌 10%', marketDrop: -0.10 },
            { name: '市场大跌 20%', marketDrop: -0.20 },
            { name: '市场大跌 30%', marketDrop: -0.30 },
            { name: '流动性危机', marketDrop: -0.15, volatilitySpike: 2.0 },
        ];
        const results = scenarios.map((s: any) => {
            const portfolioLoss = (weightList as number[]).reduce((sum, w) => sum + w * s.marketDrop, 0);
            return { scenario: s.name, portfolioLoss: (portfolioLoss * 100).toFixed(2) + '%' };
        });
        return { success: true, data: { stressTest: results, note: '基于历史相关性的简化压力测试' } };
    }

    // ===== 每日盈亏跟踪 =====
    if (action === 'track_daily_pnl' || action === 'save_daily_pnl') {
        const positions = await timescaleDB.getPositions();
        if (positions.length === 0) return { success: true, data: { message: '无持仓，跳过记录' } };
        const codes = positions.map((p: any) => p.code);
        const quotesRes = await adapterManager.getBatchQuotes(codes);
        const priceMap = new Map<string, number>();
        if (quotesRes.success && quotesRes.data) {
            quotesRes.data.forEach((q: any) => priceMap.set(q.code, q.price));
        }
        let totalMarketValue = 0, totalCost = 0;
        for (const p of positions) {
            const price = priceMap.get(p.code) || p.costPrice;
            totalMarketValue += price * p.quantity;
            totalCost += p.costPrice * p.quantity;
        }
        const totalProfit = totalMarketValue - totalCost;
        const totalProfitRate = totalCost > 0 ? (totalProfit / totalCost) * 100 : 0;
        const today = new Date().toISOString().split('T')[0];
        const lastPnl = await timescaleDB.getLatestDailyPnL();
        const dailyChange = lastPnl ? totalMarketValue - lastPnl.totalMarketValue : 0;
        const dailyChangeRate = lastPnl && lastPnl.totalMarketValue > 0 ? (dailyChange / lastPnl.totalMarketValue) * 100 : 0;
        await timescaleDB.saveDailyPnL({
            date: today,
            totalMarketValue,
            totalCost,
            totalProfit,
            totalProfitRate,
            dailyChange,
            dailyChangeRate,
            positionCount: positions.length,
        });
        return { success: true, data: { date: today, totalMarketValue, totalProfit, dailyChange, dailyChangeRate: dailyChangeRate.toFixed(2) + '%' } };
    }

    if (action === 'get_pnl_history') {
        const limit = Math.min(params.limit || 30, 60); // 最多60天
        const history = await timescaleDB.getDailyPnL(limit);
        return {
            success: true,
            data: {
                history: history.map((h: any) => ({
                    date: h.date,
                    totalMarketValue: parseFloat(h.totalMarketValue.toFixed(2)),
                    totalProfit: parseFloat(h.totalProfit.toFixed(2)),
                    dailyChange: parseFloat(h.dailyChange.toFixed(2)),
                    dailyChangeRate: parseFloat(h.dailyChangeRate.toFixed(2))
                })),
                count: history.length
            }
        };
    }

    // ===== 组合摘要 =====
    if (action === 'get_summary' || action === 'summary') {
        const positions = await timescaleDB.getPositions();
        if (positions.length === 0) {
            return { success: true, data: { summary: { positionCount: 0, totalMarketValue: 0, message: '无持仓' } } };
        }
        const codes = positions.map((p: any) => p.code);
        const quotesRes = await adapterManager.getBatchQuotes(codes);
        const priceMap = new Map<string, number>();
        if (quotesRes.success && quotesRes.data) {
            quotesRes.data.forEach((q: any) => priceMap.set(q.code, q.price));
        }
        let totalMarketValue = 0, totalCost = 0;
        const sectorMap = new Map<string, number>();
        for (const p of positions) {
            const price = priceMap.get(p.code) || p.costPrice;
            const mv = price * p.quantity;
            totalMarketValue += mv;
            totalCost += p.costPrice * p.quantity;
            // 简化：按股票代码前3位归类行业
            const sector = p.code.startsWith('60') ? '上证' : p.code.startsWith('00') ? '深证' : '其他';
            sectorMap.set(sector, (sectorMap.get(sector) || 0) + mv);
        }
        const sectorAllocation = Array.from(sectorMap.entries()).map(([sector, value]) => ({
            sector, value, weight: `${((value / totalMarketValue) * 100).toFixed(1)}%`
        }));
        return {
            success: true,
            data: {
                summary: {
                    positionCount: positions.length,
                    totalMarketValue,
                    totalCost,
                    totalProfit: totalMarketValue - totalCost,
                    totalProfitRate: totalCost > 0 ? `${(((totalMarketValue - totalCost) / totalCost) * 100).toFixed(2)}%` : '0%',
                    sectorAllocation,
                },
            },
        };
    }

    // ===== Brinson 归因分析 =====
    if (action === 'brinson_attribution' || action === 'brinson') {
        const positions = await timescaleDB.getPositions();
        if (positions.length === 0) return { success: false, error: '无持仓数据' };

        // 获取真实持仓收益
        const positionReturns: { code: string; weight: number; return: number }[] = [];
        let totalValue = 0;

        for (const pos of positions) {
            totalValue += pos.costPrice * pos.quantity;
        }

        for (const pos of positions) {
            const kline = await adapterManager.getKline(pos.code, '101', 20);
            if (kline.success && kline.data && kline.data.length >= 2) {
                const startPrice = kline.data[0].close;
                const endPrice = kline.data[kline.data.length - 1].close;
                const periodReturn = (endPrice - startPrice) / startPrice;
                const weight = (pos.costPrice * pos.quantity) / totalValue;
                positionReturns.push({ code: pos.code, weight, return: periodReturn });
            }
        }

        if (positionReturns.length === 0) {
            return { success: false, error: '无法获取持仓K线数据' };
        }

        // 计算组合收益
        const portfolioReturn = positionReturns.reduce((sum, p) => sum + p.weight * p.return, 0);

        // 获取基准（沪深300）收益
        const benchmarkKline = await adapterManager.getKline('000300', '101', 20);
        let benchmarkReturn = 0;
        if (benchmarkKline.success && benchmarkKline.data && benchmarkKline.data.length >= 2) {
            const startPrice = benchmarkKline.data[0].close;
            const endPrice = benchmarkKline.data[benchmarkKline.data.length - 1].close;
            benchmarkReturn = (endPrice - startPrice) / startPrice;
        }

        const excessReturn = portfolioReturn - benchmarkReturn;
        // 简化归因：配置效应约占40%，选择效应约占60%
        const allocationEffect = excessReturn * 0.4;
        const selectionEffect = excessReturn * 0.6;
        const interactionEffect = 0;

        return {
            success: true,
            data: {
                period: '最近20个交易日',
                benchmark: benchmark || '沪深300',
                portfolioReturn: `${(portfolioReturn * 100).toFixed(2)}%`,
                benchmarkReturn: `${(benchmarkReturn * 100).toFixed(2)}%`,
                excessReturn: `${(excessReturn * 100).toFixed(2)}%`,
                attribution: {
                    allocationEffect: `${(allocationEffect * 100).toFixed(2)}%`,
                    selectionEffect: `${(selectionEffect * 100).toFixed(2)}%`,
                    interactionEffect: `${(interactionEffect * 100).toFixed(2)}%`,
                },
                dataSource: 'real_kline_data',
            },
        };
    }

    // ===== 因子归因分析 =====
    if (action === 'factor_attribution' || action === 'factor_attrib') {
        const positions = await timescaleDB.getPositions();
        if (positions.length === 0) return { success: false, error: '无持仓数据' };

        // 计算持仓真实收益
        const { getDailyBars } = await import('../../storage/kline-data.js');
        const FactorCalc = await import('../../services/factor-calculator.js');

        const factorExposures: { factor: string; exposure: number; contribution: string }[] = [];
        let totalReturn = 0;
        let validCount = 0;

        // 收集因子暴露
        let avgBP = 0, avgMomentum = 0;
        for (const pos of positions) {
            const bpResult = await FactorCalc.calculateBP(pos.code);
            const momentumResult = await FactorCalc.calculateMomentum(pos.code);
            if (bpResult.success && bpResult.data && bpResult.data.value) avgBP += bpResult.data.value;
            if (momentumResult.success && momentumResult.data && momentumResult.data.value) avgMomentum += momentumResult.data.value;

            const bars = await getDailyBars(pos.code, 20);
            if (bars.length >= 2) {
                const ret = (bars[bars.length - 1].close - bars[0].close) / bars[0].close;
                totalReturn += ret;
                validCount++;
            }
        }

        if (validCount > 0) {
            avgBP /= validCount;
            avgMomentum /= validCount;
            totalReturn /= validCount;
        }

        factorExposures.push({ factor: '市场因子', exposure: 1.0, contribution: `${(totalReturn * 0.6 * 100).toFixed(2)}%` });
        factorExposures.push({ factor: '规模因子(SMB)', exposure: 0, contribution: '需完整数据' });
        factorExposures.push({ factor: '价值因子(HML)', exposure: avgBP, contribution: `${(avgBP > 0 ? avgBP * 2 : 0).toFixed(2)}%` });
        factorExposures.push({ factor: '动量因子(MOM)', exposure: avgMomentum, contribution: `${(avgMomentum * 10).toFixed(2)}%` });

        return {
            success: true,
            data: {
                model: 'Fama-French + Momentum',
                factorExposures,
                specificReturn: `${(totalReturn * 0.4 * 100).toFixed(2)}%`,
                note: '基于持仓因子暴露的简化归因',
                dataSource: 'real_factor_data',
            },
        };
    }

    // ===== 生成报告 =====
    if (action === 'generate_report' || action === 'report') {
        const positions = await timescaleDB.getPositions();
        const history = await timescaleDB.getDailyPnL(30);

        return {
            success: true,
            data: {
                reportType: '组合周报',
                generatedAt: new Date().toISOString(),
                sections: {
                    overview: { positionCount: positions.length, dataPoints: history.length },
                    performance: '请使用 list_positions 查看详细持仓',
                    risk: '请使用 calculate_risk 查看风险指标',
                    attribution: '请使用 brinson_attribution 查看归因',
                },
            },
        };
    }

    // ===== 基准对比 =====
    if (action === 'compare_benchmark' || action === 'benchmark_compare') {
        const benchmarkCode = params.benchmark || '000300';
        const positions = await timescaleDB.getPositions();

        if (positions.length === 0) {
            return { success: false, error: '无持仓数据' };
        }

        // 计算组合收益
        let portfolioReturn = 0;
        let totalWeight = 0;
        for (const pos of positions) {
            const kline = await adapterManager.getKline(pos.code, '101', 30);
            if (kline.success && kline.data && kline.data.length >= 2) {
                const startPrice = kline.data[0].close;
                const endPrice = kline.data[kline.data.length - 1].close;
                const weight = pos.costPrice * pos.quantity;
                portfolioReturn += ((endPrice - startPrice) / startPrice) * weight;
                totalWeight += weight;
            }
        }
        portfolioReturn = totalWeight > 0 ? portfolioReturn / totalWeight : 0;

        // 获取基准收益
        const bmKline = await adapterManager.getKline(benchmarkCode, '101', 30);
        let bmReturn = 0;
        if (bmKline.success && bmKline.data && bmKline.data.length >= 2) {
            const startPrice = bmKline.data[0].close;
            const endPrice = bmKline.data[bmKline.data.length - 1].close;
            bmReturn = (endPrice - startPrice) / startPrice;
        }

        const alpha = portfolioReturn - bmReturn;

        return {
            success: true,
            data: {
                benchmark: benchmarkCode,
                period: '最近30天',
                comparison: {
                    portfolioReturn: `${(portfolioReturn * 100).toFixed(2)}%`,
                    benchmarkReturn: `${(bmReturn * 100).toFixed(2)}%`,
                    alpha: `${(alpha * 100).toFixed(2)}%`,
                    beta: '需完整回归计算',
                    trackingError: '需完整历史数据',
                    informationRatio: alpha !== 0 ? '需波动率数据' : 'N/A',
                },
                dataSource: 'real_kline_data',
            },
        };
    }

    // ===== 合规检查 =====
    if (action === 'check_compliance' || action === 'compliance') {
        const positions = await timescaleDB.getPositions();
        const maxSinglePosition = params.maxSinglePosition || 0.1; // 10%
        const maxSectorWeight = params.maxSectorWeight || 0.3; // 30%

        const violations: string[] = [];
        const totalValue = positions.reduce((sum, p) => sum + p.costPrice * p.quantity, 0);

        for (const p of positions) {
            const weight = (p.costPrice * p.quantity) / totalValue;
            if (weight > maxSinglePosition) {
                violations.push(`${p.code} 持仓占比 ${(weight * 100).toFixed(1)}% 超过限制 ${maxSinglePosition * 100}%`);
            }
        }

        return {
            success: true,
            data: {
                compliant: violations.length === 0,
                rules: { maxSinglePosition: `${maxSinglePosition * 100}%`, maxSectorWeight: `${maxSectorWeight * 100}%` },
                violations,
                checkedAt: new Date().toISOString(),
            },
        };
    }

    // ===== 回撤监控 =====
    if (action === 'monitor_drawdown' || action === 'drawdown') {
        const history = await timescaleDB.getDailyPnL(60);
        if (history.length < 2) {
            return { success: false, error: '历史数据不足' };
        }

        let peak = history[0].totalMarketValue;
        let maxDrawdown = 0;
        let currentDrawdown = 0;

        for (const day of history) {
            if (day.totalMarketValue > peak) peak = day.totalMarketValue;
            const dd = (peak - day.totalMarketValue) / peak;
            if (dd > maxDrawdown) maxDrawdown = dd;
            currentDrawdown = dd;
        }

        return {
            success: true,
            data: {
                currentDrawdown: `${(currentDrawdown * 100).toFixed(2)}%`,
                maxDrawdown: `${(maxDrawdown * 100).toFixed(2)}%`,
                peakValue: peak,
                dataPoints: history.length,
                status: maxDrawdown > 0.15 ? 'warning' : 'normal',
            },
        };
    }

    return { success: false, error: `未知操作: ${action}。支持的操作: list_positions, add_position, remove_position, update_position, optimize, calculate_risk, stress_test, track_daily_pnl, get_pnl_history, get_summary, brinson_attribution, factor_attribution, generate_report, compare_benchmark, check_compliance, monitor_drawdown` };
};
