import type OpenAI from 'openai';

export const QUANT_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'run_simple_backtest',
      description: '运行简单策略回测（支持ma_cross/rsi_basic/macd_trend等策略）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          strategy: { type: 'string', description: '策略名：ma_cross, rsi_basic, macd_trend' },
          start_date: { type: 'string', description: '起始日期 YYYY-MM-DD' },
          end_date: { type: 'string', description: '结束日期 YYYY-MM-DD' },
          initial_capital: { type: 'number', description: '初始资金，默认100000' },
        },
        required: ['code', 'strategy'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_batch_backtest',
      description: '批量回测（多只股票 × 多个策略）',
      parameters: {
        type: 'object',
        properties: {
          codes: { type: 'array', items: { type: 'string' }, description: '股票代码列表' },
          strategies: { type: 'array', items: { type: 'string' }, description: '策略名列表' },
          start_date: { type: 'string', description: '起始日期' },
          end_date: { type: 'string', description: '结束日期' },
        },
        required: ['codes', 'strategies'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'list_factors',
      description: '列出所有可用量化因子',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'calculate_factor',
      description: '计算单个量化因子值（如 roe_ttm, atr_14, pe_ttm 等）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          factor: { type: 'string', description: '因子名（用 list_factors 查看可用因子）' },
        },
        required: ['code', 'factor'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_factor_profile',
      description: '获取因子画像（单只股票的多维因子雷达图数据）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_conditional_returns',
      description: '按历史条件统计未来收益分布（条件概率分析）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          conditions: {
            type: 'array',
            items: { type: 'object' },
            description: '条件列表，每项为 {field, op, value}，如 [{field:"rsi_14",op:"<",value:30}]',
          },
          forward_days: { type: 'array', items: { type: 'number' }, description: '向前看天数列表，默认[5,10,20]' },
          logic: { type: 'string', enum: ['AND', 'OR'], description: '多条件逻辑，默认AND' },
          lookback_days: { type: 'number', description: '回溯天数，默认250' },
        },
        required: ['code', 'conditions'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'find_similar_patterns',
      description: '查找历史上与当前K线相似的走势模式',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, window: { type: 'number', description: '匹配窗口长度，默认20' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_signal_hit_rate',
      description: '获取技术信号历史命中率',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, signal: { type: 'string', description: '信号名称' } }, required: ['code', 'signal'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_similar_stocks',
      description: '搜索与指定股票相似的股票（基于量化特征）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, top_k: { type: 'number', description: '返回数量，默认10' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_by_kline',
      description: '根据K线形态搜索相似走势的股票',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, window: { type: 'number', description: 'K线窗口长度' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'semantic_stock_search',
      description: '语义化股票搜索（用自然语言描述想找的股票）',
      parameters: { type: 'object', properties: { query: { type: 'string', description: '自然语言描述，如"高分红低估值的银行股"' } }, required: ['query'] },
    },
  },
];
