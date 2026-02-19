import { Body, Controller, Get, Post, Req, Res } from '@nestjs/common';
import { IsArray, IsString, IsIn, ValidateNested, IsOptional } from 'class-validator';
import { Type } from 'class-transformer';
import { ChatService } from './chat.service';
import { PreferencesService } from '../auth/preferences.service';

class SaveLlmConfigDto {
  @IsString() apiKey!: string;
  @IsString() baseUrl!: string;
  @IsString() model!: string;
}

class ChatMessageDto {
  @IsIn(['user', 'assistant', 'system']) role!: 'user' | 'assistant' | 'system';
  @IsString() content!: string;
}

class ChatCompletionsDto {
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => ChatMessageDto)
  messages!: ChatMessageDto[];
}

const MODEL_PRESETS = [
  { provider: 'OpenAI', baseUrl: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { provider: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { provider: 'Moonshot', baseUrl: 'https://api.moonshot.cn/v1', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'] },
  { provider: 'Qwen', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-turbo', 'qwen-plus', 'qwen-max'] },
  { provider: 'GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', models: ['glm-4-flash', 'glm-4', 'glm-4-plus'] },
  { provider: 'Yi', baseUrl: 'https://api.lingyiwanwu.com/v1', models: ['yi-lightning', 'yi-large', 'yi-medium'] },
];

@Controller('chat')
export class ChatController {
  constructor(
    private readonly chatService: ChatService,
    private readonly preferencesService: PreferencesService,
  ) {}

  @Get('config')
  async getConfig(@Req() req: { user?: any }) {
    const userId = req.user?.sub ?? req.user?.id ?? '';
    const config = await this.preferencesService.getMaskedLlmConfig(String(userId));
    return { success: true, data: config };
  }

  @Post('config')
  async saveConfig(@Req() req: { user?: any }, @Body() body: SaveLlmConfigDto) {
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

  @Post('completions')
  async completions(@Req() req: any, @Res() res: any, @Body() body: ChatCompletionsDto) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.setHeader('X-Accel-Buffering', 'no');
    res.flushHeaders();

    const userId = String(req.user?.sub ?? req.user?.id ?? '');

    try {
      for await (const event of this.chatService.streamChat(userId, body.messages)) {
        res.write(`data: ${JSON.stringify(event)}\n\n`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      res.write(`data: ${JSON.stringify({ type: 'error', message })}\n\n`);
    }

    res.end();
  }
}
