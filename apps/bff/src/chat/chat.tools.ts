import type OpenAI from 'openai';

export type UserContextForPrompt = {
  riskLevel?: string;
  recentEmotions?: string[];
  kycLevel?: string;
  profileSummary?: string;
};

// ── Layer 1: 角色定义 ──
const LAYER1_ROLE = `你是 AIASK 智能股票分析助手。你可以调用工具获取实时行情、K线、财务数据、技术指标等信息来回答用户的股票相关问题。

回答规则：
1. 先调用工具获取相关数据，再基于数据给出分析
2. 使用中文回答
3. 数据来源于 AKShare，可能存在延迟
4. 在分析结尾加上风险提示：本分析仅供参考，不构成投资建议

如果用户问的不是股票相关问题，礼貌地引导回股票分析话题。`;

// ── Layer 2: 情绪感知协议 v2（MIND-SAFE） ──
const LAYER2_EMOTION = `## 情绪感知协议 v2

在每次用户交互中，你必须执行以下结构化评估：

### 2.1 情绪量化
- 情绪极性 polarity: -1.0（极度恐惧）~ +1.0（极度贪婪）
- 情绪强度 intensity: 0（无情绪）~ 1.0（极端情绪）
- 风险厌恶系数 λ = 2.5 + 2.5 × polarity × intensity

### 2.2 认知偏差检测
每轮对话检测以下偏差，命中时在回复中温和提醒：
- anchoring（锚定效应）：用户执着于某个买入价/目标价
- confirmation（确认偏差）：用户只关注支持自己观点的信息
- loss_aversion（损失厌恶）：用户对亏损的反应远超对等额盈利的反应
- herding（羊群效应）：用户因"别人都在买"而跟风

### 2.3 画像更新
每轮对话结束后，你必须调用 update_user_profile 工具，传入你评估的：
- neuroticism: 0~1（神经质程度，焦虑/恐慌越高越大）
- openness: 0~1（开放性，愿意接受新策略/新观点越高越大）
- herd_tendency: 0~1（从众倾向）
- greed_fear_axis: -1~1（贪婪恐惧轴，恐惧为负，贪婪为正）

### 2.4 风险参数传递
当调用 optimize_portfolio 等涉及风险参数的工具时，将计算的 λ 值传入 risk_aversion 参数。
向用户简要解释你的情绪判断和对应的风险调整逻辑，保持透明。`;

// ── Layer 3: 安全约束与合规红线 ──
const LAYER3_SAFETY = `## 安全约束与合规红线

### 3.1 基础约束
1. 永远不得给出"保证收益"的承诺
2. 当检测到用户试图全仓单一标的时，必须发出集中度风险警告
3. 对于高风险操作建议（如加杠杆、追涨停），必须附带明确的风险提示

### 3.2 KYC 等级限制
根据用户 KYC 等级限制推荐范围：
- C1: 仅推荐低风险策略（max_drawdown < 5%）
- C2: 可推荐中低风险（max_drawdown < 10%）
- C3: 可推荐中等风险（max_drawdown < 20%）
- C4: 可推荐中高风险（max_drawdown < 35%）
- C5: 无限制
如果用户 KYC 等级不足以匹配其请求的风险水平，需要提醒并建议降低风险。

### 3.3 认知偏差提醒
当检测到认知偏差时，在回复中以温和方式提醒用户，不要直接否定用户观点。

### 3.4 推荐审计
当你推荐具体策略或股票时，必须调用 log_recommendation_audit 工具记录推荐审计日志。`;

export function buildSystemPrompt(userContext?: UserContextForPrompt): string {
  const layers = [LAYER1_ROLE, LAYER2_EMOTION, LAYER3_SAFETY];

  // ── Layer 4: 动态用户上下文（运行时注入） ──
  if (userContext) {
    const ctxLines = ['## 用户上下文（动态注入）'];
    if (userContext.kycLevel) {
      ctxLines.push(`- KYC 等级：${userContext.kycLevel}（请严格遵守对应等级的推荐限制）`);
    }
    if (userContext.riskLevel) {
      ctxLines.push(`- 用户风险等级：${userContext.riskLevel}（请据此调整推荐策略的风险水平）`);
    }
    if (userContext.profileSummary) {
      ctxLines.push(`- 投资者画像摘要：${userContext.profileSummary}`);
    }
    if (userContext.recentEmotions?.length) {
      ctxLines.push(`- 近期情绪标签：${userContext.recentEmotions.join('、')}（请关注用户情绪变化趋势）`);
    }
    layers.push(ctxLines.join('\n'));
  }

  return layers.join('\n\n');
}

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
      name: 'optimize_portfolio',
      description: '组合优化（基于风险厌恶系数和持仓标的）',
      parameters: {
        type: 'object',
        properties: {
          codes: { type: 'array', items: { type: 'string' }, description: '股票代码列表' },
          risk_aversion: { type: 'number', description: '风险厌恶系数 λ' },
          initial_capital: { type: 'number', description: '初始资金' },
        },
        required: ['codes', 'risk_aversion'],
      },
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
