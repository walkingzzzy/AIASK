import type OpenAI from 'openai';

export const LOCAL_CONTEXT_TOOL_NAMES = {
  behaviorSummary: 'get_recent_user_behavior_summary',
  behaviorEvidence: 'get_recent_user_behavior_evidence',
} as const;

export const LOCAL_CONTEXT_TOOLS: OpenAI.ChatCompletionTool[] = [
  {
    type: 'function',
    function: {
      name: LOCAL_CONTEXT_TOOL_NAMES.behaviorSummary,
      description: '读取当前用户最近的前端行为摘要，用于回答“我刚才在页面上做了什么”一类问题。',
      parameters: {
        type: 'object',
        additionalProperties: false,
        properties: {
          limit: {
            type: 'number',
            description: '读取最近多少条前端行为事件，默认 20，最大 50。',
          },
          days: {
            type: 'number',
            description: '回看最近多少天的数据，默认 30，最大 30。',
          },
        },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: LOCAL_CONTEXT_TOOL_NAMES.behaviorEvidence,
      description: '读取当前用户最近的前端行为原始证据。仅当用户明确追问“证据”“操作轨迹”“刚才点击了什么”时调用。',
      parameters: {
        type: 'object',
        additionalProperties: false,
        properties: {
          limit: {
            type: 'number',
            description: '读取最近多少条原始行为事件，默认 12，最大 20。',
          },
          days: {
            type: 'number',
            description: '回看最近多少天的数据，默认 30，最大 30。',
          },
          pageKey: {
            type: 'string',
            description: '可选，按页面键过滤。',
          },
          eventType: {
            type: 'string',
            description: '可选，按事件类型过滤。',
          },
          source: {
            type: 'string',
            description: '可选，按事件来源过滤。',
          },
        },
      },
    },
  },
];
