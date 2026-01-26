/**
 * 统一错误处理工具
 * 提供标准化的错误处理和日志记录
 */

import { logger } from '../logger.js';

export interface ErrorContext {
    operation: string;
    code?: string;
    params?: Record<string, unknown>;
}

export interface HandledError {
    success: false;
    error: string;
    degraded?: boolean;
    context?: ErrorContext;
}

/**
 * 安全地执行异步操作，捕获并处理错误
 */
export async function safeExecute<T>(
    operation: () => Promise<T>,
    context: ErrorContext
): Promise<T | HandledError> {
    try {
        return await operation();
    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        
        logger.error(`Error in ${context.operation}`, {
            error: errorMessage,
            code: context.code,
            params: context.params,
        });

        return {
            success: false,
            error: errorMessage,
            degraded: true,
            context,
        };
    }
}

/**
 * 批量执行操作，收集成功和失败结果
 */
export async function batchExecute<T, R>(
    items: T[],
    operation: (item: T) => Promise<R>,
    context: ErrorContext
): Promise<{
    success: R[];
    failed: Array<{ item: T; error: string }>;
}> {
    const success: R[] = [];
    const failed: Array<{ item: T; error: string }> = [];

    for (const item of items) {
        try {
            const result = await operation(item);
            success.push(result);
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            failed.push({ item, error: errorMessage });
            
            logger.warn(`Failed to process item in ${context.operation}`, {
                item,
                error: errorMessage,
            });
        }
    }

    return { success, failed };
}

/**
 * 重试执行操作
 */
export async function retryExecute<T>(
    operation: () => Promise<T>,
    context: ErrorContext,
    maxRetries: number = 3,
    delayMs: number = 1000
): Promise<T | HandledError> {
    let lastError: Error | unknown;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            return await operation();
        } catch (error) {
            lastError = error;
            
            if (attempt < maxRetries) {
                logger.warn(`Retry ${attempt + 1}/${maxRetries} for ${context.operation}`, {
                    error: error instanceof Error ? error.message : String(error),
                });
                
                await new Promise(resolve => setTimeout(resolve, delayMs * (attempt + 1)));
            }
        }
    }

    const errorMessage = lastError instanceof Error ? lastError.message : String(lastError);
    
    logger.error(`Failed after ${maxRetries} retries: ${context.operation}`, {
        error: errorMessage,
        context,
    });

    return {
        success: false,
        error: `Failed after ${maxRetries} retries: ${errorMessage}`,
        degraded: true,
        context,
    };
}

/**
 * 验证必需参数
 */
export function validateRequired<T extends Record<string, unknown>>(
    params: T,
    required: (keyof T)[]
): { valid: true } | { valid: false; missing: string[] } {
    const missing = required.filter(key => {
        const value = params[key];
        return value === undefined || value === null || value === '';
    });

    if (missing.length > 0) {
        return { valid: false, missing: missing.map(String) };
    }

    return { valid: true };
}

/**
 * 创建标准化的错误响应
 */
export function createErrorResponse(
    error: unknown,
    context?: ErrorContext
): HandledError {
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    return {
        success: false,
        error: errorMessage,
        degraded: true,
        context,
    };
}

/**
 * 检查是否为网络错误
 */
export function isNetworkError(error: unknown): boolean {
    const message = error instanceof Error ? error.message : String(error);
    const networkPatterns = [
        /ECONNREFUSED/i,
        /ECONNRESET/i,
        /ETIMEDOUT/i,
        /ENOTFOUND/i,
        /socket hang up/i,
        /network error/i,
        /timeout/i,
    ];
    
    return networkPatterns.some(pattern => pattern.test(message));
}

/**
 * 检查是否为限流错误
 */
export function isRateLimitError(error: unknown): boolean {
    const message = error instanceof Error ? error.message : String(error);
    const rateLimitPatterns = [
        /429/i,
        /rate limit/i,
        /too many requests/i,
    ];
    
    return rateLimitPatterns.some(pattern => pattern.test(message));
}

/**
 * 获取友好的错误消息
 */
export function getFriendlyErrorMessage(error: unknown): string {
    if (isNetworkError(error)) {
        return '网络连接失败，请检查网络设置或稍后重试';
    }
    
    if (isRateLimitError(error)) {
        return '请求过于频繁，请稍后再试';
    }
    
    const message = error instanceof Error ? error.message : String(error);
    return message || '操作失败，请稍后重试';
}
