import type OpenAI from 'openai';

export const MISC_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: 'get_macro_indicator',
      description: '获取宏观经济指标数据（GDP、CPI、PMI等）',
      parameters: { type: 'object', properties: { indicator: { type: 'string', description: '指标名称，如 gdp、cpi、pmi' } }, required: ['indicator'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_option_chain',
      description: '获取期权链数据',
      parameters: { type: 'object', properties: { underlying: { type: 'string', description: '标的代码，如 510300（300ETF）' } }, required: ['underlying'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'optimize_portfolio',
      description: '组合优化（基于风险厌恶系数和持仓标的）',
      parameters: {
        type: 'object',
        properties: {
          stocks: { type: 'array', items: { type: 'string' }, description: '股票代码列表' },
          risk_aversion: { type: 'number', description: '风险厌恶系数 λ' },
          method: { type: 'string', description: '优化方法：mean_variance/equal_weight/risk_parity/black_litterman' },
        },
        required: ['stocks'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'analyze_portfolio_risk',
      description: '分析组合风险（VaR、波动率、最大回撤等）',
      parameters: {
        type: 'object',
        properties: {
          holdings: { type: 'array', items: { type: 'object', properties: { code: { type: 'string' }, weight: { type: 'number' } } }, description: '持仓列表，每项含 code 和 weight' },
        },
        required: ['holdings'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'stress_test_portfolio',
      description: '组合压力测试（模拟极端市场场景的组合表现）',
      parameters: {
        type: 'object',
        properties: {
          holdings: { type: 'array', items: { type: 'object', properties: { code: { type: 'string' }, weight: { type: 'number' } } }, description: '持仓列表，每项含 code 和 weight' },
          scenarios: { type: 'array', items: { type: 'string' }, description: '场景名称列表，可选: market_crash/sector_rotation/interest_rate_hike/black_swan' },
        },
        required: ['holdings'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'create_indicator_alert',
      description: '创建技术指标预警',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          indicator: { type: 'string', description: '指标名称，如 rsi_14, macd' },
          condition: { type: 'string', description: '条件：above/below/cross_up/cross_down' },
          value: { type: 'number', description: '阈值' },
        },
        required: ['code', 'indicator', 'condition', 'value'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'create_combo_alert',
      description: '创建组合预警（多条件组合触发）',
      parameters: {
        type: 'object',
        properties: {
          code: { type: 'string', description: '6位股票代码' },
          conditions: { type: 'array', items: { type: 'object' }, description: '条件列表' },
          logic: { type: 'string', enum: ['AND', 'OR'], description: '条件逻辑' },
        },
        required: ['code', 'conditions'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'check_all_alerts',
      description: '检查所有预警是否触发',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_trading_dates',
      description: '获取交易日历（查询某段时间的交易日）',
      parameters: { type: 'object', properties: { start_date: { type: 'string', description: '起始日期' }, end_date: { type: 'string', description: '结束日期' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'get_ipo_info',
      description: '获取新股/IPO信息',
      parameters: { type: 'object', properties: {} },
    },
  },
  {
    type: 'function',
    function: {
      name: 'log_recommendation_audit',
      description: '记录推荐审计日志（推荐策略/股票时必须调用）',
      parameters: {
        type: 'object',
        properties: {
          user_id: { type: 'string', description: '用户ID' },
          strategy_id: { type: 'string', description: '策略ID' },
          stock_code: { type: 'string', description: '股票代码' },
          action: { type: 'string', description: '推荐动作：buy/sell/hold' },
          emotion_polarity: { type: 'number', description: '情绪极性 -1~1' },
          emotion_intensity: { type: 'number', description: '情绪强度 0~1' },
          cognitive_biases: { type: 'array', items: { type: 'string' }, description: '检测到的认知偏差' },
          risk_aversion: { type: 'number', description: '风险厌恶系数' },
          kyc_level: { type: 'string', description: 'KYC等级' },
          reasoning_chain: { type: 'string', description: '推理链路说明' },
        },
        required: ['user_id', 'action', 'reasoning_chain'],
      },
    },
  },
];
