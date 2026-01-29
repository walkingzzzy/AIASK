/**
 * 自然语言查询解析服务
 * 将自然语言选股查询解析为结构化条件
 */

// 查询条件类型
export interface QueryCondition {
    category: 'technical' | 'fundamental' | 'fund_flow' | 'sentiment' | 'market';
    field: string;
    operator: '>' | '<' | '=' | '>=' | '<=' | 'between' | 'in' | 'contains';
    value: number | string | boolean | [number, number] | string[];
    confidence: number;  // 解析置信度 0-1
}

// 解析结果
export interface ParsedQuery {
    originalQuery: string;
    conditions: QueryCondition[];
    logic: 'and' | 'or';
    sortBy?: { field: string; order: 'asc' | 'desc' };
    limit?: number;
    explanation: string[];  // 解析过程说明
    confidence: number;  // 整体置信度
}

// 关键词映射表
const KEYWORD_MAPPINGS: Record<string, { category: QueryCondition['category']; field: string; defaultOperator: QueryCondition['operator'] }> = {
    // 估值指标
    '市盈率': { category: 'fundamental', field: 'pe', defaultOperator: '<' },
    'pe': { category: 'fundamental', field: 'pe', defaultOperator: '<' },
    '市净率': { category: 'fundamental', field: 'pb', defaultOperator: '<' },
    'pb': { category: 'fundamental', field: 'pb', defaultOperator: '<' },
    '市销率': { category: 'fundamental', field: 'ps', defaultOperator: '<' },
    'ps': { category: 'fundamental', field: 'ps', defaultOperator: '<' },

    // 盈利指标
    'roe': { category: 'fundamental', field: 'roe', defaultOperator: '>' },
    '净资产收益率': { category: 'fundamental', field: 'roe', defaultOperator: '>' },
    'roa': { category: 'fundamental', field: 'roa', defaultOperator: '>' },
    '毛利率': { category: 'fundamental', field: 'gross_margin', defaultOperator: '>' },
    '净利率': { category: 'fundamental', field: 'net_margin', defaultOperator: '>' },

    // 成长指标
    '营收增长': { category: 'fundamental', field: 'revenue_growth', defaultOperator: '>' },
    '收入增长': { category: 'fundamental', field: 'revenue_growth', defaultOperator: '>' },
    '净利润增长': { category: 'fundamental', field: 'profit_growth', defaultOperator: '>' },
    '利润增长': { category: 'fundamental', field: 'profit_growth', defaultOperator: '>' },

    // 股息
    '股息率': { category: 'fundamental', field: 'dividend_yield', defaultOperator: '>' },
    '股息': { category: 'fundamental', field: 'dividend_yield', defaultOperator: '>' },
    '分红': { category: 'fundamental', field: 'dividend_yield', defaultOperator: '>' },
    '高股息': { category: 'fundamental', field: 'dividend_yield', defaultOperator: '>' },

    // 技术指标
    'macd': { category: 'technical', field: 'macd', defaultOperator: '=' },
    '金叉': { category: 'technical', field: 'macd_cross', defaultOperator: '=' },
    '死叉': { category: 'technical', field: 'macd_cross', defaultOperator: '=' },
    'kdj': { category: 'technical', field: 'kdj', defaultOperator: '=' },
    'rsi': { category: 'technical', field: 'rsi', defaultOperator: 'between' },
    '均线': { category: 'technical', field: 'ma', defaultOperator: '=' },
    '突破': { category: 'technical', field: 'breakout', defaultOperator: '=' },
    '站上': { category: 'technical', field: 'above_ma', defaultOperator: '=' },
    '跌破': { category: 'technical', field: 'below_ma', defaultOperator: '=' },

    // 涨跌幅
    '涨幅': { category: 'market', field: 'change_pct', defaultOperator: '>' },
    '跌幅': { category: 'market', field: 'change_pct', defaultOperator: '<' },
    '涨停': { category: 'market', field: 'limit_up', defaultOperator: '=' },
    '跌停': { category: 'market', field: 'limit_down', defaultOperator: '=' },
    '连板': { category: 'market', field: 'continuous_limit', defaultOperator: '>=' },

    // 成交量
    '换手率': { category: 'market', field: 'turnover_rate', defaultOperator: '>' },
    '成交额': { category: 'market', field: 'amount', defaultOperator: '>' },
    '成交量': { category: 'market', field: 'volume', defaultOperator: '>' },
    '放量': { category: 'market', field: 'volume_ratio', defaultOperator: '>' },
    '缩量': { category: 'market', field: 'volume_ratio', defaultOperator: '<' },
    '量比': { category: 'market', field: 'volume_ratio', defaultOperator: '>' },

    // 资金流向
    '主力': { category: 'fund_flow', field: 'main_force', defaultOperator: '>' },
    '主力流入': { category: 'fund_flow', field: 'main_inflow', defaultOperator: '>' },
    '主力流出': { category: 'fund_flow', field: 'main_outflow', defaultOperator: '>' },
    '北向': { category: 'fund_flow', field: 'north_fund', defaultOperator: '>' },
    '北向资金': { category: 'fund_flow', field: 'north_fund', defaultOperator: '>' },
    '外资': { category: 'fund_flow', field: 'north_fund', defaultOperator: '>' },
    '净流入': { category: 'fund_flow', field: 'net_inflow', defaultOperator: '>' },
    '净流出': { category: 'fund_flow', field: 'net_outflow', defaultOperator: '>' },

    // 市值
    '市值': { category: 'fundamental', field: 'market_cap', defaultOperator: 'between' },
    '大盘股': { category: 'fundamental', field: 'market_cap', defaultOperator: '>' },
    '中盘股': { category: 'fundamental', field: 'market_cap', defaultOperator: 'between' },
    '小盘股': { category: 'fundamental', field: 'market_cap', defaultOperator: '<' },

    // 情绪
    '情绪': { category: 'sentiment', field: 'sentiment_score', defaultOperator: '>' },
    '热度': { category: 'sentiment', field: 'heat_score', defaultOperator: '>' },
    '关注度': { category: 'sentiment', field: 'attention_score', defaultOperator: '>' },
};

// 行业/板块关键词
const SECTOR_KEYWORDS: Record<string, string[]> = {
    '银行': ['银行', '金融'],
    '券商': ['券商', '证券'],
    '保险': ['保险'],
    '房地产': ['房地产', '地产'],
    '医药': ['医药', '医疗', '生物', '制药'],
    '白酒': ['白酒', '酒'],
    '消费': ['消费', '食品', '饮料', '家电'],
    '科技': ['科技', '互联网', '软件', '计算机'],
    '半导体': ['半导体', '芯片', '集成电路'],
    '新能源': ['新能源', '光伏', '风电', '储能'],
    '汽车': ['汽车', '新能源车', '电动车'],
    '军工': ['军工', '国防', '航空航天'],
    '钢铁': ['钢铁'],
    '煤炭': ['煤炭'],
    '有色': ['有色', '有色金属'],
    '化工': ['化工'],
    '建材': ['建材', '水泥'],
    '电力': ['电力', '电网'],
    '通信': ['通信', '5G'],
    'AI': ['AI', '人工智能', '大模型'],
};

// 数值修饰词
const VALUE_MODIFIERS: Record<string, { operator: QueryCondition['operator']; multiplier?: number }> = {
    '低于': { operator: '<' },
    '小于': { operator: '<' },
    '不超过': { operator: '<=' },
    '高于': { operator: '>' },
    '大于': { operator: '>' },
    '超过': { operator: '>' },
    '不低于': { operator: '>=' },
    '至少': { operator: '>=' },
    '等于': { operator: '=' },
    '约': { operator: '=' },
    '左右': { operator: '=' },
};

/**
 * NLP查询解析器
 */
export class NLPQueryParser {
    /**
     * 解析自然语言查询
     */
    parseQuery(query: string): ParsedQuery {
        const conditions: QueryCondition[] = [];
        const explanations: string[] = [];
        let overallConfidence = 1.0;

        // 标准化查询
        const normalizedQuery = this.normalizeQuery(query);
        explanations.push(`标准化查询: "${normalizedQuery}"`);

        // 1. 提取行业/板块条件
        const sectorCondition = this.extractSectorCondition(normalizedQuery);
        if (sectorCondition) {
            conditions.push(sectorCondition);
            explanations.push(`识别行业: ${sectorCondition.value}`);
        }

        // 2. 提取数值条件
        const numericConditions = this.extractNumericConditions(normalizedQuery);
        conditions.push(...numericConditions);
        numericConditions.forEach((c: any) => {
            explanations.push(`识别条件: ${c.field} ${c.operator} ${c.value}`);
        });

        // 3. 提取布尔条件（排除ST/科创/创业）
        const booleanConditions = this.extractBooleanConditions(normalizedQuery);
        conditions.push(...booleanConditions);
        booleanConditions.forEach((c: any) => {
            explanations.push(`识别条件: ${c.field} = ${String(c.value)}`);
        });

        // 4. 提取技术指标条件
        const technicalConditions = this.extractTechnicalConditions(normalizedQuery);
        conditions.push(...technicalConditions);
        technicalConditions.forEach((c: any) => {
            explanations.push(`识别技术条件: ${c.field} = ${c.value}`);
        });

        // 5. 提取资金流向条件
        const fundFlowConditions = this.extractFundFlowConditions(normalizedQuery);
        conditions.push(...fundFlowConditions);
        fundFlowConditions.forEach((c: any) => {
            explanations.push(`识别资金条件: ${c.field} ${c.operator} ${c.value}`);
        });

        // 6. 提取特殊条件（涨停、连板等）
        const specialConditions = this.extractSpecialConditions(normalizedQuery);
        conditions.push(...specialConditions);
        specialConditions.forEach((c: any) => {
            explanations.push(`识别特殊条件: ${c.field} = ${c.value}`);
        });

        // 7. 确定排序方式
        const sortBy = this.extractSortBy(normalizedQuery);
        if (sortBy) {
            explanations.push(`排序方式: ${sortBy.field} ${sortBy.order}`);
        }

        // 8. 确定逻辑关系
        const logic = this.determineLogic(normalizedQuery);
        explanations.push(`条件逻辑: ${logic === 'and' ? '且' : '或'}`);

        // 计算整体置信度
        if (conditions.length > 0) {
            overallConfidence = conditions.reduce((sum, c) => sum + c.confidence, 0) / conditions.length;
        } else {
            overallConfidence = 0.3;
            explanations.push('警告: 未能识别有效条件，建议使用更具体的描述');
        }

        return {
            originalQuery: query,
            conditions,
            logic,
            sortBy,
            limit: this.extractLimit(normalizedQuery),
            explanation: explanations,
            confidence: Math.round(overallConfidence * 100) / 100,
        };
    }

    /**
     * 标准化查询
     */
    private normalizeQuery(query: string): string {
        return query
            .toLowerCase()
            .replace(/\s+/g, '')
            .replace(/％/g, '%')
            .replace(/，/g, ',')
            .replace(/。/g, '')
            .replace(/的/g, '')
            .replace(/股票/g, '')
            .replace(/个股/g, '');
    }

    /**
     * 提取行业/板块条件
     */
    private extractSectorCondition(query: string): QueryCondition | null {
        for (const [sector, keywords] of Object.entries(SECTOR_KEYWORDS)) {
            for (const keyword of keywords) {
                if (query.includes(keyword)) {
                    return {
                        category: 'fundamental',
                        field: 'sector',
                        operator: 'in',
                        value: [sector],
                        confidence: 0.95,
                    };
                }
            }
        }
        return null;
    }

    /**
     * 提取数值条件
     */
    private extractNumericConditions(query: string): QueryCondition[] {
        const conditions: QueryCondition[] = [];

        // 匹配模式: 关键词 + 修饰词 + 数值
        for (const [keyword, mapping] of Object.entries(KEYWORD_MAPPINGS)) {
            if (!query.includes(keyword)) continue;

            // 查找关键词后的数值
            const keywordIndex = query.indexOf(keyword);
            const afterKeyword = query.substring(keywordIndex + keyword.length);

            // 提取数值
            const numberMatch = afterKeyword.match(/(\d+(?:\.\d+)?)/);
            if (numberMatch) {
                let value: number | [number, number] = parseFloat(numberMatch[1]);
                let operator = mapping.defaultOperator;

                // 检查修饰词
                for (const [modifier, config] of Object.entries(VALUE_MODIFIERS)) {
                    if (query.includes(modifier + keyword) || query.includes(keyword + modifier)) {
                        operator = config.operator;
                        break;
                    }
                }

                // 处理百分比
                if (afterKeyword.includes('%') || ['roe', 'roa', 'gross_margin', 'net_margin', 'dividend_yield', 'revenue_growth', 'profit_growth', 'change_pct', 'turnover_rate'].includes(mapping.field)) {
                    // 保持百分比值
                }

                // 处理"低估值"等模糊描述
                if (keyword === '低估值' || (keyword.includes('低') && keyword.includes('估值'))) {
                    conditions.push({
                        category: 'fundamental',
                        field: 'pe',
                        operator: '<',
                        value: 20,
                        confidence: 0.7,
                    });
                    conditions.push({
                        category: 'fundamental',
                        field: 'pb',
                        operator: '<',
                        value: 2,
                        confidence: 0.7,
                    });
                    continue;
                }

                conditions.push({
                    category: mapping.category,
                    field: mapping.field,
                    operator,
                    value,
                    confidence: 0.85,
                });
            } else {
                // 没有具体数值，使用默认值
                const defaultValues = this.getDefaultValue(mapping.field);
                if (defaultValues) {
                    conditions.push({
                        category: mapping.category,
                        field: mapping.field,
                        operator: mapping.defaultOperator,
                        value: defaultValues,
                        confidence: 0.6,
                    });
                }
            }
        }

        // 处理特殊模式
        // "高股息低估值"
        if (query.includes('高股息')) {
            if (!conditions.some(c => c.field === 'dividend_yield')) {
                conditions.push({
                    category: 'fundamental',
                    field: 'dividend_yield',
                    operator: '>',
                    value: 3,
                    confidence: 0.8,
                });
            }
        }

        if (query.includes('低估值')) {
            if (!conditions.some(c => c.field === 'pe')) {
                conditions.push({
                    category: 'fundamental',
                    field: 'pe',
                    operator: '<',
                    value: 20,
                    confidence: 0.7,
                });
            }
        }

        return conditions;
    }

    /**
     * 提取布尔条件
     */
    private extractBooleanConditions(query: string): QueryCondition[] {
        const conditions: QueryCondition[] = [];

        if (query.includes('非st')) {
            conditions.push({
                category: 'fundamental',
                field: 'exclude_st',
                operator: '=',
                value: true,
                confidence: 0.9,
            });
        }

        if (query.includes('非科创')) {
            conditions.push({
                category: 'fundamental',
                field: 'exclude_star',
                operator: '=',
                value: true,
                confidence: 0.9,
            });
        }

        if (query.includes('非创业')) {
            conditions.push({
                category: 'fundamental',
                field: 'exclude_chinext',
                operator: '=',
                value: true,
                confidence: 0.9,
            });
        }

        return conditions;
    }

    /**
     * 提取技术指标条件
     */
    private extractTechnicalConditions(query: string): QueryCondition[] {
        const conditions: QueryCondition[] = [];

        // MACD金叉/死叉
        if (query.includes('macd') && query.includes('金叉')) {
            conditions.push({
                category: 'technical',
                field: 'macd_cross',
                operator: '=',
                value: 'golden',
                confidence: 0.9,
            });
        }
        if (query.includes('macd') && query.includes('死叉')) {
            conditions.push({
                category: 'technical',
                field: 'macd_cross',
                operator: '=',
                value: 'death',
                confidence: 0.9,
            });
        }

        // 均线突破
        const maPatterns = [
            { pattern: /站上(\d+)日均线/, field: 'above_ma', confidence: 0.85 },
            { pattern: /突破(\d+)日均线/, field: 'breakout_ma', confidence: 0.85 },
            { pattern: /跌破(\d+)日均线/, field: 'below_ma', confidence: 0.85 },
            { pattern: /(\d+)日均线上方/, field: 'above_ma', confidence: 0.85 },
            { pattern: /(\d+)日均线下方/, field: 'below_ma', confidence: 0.85 },
        ];

        for (const { pattern, field, confidence } of maPatterns) {
            const match = query.match(pattern);
            if (match) {
                conditions.push({
                    category: 'technical',
                    field,
                    operator: '=',
                    value: parseInt(match[1]),
                    confidence,
                });
            }
        }

        // KDJ超买超卖
        if (query.includes('kdj') && query.includes('超买')) {
            conditions.push({
                category: 'technical',
                field: 'kdj_status',
                operator: '=',
                value: 'overbought',
                confidence: 0.85,
            });
        }
        if (query.includes('kdj') && query.includes('超卖')) {
            conditions.push({
                category: 'technical',
                field: 'kdj_status',
                operator: '=',
                value: 'oversold',
                confidence: 0.85,
            });
        }

        // RSI
        if (query.includes('rsi')) {
            if (query.includes('超买')) {
                conditions.push({
                    category: 'technical',
                    field: 'rsi',
                    operator: '>',
                    value: 70,
                    confidence: 0.85,
                });
            } else if (query.includes('超卖')) {
                conditions.push({
                    category: 'technical',
                    field: 'rsi',
                    operator: '<',
                    value: 30,
                    confidence: 0.85,
                });
            }
        }

        return conditions;
    }

    /**
     * 提取资金流向条件
     */
    private extractFundFlowConditions(query: string): QueryCondition[] {
        const conditions: QueryCondition[] = [];

        // 主力资金
        if (query.includes('主力') && query.includes('流入')) {
            conditions.push({
                category: 'fund_flow',
                field: 'main_inflow',
                operator: '>',
                value: 0,
                confidence: 0.8,
            });
        }
        if (query.includes('主力') && query.includes('流出')) {
            conditions.push({
                category: 'fund_flow',
                field: 'main_outflow',
                operator: '>',
                value: 0,
                confidence: 0.8,
            });
        }

        // 北向资金
        if ((query.includes('北向') || query.includes('外资')) && query.includes('流入')) {
            conditions.push({
                category: 'fund_flow',
                field: 'north_inflow',
                operator: '>',
                value: 0,
                confidence: 0.85,
            });
        }

        // 连续流入
        const continuousMatch = query.match(/连续(\d+)日?净?流入/);
        if (continuousMatch) {
            conditions.push({
                category: 'fund_flow',
                field: 'continuous_inflow_days',
                operator: '>=',
                value: parseInt(continuousMatch[1]),
                confidence: 0.9,
            });
        }

        return conditions;
    }

    /**
     * 提取特殊条件
     */
    private extractSpecialConditions(query: string): QueryCondition[] {
        const conditions: QueryCondition[] = [];

        // 涨停
        if (query.includes('涨停') && !query.includes('跌停')) {
            if (query.includes('首板') || query.includes('首次')) {
                conditions.push({
                    category: 'market',
                    field: 'first_limit_up',
                    operator: '=',
                    value: true,
                    confidence: 0.9,
                });
            } else {
                conditions.push({
                    category: 'market',
                    field: 'limit_up',
                    operator: '=',
                    value: true,
                    confidence: 0.9,
                });
            }
        }

        // 连板
        const continuousLimitMatch = query.match(/(\d+)连板/);
        if (continuousLimitMatch) {
            conditions.push({
                category: 'market',
                field: 'continuous_limit_days',
                operator: '>=',
                value: parseInt(continuousLimitMatch[1]),
                confidence: 0.95,
            });
        }

        // 创新高/新低
        if (query.includes('创新高') || query.includes('历史新高')) {
            conditions.push({
                category: 'market',
                field: 'new_high',
                operator: '=',
                value: true,
                confidence: 0.9,
            });
        }
        if (query.includes('创新低') || query.includes('历史新低')) {
            conditions.push({
                category: 'market',
                field: 'new_low',
                operator: '=',
                value: true,
                confidence: 0.9,
            });
        }

        // 放量
        if (query.includes('放量')) {
            conditions.push({
                category: 'market',
                field: 'volume_ratio',
                operator: '>',
                value: 2,
                confidence: 0.75,
            });
        }

        // 缩量
        if (query.includes('缩量')) {
            conditions.push({
                category: 'market',
                field: 'volume_ratio',
                operator: '<',
                value: 0.5,
                confidence: 0.75,
            });
        }

        return conditions;
    }

    /**
     * 提取排序方式
     */
    private extractSortBy(query: string): { field: string; order: 'asc' | 'desc' } | undefined {
        // 默认排序映射
        const fieldMappings: Record<string, string> = {
            '涨幅': 'change_pct',
            '市值': 'market_cap',
            '换手率': 'turnover_rate',
            '成交量': 'volume',
            '成交额': 'amount',
            '价格': 'price',
            '市盈率': 'pe',
            '股息率': 'dividend_yield',
            'roe': 'roe',
        };

        const directionalMatch = query.match(/(成交额|成交量|涨幅|市值|换手率|价格)(由|从)(小到大|大到小)/);
        if (directionalMatch) {
            const fieldName = directionalMatch[1];
            const order = directionalMatch[3] === '小到大' ? 'asc' : 'desc';
            const field = fieldMappings[fieldName] || fieldName;
            return { field, order };
        }

        const sortPatterns = [
            { pattern: /按(.+?)排序/, extract: true },
            { pattern: /(.+?)最高/, field: null, order: 'desc' as const },
            { pattern: /(.+?)最低/, field: null, order: 'asc' as const },
        ];

        for (const { pattern, order } of sortPatterns) {
            const match = query.match(pattern);
            if (match) {
                const fieldName = match[1];
                const field = fieldMappings[fieldName] || fieldName;
                return { field, order: order || 'desc' };
            }
        }

        return undefined;
    }

    /**
     * 确定条件逻辑
     */
    private determineLogic(query: string): 'and' | 'or' {
        if (query.includes('或者') || query.includes('或')) {
            return 'or';
        }
        return 'and';
    }

    /**
     * 提取数量限制
     */
    private extractLimit(query: string): number | undefined {
        const match = query.match(/前(\d+)|top(\d+)|(\d+)只/i);
        if (match) {
            return parseInt(match[1] || match[2] || match[3]);
        }
        return undefined;
    }

    /**
     * 获取字段默认值
     */
    private getDefaultValue(field: string): number | [number, number] | null {
        const defaults: Record<string, number | [number, number]> = {
            'pe': 20,
            'pb': 2,
            'roe': 15,
            'dividend_yield': 3,
            'revenue_growth': 20,
            'profit_growth': 20,
            'turnover_rate': 5,
            'volume_ratio': 2,
        };
        return defaults[field] || null;
    }

    /**
     * 生成查询建议
     */
    generateSuggestions(partialQuery: string): string[] {
        const suggestions: string[] = [];
        const normalized = this.normalizeQuery(partialQuery);

        // 基于输入生成建议
        if (normalized.includes('高股息')) {
            suggestions.push('高股息低估值的银行股');
            suggestions.push('高股息且ROE大于15%的股票');
        }

        if (normalized.includes('涨停')) {
            suggestions.push('今日涨停且换手率大于10%的股票');
            suggestions.push('连续2天涨停的股票');
            suggestions.push('首次涨停的股票');
        }

        if (normalized.includes('macd')) {
            suggestions.push('MACD刚刚金叉的股票');
            suggestions.push('MACD金叉且站上20日均线的股票');
        }

        if (normalized.includes('北向') || normalized.includes('外资')) {
            suggestions.push('北向资金连续5日净流入的股票');
            suggestions.push('北向资金今日大幅流入的股票');
        }

        // 通用建议
        if (suggestions.length === 0) {
            suggestions.push(
                '市盈率低于20且ROE大于15%的消费股',
                '最近3天涨停且换手率大于10%的股票',
                '北向资金连续5日净流入的股票',
                'MACD刚刚金叉且在20日均线上方的股票',
                '高股息低估值的银行股',
            );
        }

        return suggestions.slice(0, 5);
    }
}

// 导出单例
export const nlpQueryParser = new NLPQueryParser();
