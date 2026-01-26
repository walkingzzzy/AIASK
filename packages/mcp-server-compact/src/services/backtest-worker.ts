/**
 * 回测 Worker 线程
 * 用于并行化参数优化，避免阻塞主线程
 */

import { parentPort, workerData } from 'worker_threads';
import { runBacktest } from './backtest.js';
import type { KlineData } from '../types/stock.js';

interface BacktestParams {
    initialCapital: number;
    commission: number;
    slippage: number;
    shortPeriod?: number;
    longPeriod?: number;
    lookback?: number;
    threshold?: number;
}

interface WorkerData {
    code: string;
    klines: KlineData[];
    strategy: string;
    paramCombinations: BacktestParams[];
}

interface WorkerResult {
    bestParams: BacktestParams;
    bestMetric: number;
    results: Array<{ params: BacktestParams; metric: number }>;
}

if (!parentPort) {
    throw new Error('This file must be run as a Worker thread');
}

const { code, klines, strategy, paramCombinations } = workerData as WorkerData;

try {
    let bestMetric = -Infinity;
    let bestParams: BacktestParams = paramCombinations[0];
    const results: Array<{ params: BacktestParams; metric: number }> = [];

    // 在 Worker 中运行回测
    for (const params of paramCombinations) {
        const { result } = runBacktest(code, klines, strategy, params);
        
        // 优化目标：夏普比率 * (1 - 最大回撤)
        const metric = result.sharpeRatio * (1 - result.maxDrawdown);
        
        results.push({ params, metric });
        
        if (metric > bestMetric) {
            bestMetric = metric;
            bestParams = params;
        }
    }

    const workerResult: WorkerResult = {
        bestParams,
        bestMetric,
        results,
    };

    parentPort.postMessage({ success: true, data: workerResult });
} catch (error) {
    parentPort.postMessage({ 
        success: false, 
        error: error instanceof Error ? error.message : String(error) 
    });
}
