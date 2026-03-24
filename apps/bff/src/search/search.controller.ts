import { Controller, Get, Query, Req } from '@nestjs/common';
import { Type } from 'class-transformer';
import { IsInt, IsOptional, IsString, Matches, Max, Min } from 'class-validator';
import { SearchService } from './search.service';

export class SimilarDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) topN?: number;
  @IsOptional() @IsString() type?: string;
}

export class SemanticDto {
  @IsString() query!: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) limit?: number;
}

export class KlineSearchDto {
  @IsString() @Matches(/^\d{6}$/) code!: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) @Max(200) topN?: number;
}

@Controller('search')
export class SearchController {
  constructor(private readonly searchService: SearchService) {}

  @Get('similar')
  async similar(
    @Query() query: SimilarDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.searchService.similarStocks(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('semantic')
  async semantic(
    @Query() query: SemanticDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.searchService.semanticSearch(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('vector-kline')
  async vectorKline(
    @Query() query: KlineSearchDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.searchService.searchByKline(query);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
