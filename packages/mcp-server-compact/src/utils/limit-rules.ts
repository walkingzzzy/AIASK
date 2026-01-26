/**
 * 涨跌停规则模块
 * 
 * 解决 P0-5 问题：涨跌停阈值硬编码不适配 ST/20cm/北交所等
 */

/**
 * 股票板块类型
 */
export type BoardType = 'main' | 'star' | 'gem' | 'bse' | 'unknown';

/**
 * 根据股票代码判断板块类型
 */
export function getBoardType(code: string): BoardType {
    if (!code || code.length < 6) return 'unknown';

    const prefix = code.substring(0, 3);
    const prefix2 = code.substring(0, 2);

    // 科创板: 688xxx
    if (prefix === '688') return 'star';

    // 创业板: 30xxxx
    if (prefix2 === '30') return 'gem';

    // 北交所: 8xxxxx, 4xxxxx (新三板精选层转板)
    if (prefix2 === '83' || prefix2 === '87' || prefix2 === '43') return 'bse';

    // 主板: 60xxxx (上证), 00xxxx (深证)
    if (prefix2 === '60' || prefix2 === '00') return 'main';

    return 'unknown';
}

/**
 * 判断是否为 ST 股票
 */
export function checkIsST(stockName?: string): boolean {
    if (!stockName) return false;
    return stockName.includes('ST') || stockName.includes('*ST');
}

/**
 * 获取涨跌停阈值（百分比）
 */
export function getLimitThreshold(
    code: string,
    isST: boolean = false,
    isFirstDay: boolean = false
): number | null {
    // 上市首日不设涨跌停
    if (isFirstDay) return null;

    // ST 股票固定 5%
    if (isST) return 5;

    const board = getBoardType(code);

    switch (board) {
        case 'star':  // 科创板
        case 'gem':   // 创业板
            return 20;
        case 'bse':   // 北交所
            return 30;
        case 'main':  // 主板
        default:
            return 10;
    }
}

/**
 * 判断是否涨停
 */
export function isLimitUp(
    code: string,
    changePercent: number,
    isST: boolean = false,
    tolerance: number = 0.1
): boolean {
    const threshold = getLimitThreshold(code, isST);
    if (threshold === null) return false; // 无涨跌停限制

    return changePercent >= threshold - tolerance;
}

/**
 * 判断是否跌停
 */
export function isLimitDown(
    code: string,
    changePercent: number,
    isST: boolean = false,
    tolerance: number = 0.1
): boolean {
    const threshold = getLimitThreshold(code, isST);
    if (threshold === null) return false;

    return changePercent <= -(threshold - tolerance);
}

/**
 * 计算涨停价
 */
export function getLimitUpPrice(
    preClose: number,
    code: string,
    isST: boolean = false
): number | null {
    const threshold = getLimitThreshold(code, isST);
    if (threshold === null) return null;

    return Math.round(preClose * (1 + threshold / 100) * 100) / 100;
}

/**
 * 计算跌停价
 */
export function getLimitDownPrice(
    preClose: number,
    code: string,
    isST: boolean = false
): number | null {
    const threshold = getLimitThreshold(code, isST);
    if (threshold === null) return null;

    return Math.round(preClose * (1 - threshold / 100) * 100) / 100;
}

/**
 * 判断是否接近涨停
 */
export function isNearLimitUp(
    code: string,
    changePercent: number,
    isST: boolean = false,
    nearThreshold: number = 2
): boolean {
    const threshold = getLimitThreshold(code, isST);
    if (threshold === null) return false;

    return changePercent >= threshold - nearThreshold && changePercent < threshold - 0.1;
}

/**
 * 判断是否接近跌停
 */
export function isNearLimitDown(
    code: string,
    changePercent: number,
    isST: boolean = false,
    nearThreshold: number = 2
): boolean {
    const threshold = getLimitThreshold(code, isST);
    if (threshold === null) return false;

    return changePercent <= -(threshold - nearThreshold) && changePercent > -(threshold - 0.1);
}
