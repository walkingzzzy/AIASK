import { Controller, Get, Query, Req } from '@nestjs/common';
import { IsNumber, IsOptional, IsString, Matches } from 'class-validator';
import { SearchService } from './search.service';

class SimilarDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsNumber() topN?: number;
  @IsOptional() @IsString() type?: string;
}

class SemanticDto {
  @IsString() query!: string;
  @IsOptional() @IsNumber() limit?: number;
}

class KlineSearchDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @IsNumber() topN?: number;
}

@Controller('search')
export class SearchController {
  constructor(private readonly searchService: SearchService) {}

  @Get('similar')
  async similar(@Query() query: SimilarDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.searchService.similarStocks(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('semantic')
  async semantic(@Query() query: SemanticDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.searchService.semanticSearch(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('vector-kline')
  async vectorKline(@Query() query: KlineSearchDto, @Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.searchService.searchByKline(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
