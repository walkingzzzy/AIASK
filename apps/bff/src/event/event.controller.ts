import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsIn, IsNumberString, IsOptional, IsString, Matches } from 'class-validator';
import { EventService } from './event.service';

class EventByCodeQueryDto {
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsOptional()
  @IsNumberString({}, { message: 'limit 必须为数字字符串' })
  limit?: string;
}

class EventCalendarQueryDto {
  @IsOptional()
  @IsNumberString({}, { message: 'days 必须为数字字符串' })
  days?: string;

  @IsOptional()
  @IsString()
  type?: string;
}

class EventImportantQueryDto {
  @IsOptional()
  @IsNumberString({}, { message: 'days 必须为数字字符串' })
  days?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'limit 必须为数字字符串' })
  limit?: string;
}

class EventSubscribeDto {
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsOptional()
  @IsString()
  name?: string;
}

class EventPreferencesDto {
  /** 通知频率：realtime / daily / weekly */
  @IsOptional()
  @IsIn(['realtime', 'daily', 'weekly'])
  frequency?: 'realtime' | 'daily' | 'weekly';

  /** 订阅的事件类型，逗号分隔，如 "notice,report,dividend,ipo" */
  @IsOptional()
  @IsString()
  eventTypes?: string;

  /** 最低重要性阈值 1-5 */
  @IsOptional()
  @IsNumberString({}, { message: 'minImportance 必须为数字字符串' })
  minImportance?: string;
}

type RequestWithUser = {
  traceId?: string;
  headers?: Record<string, string | undefined>;
  user?: { id?: string; sub?: string };
};

@Controller('event')
export class EventController {
  constructor(private readonly eventService: EventService) {}

  private userId(req: RequestWithUser) {
    return String(req.user?.sub ?? req.user?.id ?? 'default');
  }

  private traceId(req: RequestWithUser) {
    return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
  }

  @Get('by-code')
  async byCode(@Query() query: EventByCodeQueryDto, @Req() req: RequestWithUser) {
    const data = await this.eventService.byCode(query.code, query.limit ? Number(query.limit) : 20);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('calendar')
  async calendar(@Query() query: EventCalendarQueryDto, @Req() req: RequestWithUser) {
    const data = await this.eventService.calendar(query.days ? Number(query.days) : 7, query.type ?? 'all');
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('important')
  async important(@Query() query: EventImportantQueryDto, @Req() req: RequestWithUser) {
    const data = await this.eventService.important(
      this.userId(req),
      query.days ? Number(query.days) : 7,
      query.limit ? Number(query.limit) : 12,
    );
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('subscriptions')
  async subscriptions(@Req() req: RequestWithUser) {
    const data = await this.eventService.subscriptions(this.userId(req));
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('subscribe')
  async subscribe(@Body() body: EventSubscribeDto, @Req() req: RequestWithUser) {
    const data = await this.eventService.subscribe(this.userId(req), body.code, body.name);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('unsubscribe')
  async unsubscribe(@Body() body: EventSubscribeDto, @Req() req: RequestWithUser) {
    const data = await this.eventService.unsubscribe(this.userId(req), body.code);
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Get('preferences')
  async getPreferences(@Req() req: RequestWithUser) {
    const data = await this.eventService.getPreferences(this.userId(req));
    return { success: true, data, traceId: this.traceId(req) };
  }

  @Post('preferences')
  async updatePreferences(@Body() body: EventPreferencesDto, @Req() req: RequestWithUser) {
    const patch = {
      frequency: body.frequency,
      eventTypes: body.eventTypes ? body.eventTypes.split(',').map((s) => s.trim()).filter(Boolean) : undefined,
      minImportance: body.minImportance ? Number(body.minImportance) : undefined,
    };
    const data = await this.eventService.updatePreferences(this.userId(req), patch);
    return { success: true, data, traceId: this.traceId(req) };
  }
}
