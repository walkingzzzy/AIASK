import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import OpenAI from 'openai';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { PreferencesService } from '../auth/preferences.service';
import { UserContextService } from './user-context.service';
import { CHAT_TOOLS, buildSystemPrompt } from './chat.tools';

export type ChatEvent =
  | { type: 'delta'; content: string }
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; result: unknown }
  | { type: 'error'; message: string }
  | { type: 'done' };

type ChatMessage = { role: 'user' | 'assistant' | 'system'; content: string };

const MAX_TOOL_ROUNDS = 10;

@Injectable()
export class ChatService {
  private readonly logger = new Logger(ChatService.name);

  constructor(
    private readonly mcp: McpGatewayService,
    private readonly preferencesService: PreferencesService,
    private readonly userContextService: UserContextService,
  ) {}

  async *streamChat(userId: string, messages: ChatMessage[]): AsyncGenerator<ChatEvent> {
    const config = await this.preferencesService.getLlmConfig(userId);
    if (!config) throw new BadRequestException('请先在设置中配置 LLM API Key');

    const openai = new OpenAI({ apiKey: config.apiKey, baseURL: config.baseUrl });

    const userContext = await this.userContextService.getUserContext(userId);
    const systemPrompt = buildSystemPrompt(userContext);

    const conversationMessages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
      { role: 'system', content: systemPrompt },
      ...messages.map((m) => ({ role: m.role, content: m.content }) as OpenAI.Chat.Completions.ChatCompletionMessageParam),
    ];

    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      const stream = await openai.chat.completions.create({
        model: config.model,
        messages: conversationMessages,
        tools: CHAT_TOOLS,
        stream: true,
      });

      let assistantContent = '';
      const toolCallFragments: Map<number, { id: string; name: string; arguments: string }> = new Map();

      for await (const chunk of stream) {
        const choice = chunk.choices[0];
        if (!choice) continue;

        const delta = choice.delta;
        if (delta?.content) {
          assistantContent += delta.content;
          yield { type: 'delta', content: delta.content };
        }

        if (delta?.tool_calls) {
          for (const tc of delta.tool_calls) {
            const idx = tc.index;
            if (!toolCallFragments.has(idx)) {
              toolCallFragments.set(idx, { id: tc.id ?? '', name: tc.function?.name ?? '', arguments: '' });
            }
            const frag = toolCallFragments.get(idx)!;
            if (tc.id) frag.id = tc.id;
            if (tc.function?.name) frag.name = tc.function.name;
            if (tc.function?.arguments) frag.arguments += tc.function.arguments;
          }
        }
      }

      if (toolCallFragments.size === 0) {
        yield { type: 'done' };
        return;
      }

      // Build assistant message with tool_calls
      const toolCalls: Array<{ id: string; type: 'function'; function: { name: string; arguments: string } }> = [];
      for (const [, frag] of toolCallFragments) {
        toolCalls.push({
          id: frag.id,
          type: 'function',
          function: { name: frag.name, arguments: frag.arguments },
        });
      }

      conversationMessages.push({
        role: 'assistant',
        content: assistantContent || null,
        tool_calls: toolCalls,
      } as OpenAI.Chat.Completions.ChatCompletionMessageParam);

      // Execute each tool call via MCP
      for (const tc of toolCalls) {
        let args: Record<string, unknown> = {};
        try { args = JSON.parse(tc.function.arguments); } catch { /* empty */ }
        yield { type: 'tool_call', name: tc.function.name, args };

        let result: unknown;
        try {
          result = await this.mcp.callTool(tc.function.name, args);
        } catch (err) {
          result = { error: err instanceof Error ? err.message : String(err) };
        }

        // Side-effect: record emotion when LLM updates user profile
        if (tc.function.name === 'update_user_profile') {
          try {
            const gfa = Number(args.greed_fear_axis ?? 0);
            let label: string;
            if (gfa < -0.6) label = '极度焦虑';
            else if (gfa < -0.2) label = '偏焦虑';
            else if (gfa < 0.2) label = '理性';
            else if (gfa < 0.6) label = '偏乐观';
            else label = '极度贪婪';
            this.userContextService.recordEmotion(userId, label);
          } catch { /* best-effort */ }
        }

        yield { type: 'tool_result', name: tc.function.name, result };

        conversationMessages.push({
          role: 'tool',
          tool_call_id: tc.id,
          content: typeof result === 'string' ? result : JSON.stringify(result),
        } as OpenAI.Chat.Completions.ChatCompletionMessageParam);
      }
      // Loop back for LLM to process tool results
    }

    yield { type: 'error', message: '工具调用轮次超限' };
    yield { type: 'done' };
  }
}
