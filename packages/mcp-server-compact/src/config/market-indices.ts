/**
 * 市场指数配置
 * 提取硬编码的指数代码
 */

export interface IndexConfig {
    code: string;
    name: string;
    market: 'SH' | 'SZ' | 'BJ';
    type: 'broad' | 'sector' | 'style' | 'theme';
}

/**
 * 主要市场指数
 */
export const MAJOR_INDICES: IndexConfig[] = [
    // 宽基指数
    { code: '000001', name: '上证指数', market: 'SH', type: 'broad' },
    { code: '399001', name: '深证成指', market: 'SZ', type: 'broad' },
    { code: '399006', name: '创业板指', market: 'SZ', type: 'broad' },
    { code: '000300', name: '沪深300', market: 'SH', type: 'broad' },
    { code: '000905', name: '中证500', market: 'SH', type: 'broad' },
    { code: '000852', name: '中证1000', market: 'SH', type: 'broad' },
    { code: '000688', name: '科创50', market: 'SH', type: 'broad' },
    
    // 行业指数
    { code: '000933', name: '中证医药', market: 'SH', type: 'sector' },
    { code: '000991', name: '全指医药', market: 'SH', type: 'sector' },
    { code: '399975', name: '证券公司', market: 'SZ', type: 'sector' },
    { code: '399986', name: '中证银行', market: 'SZ', type: 'sector' },
    { code: '931087', name: '中证白酒', market: 'SH', type: 'sector' },
    { code: '000931', name: '中证可选', market: 'SH', type: 'sector' },
    { code: '000932', name: '中证消费', market: 'SH', type: 'sector' },
    { code: '399997', name: '中证白马', market: 'SZ', type: 'style' },
    
    // 科技指数
    { code: '931079', name: '半导体', market: 'SH', type: 'sector' },
    { code: '399006', name: '创业板指', market: 'SZ', type: 'broad' },
    { code: '399673', name: '创业板50', market: 'SZ', type: 'broad' },
    
    // 新能源指数
    { code: '399417', name: '国证新能', market: 'SZ', type: 'theme' },
    { code: '931151', name: '新能源车', market: 'SH', type: 'theme' },
    { code: '931068', name: '光伏产业', market: 'SH', type: 'theme' },
    
    // 风格指数
    { code: '000919', name: '300价值', market: 'SH', type: 'style' },
    { code: '000918', name: '300成长', market: 'SH', type: 'style' },
    { code: '399372', name: '大盘成长', market: 'SZ', type: 'style' },
    { code: '399373', name: '大盘价值', market: 'SZ', type: 'style' },
];

/**
 * 指数代码映射
 */
export const INDEX_CODE_MAP: Record<string, string> = {
    // 别名映射
    '上证': '000001',
    '深成': '399001',
    '创业板': '399006',
    '沪深300': '000300',
    '中证500': '000905',
    '中证1000': '000852',
    '科创50': '000688',
    
    // 行业别名
    '医药': '000933',
    '证券': '399975',
    '银行': '399986',
    '白酒': '931087',
    '消费': '000932',
    '半导体': '931079',
    '新能源': '399417',
    '新能源车': '931151',
    '光伏': '931068',
};

/**
 * 根据名称获取指数代码
 */
export function getIndexCode(nameOrCode: string): string | null {
    // 如果已经是代码，直接返回
    if (/^\d{6}$/.test(nameOrCode)) {
        return nameOrCode;
    }
    
    // 查找别名
    return INDEX_CODE_MAP[nameOrCode] || null;
}

/**
 * 根据代码获取指数信息
 */
export function getIndexInfo(code: string): IndexConfig | null {
    return MAJOR_INDICES.find(idx => idx.code === code) || null;
}

/**
 * 获取指数名称
 */
export function getIndexName(code: string): string {
    const info = getIndexInfo(code);
    return info?.name || code;
}

/**
 * 按类型获取指数列表
 */
export function getIndicesByType(type: IndexConfig['type']): IndexConfig[] {
    return MAJOR_INDICES.filter(idx => idx.type === type);
}

/**
 * 获取所有宽基指数
 */
export function getBroadIndices(): IndexConfig[] {
    return getIndicesByType('broad');
}

/**
 * 获取所有行业指数
 */
export function getSectorIndices(): IndexConfig[] {
    return getIndicesByType('sector');
}

/**
 * 添加自定义指数
 */
export function addCustomIndex(config: IndexConfig): void {
    MAJOR_INDICES.push(config);
    if (config.name) {
        INDEX_CODE_MAP[config.name] = config.code;
    }
}
