import type OpenAI from 'openai';

export const SYSTEM_PROMPT = `你是 AIASK 智能股票分析助手。你可以调用工具获取实时行情、K线、财务数据、技术指标等信息来回答用户的股票相关问题。

回答规则：
1. 先调用工具获取相关数据，再基于数据给出分析
2. 使用中文回答
3. 数据来源于 AKShare，可能存在延迟
4. 在分析结尾加上风险提示：本分析仅供参考，不构成投资建议

如果用户问的不是股票相关问题，礼貌地引导回股票分析话题。`;

export const CHAT_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'get_realtime_quote',
      description: '获取股票实时行情报价（价格、涨跌幅、成交量等）',
      parameters: { type: 'object', properties: { symbol: { type: 'string', description: '6位股票代码，如 600519' } }, required: ['symbol'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_kline_data',
      description: '获取股票K线数据（日线/周线/月线）',
      parameters: { type: 'object', properties: { symbol: { type: 'string', description: '6位股票代码' }, period: { type: 'string', enum: ['daily', 'weekly', 'monthly'], description: '周期' }, limit: { type: 'number', description: '数据条数，默认100' } }, required: ['symbol'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_info',
      description: '获取股票基本信息（公司名称、行业、上市日期等）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_financials',
      description: '获取股票财务数据（ROE、净利润、营收、资产负债率）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_valuation_metrics',
      description: '获取股票估值指标（PE、PB、PS、总市值）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'should_i_buy',
      description: '智能分析某只股票是否值得买入',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'should_i_sell',
      description: '智能分析某只股票是否应该卖出',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'smart_stock_diagnosis',
      description: '对股票进行综合诊断分析',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'calculate_technical_indicators',
      description: '计算技术指标（MA、RSI、MACD、KDJ、BOLL等）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, indicators: { type: 'array', items: { type: 'string' }, description: '指标列表，如 ["MA","RSI","MACD"]' } }, required: ['code', 'indicators'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'analyze_stock_sentiment',
      description: '分析个股市场情绪',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_stocks',
      description: '搜索股票（按关键词搜索股票名称或代码）',
      parameters: { type: 'object', properties: { keyword: { type: 'string', description: '搜索关键词' } }, required: ['keyword'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_fund_flow',
      description: '获取个股资金流向数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_profit_forecast',
      description: '获取股票盈利预测数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_news',
      description: '获取个股相关新闻',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, limit: { type: 'number', description: '新闻条数，默认10' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund_holding',
      description: '获取北向资金持仓数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_sector_fund_flow',
      description: '获取板块资金流向',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_industry_chain',
      description: '获取产业链信息',
      parameters: { type: 'object', properties: { keyword: { type: 'string', description: '产业链关键词' } }, required: ['keyword'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_dragon_tiger',
      description: '获取龙虎榜数据',
      parameters: { type: 'object', properties: { date: { type: 'string', description: '日期，如 2024-01-15，默认最新' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_macro_indicator',
      description: '获取宏观经济指标数据（GDP、CPI、PMI等）',
      parameters: { type: 'object', properties: { indicator: { type: 'string', description: '指标名称，如 gdp、cpi、pmi' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'calculate_fear_greed_index',
      description: '计算市场恐贪指数',
      parameters: { type: 'object', properties: {} },
    },
  },
];
