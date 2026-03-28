import { Body, Controller, Get, Post, Req, Res } from '@nestjs/common';
import { IsArray, IsString, IsIn, ValidateNested, IsOptional, MaxLength, ArrayMaxSize, IsObject } from 'class-validator';
import { Type } from 'class-transformer';
import type { Request, Response } from 'express';
import { ChatService } from './chat.service';
import { PreferencesService } from '../auth/preferences.service';
import type { ChatMode } from './chat.protocol';

class SaveLlmConfigDto {
  @IsString() apiKey!: string;
  @IsString() baseUrl!: string;
  @IsString() model!: string;
}

class ChatMessageDto {
  @IsIn(['user', 'assistant', 'system']) role!: 'user' | 'assistant' | 'system';
  @IsString() @MaxLength(32000) content!: string;
}

class ChatCompletionsDto {
  @IsArray()
  @ArrayMaxSize(100)
  @ValidateNested({ each: true })
  @Type(() => ChatMessageDto)
  messages!: ChatMessageDto[];

  @IsOptional()
  @IsIn(['chat', 'copilot', 'assistant'])
  mode?: ChatMode;

  @IsOptional()
  @ValidateNested()
  @Type(() => ChatPageContextDto)
  pageContext?: ChatPageContextDto | null;

  @IsOptional()
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => ClientActionDescriptorDto)
  availableActions?: ClientActionDescriptorDto[];
}

class ChatPageContextDto {
  @IsString() pageKey!: string;
  @IsString() title!: string;
  @IsString() summary!: string;
  @IsOptional() @IsString() stockCode?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) tags?: string[];
  @IsOptional() @IsArray() @IsString({ each: true }) suggestions?: string[];
  @IsOptional() @IsObject() raw?: Record<string, unknown>;
}

class ClientActionDescriptorDto {
  @IsString() id!: string;
  @IsString() label!: string;
  @IsOptional() @IsString() description?: string;
  @IsOptional() @IsArray() @IsString({ each: true }) keywords?: string[];
  @IsOptional() @IsIn(['global', 'page']) scope?: 'global' | 'page';
  @IsOptional() @IsString() pageKey?: string;
}

class ChatConversationMessageDto {
  @IsIn(['user', 'assistant']) role!: 'user' | 'assistant';
  @IsString() content!: string;
}

class ChatConversationDto {
  @IsString() id!: string;
  @IsOptional() @IsString() title?: string;
  @IsString() updatedAt!: string;
  @IsOptional() @IsString() workspaceId?: string;
  @IsArray() @ValidateNested({ each: true }) @Type(() => ChatConversationMessageDto) messages!: ChatConversationMessageDto[];
}

class SyncChatConversationsDto {
  @IsArray() @ValidateNested({ each: true }) @Type(() => ChatConversationDto) conversations!: ChatConversationDto[];
}

const MODEL_PRESETS = [
  { provider: 'A-J API', baseUrl: 'https://api.a-j.app/v1', models: ['gpt-5.4'] },
  { provider: 'OpenAI', baseUrl: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { provider: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { provider: 'Moonshot', baseUrl: 'https://api.moonshot.cn/v1', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'] },
  { provider: 'Qwen', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-turbo', 'qwen-plus', 'qwen-max'] },
  { provider: 'GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-flash', 'glm-4', 'glm-4-plus'] },
  { provider: 'Yi', baseUrl: 'https://api.lingyiwanwu.com/v1', models: ['yi-lightning', 'yi-large', 'yi-medium'] },
];

type ChatRequest = Request & {
  user?: { sub?: string; id?: string };
};

@Controller('chat')
export class ChatController {
  constructor(
    private readonly chatService: ChatService,
    private readonly preferencesService: PreferencesService,
  ) {}

  @Get('config')
  async getConfig(@Req() req: ChatRequest) {
    const userId = req.user?.sub ?? req.user?.id ?? '';
    const config = await this.preferencesService.getMaskedLlmConfig(String(userId));
    return { success: true, data: config };
  }

  @Post('config')
  async saveConfig(@Req() req: ChatRequest, @Body() body: SaveLlmConfigDto) {
    const userId = req.user?.sub ?? req.user?.id ?? '';
    await this.preferencesService.setLlmConfig(String(userId), {
      apiKey: body.apiKey,
      baseUrl: body.baseUrl.replace(/\/+$/, ''),
      model: body.model,
    });
    return { success: true, data: { saved: true } };
  }

  @Get('models')
  getModels() {
    return { success: true, data: MODEL_PRESETS };
  }

  @Get('conversations')
  async getConversations(@Req() req: ChatRequest) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const prefs = await this.preferencesService.getUserPreferences(userId);
    const chatHistory = ((prefs.chatHistory ?? {}) as Record<string, unknown>).conversations;
    return { success: true, data: { conversations: Array.isArray(chatHistory) ? chatHistory : [] } };
  }

  @Post('conversations/sync')
  async syncConversations(@Req() req: ChatRequest, @Body() body: SyncChatConversationsDto) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const prefs = await this.preferencesService.getUserPreferences(userId);
    await this.preferencesService.setUserPreferences(userId, {
      ...prefs,
      chatHistory: {
        conversations: body.conversations.slice(0, 50),
        syncedAt: new Date().toISOString(),
      },
    });
    return { success: true, data: { saved: true, count: body.conversations.length } };
  }

  @Post('completions')
  async completions(@Req() req: ChatRequest, @Res() res: Response, @Body() body: ChatCompletionsDto) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.flushHeaders();

    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    let clientDisconnected = false;
    const markDisconnected = () => {
      clientDisconnected = true;
    };

    req.on('close', markDisconnected);
    res.on('close', markDisconnected);

    try {
      for await (const event of this.chatService.streamChat(userId, body)) {
        if (clientDisconnected || res.writableEnded || res.destroyed) {
          break;
        }
        res.write(`data: ${JSON.stringify(event)}\n\n`);
      }
    } catch (err: unknown) {
      if (!clientDisconnected && !res.writableEnded && !res.destroyed) {
        const message = err instanceof Error ? err.message : String(err);
        res.write(`data: ${JSON.stringify({ type: 'error', message })}\n\n`);
      }
    } finally {
      req.off('close', markDisconnected);
      res.off('close', markDisconnected);
    }

    if (!res.writableEnded && !res.destroyed) {
      res.end();
    }
  }
}
