import type OpenAI from 'openai';

export const FUNDAMENTALS_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'get_stock_info',
      description: '获取股票基本信息（公司名称、行业、上市日期等）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_financials',
      description: '获取股票财务数据（ROE、净利润、营收、资产负债率）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_stock_capital',
      description: '获取股票股本信息（总股本、流通股本等）',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
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
      name: 'get_historical_valuation',
      description: '获取股票历史估值分位数（PE/PB百分位）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, years: { type: 'number', description: '回溯年数，默认5' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'dcf_valuation',
      description: 'DCF现金流折现估值模型',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, growth_rate: { type: 'number', description: '增长率（如0.08表示8%）' }, discount_rate: { type: 'number', description: '折现率/WACC（如0.1表示10%）' }, terminal_growth_rate: { type: 'number', description: '永续增长率（如0.03），须小于discount_rate' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'ddm_valuation',
      description: 'DDM股利贴现模型估值',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' }, required_return: { type: 'number', description: '要求回报率' }, growth_rate: { type: 'number', description: '股利增长率' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'relative_valuation',
      description: '相对估值法（行业可比公司PE/PB/PS对标）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'scenario_dcf_valuation',
      description: '情景分析DCF估值（乐观/中性/悲观三种场景）',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码' } }, required: ['code'] },
    },
  },
];
