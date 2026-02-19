import { Controller, Get, Query, Req } from '@nestjs/common';
import { IsString, Matches } from 'class-validator';
import { SentimentService } from './sentiment.service';

class StockCodeDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
}

@Controller('sentiment')
export class SentimentController {
  constructor(private readonly sentimentService: SentimentService) {}

  @Get('stock')
  async stock(@Query() query: StockCodeDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.sentimentService.analyzeStock(query.code);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('fear-greed')
  async fearGreed(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.sentimentService.fearGreedIndex();
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
