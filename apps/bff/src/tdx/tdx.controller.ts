import { Body, Controller, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsOptional, IsString, Matches } from 'class-validator';
import { TdxService } from './tdx.service';

class PushMessageDto {
  @IsString()
  message!: string;

  @IsOptional()
  @IsString()
  stock_code?: string;
}

class PushWarnDto {
  @IsString()
  message!: string;

  @IsOptional()
  @IsString()
  stock_code?: string;
}

class CreateWatchlistDto {
  @IsString()
  name!: string;

  @IsArray()
  @IsString({ each: true })
  stock_codes!: string[];
}

class CalculateIndicatorDto {
  @IsString()
  code!: string;

  @IsString()
  indicator!: string;

  @IsOptional()
  params?: Record<string, unknown>;
}

class ScreenStocksDto {
  @IsOptional()
  @IsString()
  formula?: string;

  @IsOptional()
  conditions?: Record<string, unknown>;
}

class ExpertSignalsQueryDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

@Controller('tdx')
export class TdxController {
  constructor(private readonly tdxService: TdxService) {}

  @Post('push-message')
  async pushMessage(
    @Body() body: PushMessageDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.tdxService.pushMessage(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('push-warn')
  async pushWarn(
    @Body() body: PushWarnDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.tdxService.pushWarn(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('create-watchlist')
  async createWatchlist(
    @Body() body: CreateWatchlistDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.tdxService.createWatchlist(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('calculate-indicator')
  async calculateIndicator(
    @Body() body: CalculateIndicatorDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.tdxService.calculateIndicator(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('screen-stocks')
  async screenStocks(
    @Body() body: ScreenStocksDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.tdxService.screenStocks(body);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('expert-signals')
  async getExpertSignals(
    @Query() query: ExpertSignalsQueryDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.tdxService.getExpertSignals(query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
