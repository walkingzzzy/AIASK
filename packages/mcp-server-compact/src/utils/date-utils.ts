/**
 * 日期时区工具函数
 * 
 * 解决 P0-4 问题：UTC 日期默认值导致中国市场交易日错位
 */

/**
 * 获取上海时区的今天日期 (YYYY-MM-DD)
 * 替代 new Date().toISOString().split('T')[0]
 */
export function getTodayInShanghai(): string {
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).format(new Date());
}

/**
 * 格式化日期为上海时区 (YYYY-MM-DD)
 */
export function formatDateShanghai(date: Date): string {
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).format(date);
}

/**
 * 获取上海时区的当前时间戳
 */
export function getNowInShanghai(): Date {
    return new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));
}

/**
 * 判断是否为交易日（基础版：排除周末）
 * 
 * 注意：完整实现需要集成节假日数据
 */
export function isTradeDay(date: Date | string): boolean {
    const d = typeof date === 'string' ? new Date(date) : date;
    const dayOfWeek = d.getDay();
    // 周六(6)和周日(0)不是交易日
    return dayOfWeek !== 0 && dayOfWeek !== 6;
}

/**
 * 获取最近的交易日（如果今天不是交易日则回溯）
 */
export function getLatestTradeDay(date?: Date | string): string {
    let d = date ? (typeof date === 'string' ? new Date(date) : date) : new Date();

    // 转换到上海时区
    d = new Date(d.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }));

    // 最多回溯7天
    for (let i = 0; i < 7; i++) {
        if (isTradeDay(d)) {
            return formatDateShanghai(d);
        }
        d.setDate(d.getDate() - 1);
    }

    return formatDateShanghai(d);
}

/**
 * 解析日期字符串，返回 Date 对象（上海时区）
 */
export function parseDateShanghai(dateStr: string): Date {
    // 处理 YYYY-MM-DD 格式
    const [year, month, day] = dateStr.split('-').map(Number);
    const d = new Date(year, month - 1, day);
    return d;
}

/**
 * 获取 N 天前的日期
 */
export function getDaysAgo(days: number): string {
    const d = new Date();
    d.setDate(d.getDate() - days);
    return formatDateShanghai(d);
}
