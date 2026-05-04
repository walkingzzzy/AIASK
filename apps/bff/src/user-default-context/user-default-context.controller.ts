import { Body, Controller, Get, Post, Req } from '@nestjs/common';
import { IsOptional, IsString, Matches } from 'class-validator';
import { UserDefaultContextService } from './user-default-context.service';

class SaveUserDefaultContextDto {
  @IsOptional()
  @IsString()
  @Matches(/^\d{6}$/, { message: 'stockCode 必须为 6 位数字' })
  stockCode?: string;

  @IsOptional() @IsString() accountId?: string;
  @IsOptional() @IsString() strategyId?: string;
  @IsOptional() @IsString() strategyName?: string;
  @IsOptional() @IsString() workspaceId?: string;
}

type RequestWithUser = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
  user?: { id?: string; sub?: string };
};

@Controller('user/default-context')
export class UserDefaultContextController {
  constructor(private readonly service: UserDefaultContextService) {}

  @Get()
  async getDefaultContext(@Req() req: RequestWithUser) {
    const data = await this.service.getDefaultContext(this.userId(req));
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post()
  async saveDefaultContext(@Body() body: SaveUserDefaultContextDto, @Req() req: RequestWithUser) {
    const data = await this.service.saveDefaultContext(this.userId(req), body);
    return { success: true, data, traceId: this.traceId(req) };
  }

  private userId(req: RequestWithUser) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  private traceId(req: RequestWithUser) {
    return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
  }
}
