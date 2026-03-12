import type OpenAI from 'openai';

export const MARKET_DATA_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'get_realtime_quote',
      description: '获取股票实时行情报价（价格、涨跌幅、成交量等）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码，如 600519' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_batch_quotes',
      description: '批量获取多只股票实时行情',
      parameters: { type: 'object', properties: { stock_codes: { type: 'array', items: { type: 'string' }, description: '股票代码列表' } }, required: ['stock_codes'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_kline_data',
      description: '获取股票K线数据（日线/周线/月线）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, period: { type: 'string', enum: ['daily', 'weekly', 'monthly'], description: '周期' }, limit: { type: 'number', description: '数据条数，默认100' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_minute_kline',
      description: '获取股票分钟级K线（1分钟/5分钟/15分钟/30分钟/60分钟）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' }, period: { type: 'string', enum: ['1', '5', '15', '30', '60'], description: '分钟周期' }, limit: { type: 'number', description: '数据条数' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_index_quote',
      description: '获取指数实时行情（上证指数、深证成指、创业板指等）',
      parameters: { type: 'object', properties: { index_code: { type: 'string', description: '指数代码，如 000001（上证指数）、399001（深证成指）' } }, required: ['index_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_order_book',
      description: '获取股票实时五档盘口数据',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_trade_details',
      description: '获取股票成交明细（逐笔成交）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_limit_up_stocks',
      description: '获取当日涨停板股票列表',
      parameters: { type: 'object', properties: { date: { type: 'string', description: '日期 YYYY-MM-DD，默认今天' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_list',
      description: '获取A股全部股票列表',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_market_blocks',
      description: '获取板块列表（行业板块/概念板块/地域板块）',
      parameters: { type: 'object', properties: { block_type: { type: 'string', enum: ['industry', 'concept', 'area'], description: '板块类型' } }, required: ['block_type'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_block_stocks',
      description: '获取指定板块的成分股',
      parameters: { type: 'object', properties: { block_code: { type: 'string', description: '板块代码（从 get_market_blocks 获取）' } }, required: ['block_code'] },
    },
  },
];
