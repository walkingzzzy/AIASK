import type OpenAI from 'openai';

export const DECISION_TOOLS: OpenAI.ChatCompletionTool[] = [
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
      description: '智能分析某只股票是否应该卖出（需要买入价）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          buy_price: { type: 'number', description: '买入价格（必填）' },
          holding_days: { type: 'number', description: '持有天数，默认0' },
        },
        required: ['code', 'buy_price'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_investment_analysis',
      description: '获取投资分析综合报告',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'smart_stock_diagnosis',
      description: '对股票进行综合诊断分析（技术面+基本面+资金面）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
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
      name: 'check_candlestick_patterns',
      description: '检测K线形态（锤子线、吞没形态、十字星等）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_available_patterns',
      description: '获取支持的K线形态列表',
      parameters: { type: 'object', properties: {} },
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
      name: 'parse_selection_query',
      description: '自然语言选股解析（如"市盈率低于20的银行股"）',
      parameters: { type: 'object', properties: { query: { type: 'string', description: '自然语言选股条件描述' } }, required: ['query'] },
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
      name: 'generate_daily_report',
      description: '生成每日市场综合报告',
      parameters: { type: 'object', properties: {} },
    },
  },
];
