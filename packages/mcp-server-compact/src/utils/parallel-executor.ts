/**
 * 并行执行器
 * 提供批量操作的并行化支持
 */

export interface ParallelOptions {
    concurrency?: number;      // 并发数，默认5
    timeout?: number;          // 超时时间（毫秒），默认30000
    retryCount?: number;       // 重试次数，默认0
    retryDelay?: number;       // 重试延迟（毫秒），默认1000
    onProgress?: (completed: number, total: number) => void;  // 进度回调
}

export interface ParallelResult<T> {
    success: boolean;
    data?: T;
    error?: string;
    executionTime: number;
}

/**
 * 并行执行多个异步任务
 */
export async function parallelExecute<T, R>(
    items: T[],
    executor: (item: T) => Promise<R>,
    options: ParallelOptions = {}
): Promise<ParallelResult<R>[]> {
    const {
        concurrency = 5,
        timeout = 30000,
        retryCount = 0,
        retryDelay = 1000,
        onProgress,
    } = options;

    const results: ParallelResult<R>[] = new Array(items.length);
    let completed = 0;
    let currentIndex = 0;

    // 执行单个任务的函数
    const executeTask = async (item: T, index: number): Promise<void> => {
        const startTime = Date.now();
        let lastError: Error | null = null;

        // 重试逻辑
        for (let attempt = 0; attempt <= retryCount; attempt++) {
            try {
                // 超时控制
                const result = await Promise.race([
                    executor(item),
                    new Promise<never>((_, reject) =>
                        setTimeout(() => reject(new Error('Timeout')), timeout)
                    ),
                ]);

                const executionTime = Date.now() - startTime;
                results[index] = {
                    success: true,
                    data: result,
                    executionTime,
                };
                break;
            } catch (error) {
                lastError = error instanceof Error ? error : new Error(String(error));

                // 如果还有重试机会，等待后重试
                if (attempt < retryCount) {
                    await new Promise(resolve => setTimeout(resolve, retryDelay));
                }
            }
        }

        // 所有重试都失败
        if (!results[index]) {
            const executionTime = Date.now() - startTime;
            results[index] = {
                success: false,
                error: lastError?.message || 'Unknown error',
                executionTime,
            };
        }

        completed++;
        if (onProgress) {
            onProgress(completed, items.length);
        }
    };

    // 工作池：启动并发任务
    const workers: Promise<void>[] = [];
    
    const startWorker = async (): Promise<void> => {
        while (currentIndex < items.length) {
            const index = currentIndex++;
            await executeTask(items[index], index);
        }
    };

    // 启动指定数量的并发工作线程
    for (let i = 0; i < Math.min(concurrency, items.length); i++) {
        workers.push(startWorker());
    }

    // 等待所有工作线程完成
    await Promise.all(workers);

    return results;
}

/**
 * 批量执行并返回成功的结果
 */
export async function batchExecute<T, R>(
    items: T[],
    executor: (item: T) => Promise<R>,
    options: ParallelOptions = {}
): Promise<{
    success: R[];
    failed: Array<{ item: T; error: string }>;
    stats: {
        total: number;
        succeeded: number;
        failed: number;
        avgExecutionTime: number;
    };
}> {
    const results = await parallelExecute(items, executor, options);

    const success: R[] = [];
    const failed: Array<{ item: T; error: string }> = [];
    let totalExecutionTime = 0;

    results.forEach((result, index) => {
        totalExecutionTime += result.executionTime;

        if (result.success && result.data !== undefined) {
            success.push(result.data);
        } else {
            failed.push({
                item: items[index],
                error: result.error || 'Unknown error',
            });
        }
    });

    return {
        success,
        failed,
        stats: {
            total: items.length,
            succeeded: success.length,
            failed: failed.length,
            avgExecutionTime: totalExecutionTime / items.length,
        },
    };
}

/**
 * 分块执行（适用于大批量数据）
 */
export async function chunkExecute<T, R>(
    items: T[],
    executor: (chunk: T[]) => Promise<R[]>,
    chunkSize: number = 10,
    options: ParallelOptions = {}
): Promise<R[]> {
    const chunks: T[][] = [];

    // 分块
    for (let i = 0; i < items.length; i += chunkSize) {
        chunks.push(items.slice(i, i + chunkSize));
    }

    // 并行执行每个块
    const results = await parallelExecute(chunks, executor, options);

    // 合并结果
    const allResults: R[] = [];
    results.forEach((result: any) => {
        if (result.success && result.data) {
            allResults.push(...result.data);
        }
    });

    return allResults;
}

/**
 * 带缓存的并行执行
 */
export class CachedParallelExecutor<K, V> {
    private cache: Map<string, { data: V; timestamp: number }> = new Map();
    private ttl: number;

    constructor(ttl: number = 60000) {
        this.ttl = ttl;
    }

    async execute(
        keys: K[],
        executor: (key: K) => Promise<V>,
        options: ParallelOptions = {}
    ): Promise<Map<K, V>> {
        const now = Date.now();
        const results = new Map<K, V>();
        const keysToFetch: K[] = [];

        // 检查缓存
        keys.forEach((key: any) => {
            const cacheKey = JSON.stringify(key);
            const cached = this.cache.get(cacheKey);

            if (cached && now - cached.timestamp < this.ttl) {
                results.set(key, cached.data);
            } else {
                keysToFetch.push(key);
            }
        });

        // 并行获取未缓存的数据
        if (keysToFetch.length > 0) {
            const fetchResults = await parallelExecute(keysToFetch, executor, options);

            fetchResults.forEach((result, index) => {
                if (result.success && result.data !== undefined) {
                    const key = keysToFetch[index];
                    const cacheKey = JSON.stringify(key);

                    results.set(key, result.data);
                    this.cache.set(cacheKey, {
                        data: result.data,
                        timestamp: now,
                    });
                }
            });
        }

        return results;
    }

    clear(): void {
        this.cache.clear();
    }

    clearExpired(): void {
        const now = Date.now();
        for (const [key, value] of this.cache.entries()) {
            if (now - value.timestamp >= this.ttl) {
                this.cache.delete(key);
            }
        }
    }
}

/**
 * 限流执行器（防止API限流）
 */
export class RateLimitedExecutor<T, R> {
    private queue: Array<{
        item: T;
        resolve: (value: R) => void;
        reject: (error: Error) => void;
    }> = [];
    private executing = 0;
    private lastExecutionTime = 0;

    constructor(
        private maxConcurrency: number = 5,
        private minInterval: number = 200  // 最小间隔（毫秒）
    ) {}

    async execute(item: T, executor: (item: T) => Promise<R>): Promise<R> {
        return new Promise((resolve, reject) => {
            this.queue.push({ item, resolve, reject });
            this.processQueue(executor);
        });
    }

    private async processQueue(executor: (item: T) => Promise<R>): Promise<void> {
        if (this.executing >= this.maxConcurrency || this.queue.length === 0) {
            return;
        }

        // 限流控制
        const now = Date.now();
        const timeSinceLastExecution = now - this.lastExecutionTime;
        if (timeSinceLastExecution < this.minInterval) {
            await new Promise(resolve =>
                setTimeout(resolve, this.minInterval - timeSinceLastExecution)
            );
        }

        const task = this.queue.shift();
        if (!task) return;

        this.executing++;
        this.lastExecutionTime = Date.now();

        try {
            const result = await executor(task.item);
            task.resolve(result);
        } catch (error) {
            task.reject(error instanceof Error ? error : new Error(String(error)));
        } finally {
            this.executing--;
            this.processQueue(executor);
        }
    }

    async executeAll(
        items: T[],
        executor: (item: T) => Promise<R>
    ): Promise<R[]> {
        return Promise.all(items.map(item => this.execute(item, executor)));
    }
}
