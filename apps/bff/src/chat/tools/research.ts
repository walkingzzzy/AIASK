import type OpenAI from 'openai';

export const RESEARCH_TOOLS: OpenAI.ChatCompletionTool[] = [
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
      name: 'get_market_news',
      description: '获取市场综合新闻',
      parameters: { type: 'object', properties: { limit: { type: 'number', description: '新闻条数，默认20' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_notices',
      description: '获取个股公告',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' }, start_date: { type: 'string', description: '起始日期 YYYY-MM-DD' }, end_date: { type: 'string', description: '结束日期 YYYY-MM-DD' } }, required: ['start_date', 'end_date'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_research',
      description: '获取个股研究报告',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search_research',
      description: '搜索研报（按关键词）',
      parameters: { type: 'object', properties: { keyword: { type: 'string', description: '搜索关键词' } }, required: ['keyword'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_analyst_ranking',
      description: '获取分析师排名',
      parameters: { type: 'object', properties: {} },
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
      name: 'analyze_stock_sentiment',
      description: '分析个股市场情绪',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
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
  {
    type: 'function',
    function: {
      name: 'get_market_sentiment_context',
      description: '获取市场情绪全景（恐贪指数+涨跌比+板块热度）',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_text_signals',
      description: '获取个股文本信号（舆情分析）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'update_user_profile',
      description: '更新用户投资者画像（每轮对话后必须调用）',
      parameters: {
        type: 'object',
        properties: {
          user_id: { type: 'string', description: '用户ID，默认 default' },
          neuroticism: { type: 'number', description: '神经质程度 0~1' },
          openness: { type: 'number', description: '开放性 0~1' },
          herd_tendency: { type: 'number', description: '从众倾向 0~1' },
          greed_fear_axis: { type: 'number', description: '贪婪恐惧轴 -1~1' },
          confidence: { type: 'number', description: '置信度 0~1' },
        },
        required: ['neuroticism', 'openness', 'herd_tendency', 'greed_fear_axis'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_user_profile',
      description: '获取用户投资者画像（查看历史画像数据）',
      parameters: { type: 'object', properties: { user_id: { type: 'string', description: '用户ID，默认 default' } } },
    },
  },
];
