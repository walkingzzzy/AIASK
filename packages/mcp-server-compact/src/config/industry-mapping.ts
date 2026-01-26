/**
 * 行业分类配置
 * 将硬编码的行业映射提取到配置文件
 */

export interface IndustryConfig {
    code: string;
    name: string;
    sector: string;
    subsector?: string;
}

/**
 * 股票代码到行业的映射
 */
export const INDUSTRY_MAPPING: Record<string, string> = {
    // 银行
    '601398': '金融',
    '601939': '金融',
    '601288': '金融',
    '600036': '金融',
    '601328': '金融',
    '600000': '金融',
    '601166': '金融',
    '600016': '金融',
    
    // 证券
    '600030': '金融',
    '601688': '金融',
    '600999': '金融',
    '000166': '金融',
    
    // 保险
    '601318': '金融',
    '601601': '金融',
    '601336': '金融',
    
    // 白酒
    '600519': '消费',
    '000858': '消费',
    '000568': '消费',
    '000799': '消费',
    '600809': '消费',
    
    // 食品饮料
    '600887': '消费',
    '000895': '消费',
    '603288': '消费',
    
    // 医药
    '600276': '医药',
    '000538': '医药',
    '600196': '医药',
    '300015': '医药',
    '002821': '医药',
    '603259': '医药',
    
    // 半导体
    '002415': '科技',
    '688981': '科技',
    '603501': '科技',
    '688008': '科技',
    
    // 软件
    '000725': '科技',
    '002371': '科技',
    '600588': '科技',
    '300033': '科技',
    
    // 新能源汽车
    '300750': '新能源',
    '002594': '新能源',
    '002920': '新能源',
    
    // 光伏
    '601012': '新能源',
    '688599': '新能源',
    '300274': '新能源',
    
    // 电池
    '300014': '新能源',
    '002460': '新能源',
    
    // 房地产
    '000002': '地产',
    '600048': '地产',
    '001979': '地产',
    
    // 建筑
    '601668': '基建',
    '601186': '基建',
    '601800': '基建',
    
    // 钢铁
    '600019': '周期',
    '000709': '周期',
    '600010': '周期',
    
    // 煤炭
    '601088': '周期',
    '601225': '周期',
    '600188': '周期',
    
    // 有色金属
    '600547': '周期',
    '601899': '周期',
    '600362': '周期',
};

/**
 * 行业分类层级
 */
export const SECTOR_HIERARCHY: Record<string, { name: string; subsectors: string[] }> = {
    '金融': {
        name: '金融',
        subsectors: ['银行', '证券', '保险', '多元金融']
    },
    '消费': {
        name: '消费',
        subsectors: ['白酒', '食品饮料', '家电', '纺织服装', '商贸零售']
    },
    '医药': {
        name: '医药',
        subsectors: ['化学制药', '生物制药', '医疗器械', '医疗服务', '中药']
    },
    '科技': {
        name: '科技',
        subsectors: ['半导体', '软件', '通信设备', '电子元件', '计算机']
    },
    '新能源': {
        name: '新能源',
        subsectors: ['新能源汽车', '光伏', '风电', '电池', '储能']
    },
    '地产': {
        name: '地产',
        subsectors: ['房地产开发', '物业管理', '园区开发']
    },
    '基建': {
        name: '基建',
        subsectors: ['建筑装饰', '工程建设', '基础建设']
    },
    '周期': {
        name: '周期',
        subsectors: ['钢铁', '煤炭', '有色金属', '化工', '建材']
    },
};

/**
 * 根据股票代码获取行业
 */
export function getIndustry(code: string): string {
    // 优先使用映射表
    if (INDUSTRY_MAPPING[code]) {
        return INDUSTRY_MAPPING[code];
    }

    // 根据代码规则推断
    if (code.startsWith('688')) return '科技'; // 科创板
    if (code.startsWith('300')) return '科技'; // 创业板
    if (code.startsWith('601') || code.startsWith('600')) return '金融'; // 上交所主板
    if (code.startsWith('000') || code.startsWith('001')) return '消费'; // 深交所主板
    if (code.startsWith('002')) return '制造'; // 中小板
    
    return '其他';
}

/**
 * 获取行业列表
 */
export function getAllSectors(): string[] {
    return Object.keys(SECTOR_HIERARCHY);
}

/**
 * 获取行业的子行业
 */
export function getSubsectors(sector: string): string[] {
    return SECTOR_HIERARCHY[sector]?.subsectors || [];
}

/**
 * 添加自定义行业映射
 */
export function addIndustryMapping(code: string, industry: string): void {
    INDUSTRY_MAPPING[code] = industry;
}

/**
 * 批量添加行业映射
 */
export function addIndustryMappings(mappings: Record<string, string>): void {
    Object.assign(INDUSTRY_MAPPING, mappings);
}
