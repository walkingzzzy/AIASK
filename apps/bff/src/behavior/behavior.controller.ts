import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsInt,
  IsObject,
  IsOptional,
  IsString,
  Max,
  Min,
  ValidateNested,
} from 'class-validator';
import { BehaviorService } from './behavior.service';

class BehaviorEventDto {
  @IsOptional() @IsString() sessionId?: string;
  @IsString() pageKey!: string;
  @IsString() route!: string;
  @IsString() eventType!: string;
  @IsOptional() @IsString() targetType?: string;
  @IsOptional() @IsString() targetLabel?: string;
  @IsOptional() @IsString() targetId?: string;
  @IsOptional() @IsString() targetTestId?: string;
  @IsOptional() @IsObject() payload?: Record<string, unknown>;
  @IsOptional() @IsString() source?: string;
  @IsOptional() @IsString() occurredAt?: string;
}

class BatchBehaviorEventsDto {
  @IsOptional() @IsString() sessionId?: string;

  @IsArray()
  @ArrayMaxSize(100)
  @ValidateNested({ each: true })
  @Type(() => BehaviorEventDto)
  events!: BehaviorEventDto[];
}

class BehaviorQueryDto {
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(200)
  limit?: number;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(30)
  days?: number;

  @IsOptional() @IsString() source?: string;
  @IsOptional() @IsString() pageKey?: string;
  @IsOptional() @IsString() eventType?: string;
}

type AuthenticatedRequest = {
  user?: { id?: string; sub?: string };
};

@Controller('behavior')
export class BehaviorController {
  constructor(private readonly behaviorService: BehaviorService) {}

  @Post('events')
  async append(@Req() req: AuthenticatedRequest, @Body() body: BatchBehaviorEventsDto) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const sessionId = String(body.sessionId ?? '').trim();
    const stored = await this.behaviorService.append(
      userId,
      body.events.map((event) => ({
        ...event,
        sessionId: String(event.sessionId ?? sessionId ?? '').trim(),
      })),
    );
    return {
      success: true,
      data: { stored },
    };
  }

  @Get('summary')
  async summary(@Req() req: AuthenticatedRequest, @Query() query: BehaviorQueryDto) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const summary = await this.behaviorService.getRecentSummary(userId, {
      limit: query.limit ?? 20,
      days: query.days ?? 30,
    });
    return {
      success: true,
      data: summary,
    };
  }

  @Get('events')
  async list(@Req() req: AuthenticatedRequest, @Query() query: BehaviorQueryDto) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    const items = await this.behaviorService.listByUser(userId, {
      limit: query.limit ?? 50,
      days: query.days ?? 30,
      source: query.source ?? null,
      pageKey: query.pageKey ?? null,
      eventType: query.eventType ?? null,
    });
    return {
      success: true,
      data: {
        items,
        limit: query.limit ?? 50,
        days: query.days ?? 30,
      },
    };
  }
}
