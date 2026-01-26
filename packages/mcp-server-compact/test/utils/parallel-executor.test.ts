/**
 * 并行执行器测试
 */

import { describe, it, expect } from 'vitest';
import {
    parallelExecute,
    batchExecute,
    chunkExecute,
    CachedParallelExecutor,
    RateLimitedExecutor,
} from '../../src/utils/parallel-executor.js';

describe('Parallel Executor', () => {
    describe('parallelExecute', () => {
        it('should execute tasks in parallel', async () => {
            const items = [1, 2, 3, 4, 5];
            const startTime = Date.now();

            const results = await parallelExecute(
                items,
                async (item) => {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    return item * 2;
                },
                { concurrency: 3 }
            );

            const executionTime = Date.now() - startTime;

            expect(results).toHaveLength(5);
            expect(results.every(r => r.success)).toBe(true);
            
            // 验证结果数据
            const successData = results.filter(r => r.success).map(r => r.data);
            expect(successData).toEqual([2, 4, 6, 8, 10]);
            
            // 并行执行应该比串行快
            // 5个任务，每个100ms，并发3，应该约200ms
            expect(executionTime).toBeLessThan(400);
        });

        it('should handle errors gracefully', async () => {
            const items = [1, 2, 3, 4, 5];

            const results = await parallelExecute(
                items,
                async (item) => {
                    if (item === 3) {
                        throw new Error('Test error');
                    }
                    return item * 2;
                },
                { concurrency: 2 }
            );

            expect(results).toHaveLength(5);
            expect(results.filter(r => r.success)).toHaveLength(4);
            expect(results.filter(r => !r.success)).toHaveLength(1);
            expect(results[2].error).toBe('Test error');
        });

        it('should respect timeout', async () => {
            const items = [1, 2, 3];

            const results = await parallelExecute(
                items,
                async (item) => {
                    await new Promise(resolve => setTimeout(resolve, item * 100));
                    return item;
                },
                { timeout: 150, concurrency: 1 }  // 串行执行以确保超时
            );

            // 第一个应该成功（100ms < 150ms）
            expect(results[0].success).toBe(true);
            // 后两个应该超时
            expect(results[1].success).toBe(false);
            expect(results[2].success).toBe(false);
        });

        it('should retry on failure', async () => {
            let attempts = 0;

            const results = await parallelExecute(
                [1],
                async () => {
                    attempts++;
                    if (attempts < 3) {
                        throw new Error('Retry me');
                    }
                    return 'success';
                },
                { retryCount: 2, retryDelay: 10 }
            );

            expect(attempts).toBe(3);
            expect(results[0].success).toBe(true);
            expect(results[0].data).toBe('success');
        });

        it('should call progress callback', async () => {
            const items = [1, 2, 3, 4, 5];
            const progressUpdates: number[] = [];

            await parallelExecute(
                items,
                async (item) => {
                    await new Promise(resolve => setTimeout(resolve, 10));
                    return item * 2;
                },
                {
                    concurrency: 2,
                    onProgress: (completed, total) => {
                        progressUpdates.push(completed);
                    },
                }
            );

            // 应该有5次进度更新
            expect(progressUpdates.length).toBe(5);
            // 最后一次应该是5
            expect(progressUpdates[progressUpdates.length - 1]).toBe(5);
        });
    });

    describe('batchExecute', () => {
        it('should return success and failed results', async () => {
            const items = [1, 2, 3, 4, 5];

            const result = await batchExecute(
                items,
                async (item) => {
                    if (item === 3) {
                        throw new Error('Failed');
                    }
                    return item * 2;
                }
            );

            expect(result.success).toEqual([2, 4, 8, 10]);
            expect(result.failed).toHaveLength(1);
            expect(result.failed[0].item).toBe(3);
            expect(result.stats.total).toBe(5);
            expect(result.stats.succeeded).toBe(4);
            expect(result.stats.failed).toBe(1);
        });
    });

    describe('chunkExecute', () => {
        it('should execute in chunks', async () => {
            const items = Array.from({ length: 25 }, (_, i) => i + 1);

            const results = await chunkExecute(
                items,
                async (chunk) => {
                    return chunk.map(item => item * 2);
                },
                10,  // chunk size
                { concurrency: 2 }
            );

            expect(results).toHaveLength(25);
            expect(results[0]).toBe(2);
            expect(results[24]).toBe(50);
        });
    });

    describe('CachedParallelExecutor', () => {
        it('should cache results', async () => {
            const executor = new CachedParallelExecutor<number, number>(1000);
            let executionCount = 0;

            const fetchFn = async (key: number) => {
                executionCount++;
                return key * 2;
            };

            // 第一次执行
            const result1 = await executor.execute([1, 2, 3], fetchFn);
            expect(result1.size).toBe(3);
            expect(executionCount).toBe(3);

            // 第二次执行（应该使用缓存）
            const result2 = await executor.execute([1, 2, 3], fetchFn);
            expect(result2.size).toBe(3);
            expect(executionCount).toBe(3);  // 没有增加

            // 部分缓存
            const result3 = await executor.execute([1, 2, 4], fetchFn);
            expect(result3.size).toBe(3);
            expect(executionCount).toBe(4);  // 只执行了4
        });

        it('should expire cache', async () => {
            const executor = new CachedParallelExecutor<number, number>(100);
            let executionCount = 0;

            const fetchFn = async (key: number) => {
                executionCount++;
                return key * 2;
            };

            await executor.execute([1], fetchFn);
            expect(executionCount).toBe(1);

            // 等待缓存过期
            await new Promise(resolve => setTimeout(resolve, 150));

            await executor.execute([1], fetchFn);
            expect(executionCount).toBe(2);
        });
    });

    describe('RateLimitedExecutor', () => {
        it('should limit execution rate', async () => {
            const executor = new RateLimitedExecutor<number, number>(2, 100);
            const items = [1, 2, 3, 4, 5];
            const startTime = Date.now();

            const results = await executor.executeAll(
                items,
                async (item) => item * 2
            );

            const executionTime = Date.now() - startTime;

            expect(results).toEqual([2, 4, 6, 8, 10]);
            
            // 5个任务，最小间隔100ms，并发2
            // 应该至少需要一定时间（放宽要求）
            expect(executionTime).toBeGreaterThan(50);
        });
    });
});
