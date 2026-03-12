import type OpenAI from 'openai';

export const FUND_FLOW_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'get_stock_fund_flow',
      description: '获取个股资金流向数据',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund',
      description: '获取北向资金整体流入/流出数据',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund_holding',
      description: '获取北向资金持仓数据',
      parameters: { type: 'object', properties: { stock_code: { type: 'string', description: '6位股票代码' } }, required: ['stock_code'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_north_fund_top',
      description: '获取北向资金成交净买入TOP个股',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_sector_fund_flow',
      description: '获取行业板块资金流向',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_concept_fund_flow',
      description: '获取概念板块资金流向',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_margin_data',
      description: '获取融资融券数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码（可选，不传则获取市场总量）' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_margin_ranking',
      description: '获取融资融券标的排行榜',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_block_trades',
      description: '获取大宗交易数据',
      parameters: { type: 'object', properties: { code: { type: 'string', description: '6位股票代码（可选）' } } },
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
];
