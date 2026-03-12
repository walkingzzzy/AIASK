import type OpenAI from 'openai';

import { MARKET_DATA_TOOLS } from './market-data';
import { FUNDAMENTALS_TOOLS } from './fundamentals';
import { DECISION_TOOLS } from './decision';
import { FUND_FLOW_TOOLS } from './fund-flow';
import { RESEARCH_TOOLS } from './research';
import { QUANT_TOOLS } from './quant';
import { MISC_TOOLS } from './misc';

export { buildSystemPrompt, type UserContextForPrompt } from './system-prompt';

export { MARKET_DATA_TOOLS } from './market-data';
export { FUNDAMENTALS_TOOLS } from './fundamentals';
export { DECISION_TOOLS } from './decision';
export { FUND_FLOW_TOOLS } from './fund-flow';
export { RESEARCH_TOOLS } from './research';
export { QUANT_TOOLS } from './quant';
export { MISC_TOOLS } from './misc';

export const CHAT_TOOLS: OpenAI.ChatCompletionTool[] = [
  ...MARKET_DATA_TOOLS,
  ...FUNDAMENTALS_TOOLS,
  ...DECISION_TOOLS,
  ...FUND_FLOW_TOOLS,
  ...RESEARCH_TOOLS,
  ...QUANT_TOOLS,
  ...MISC_TOOLS,
];
