import { Body, Controller, Post, Req } from '@nestjs/common';
import { IsOptional, IsString, Matches } from 'class-validator';
import { AssistantService } from './assistant.service';

class StockCodeBodyDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

class IndustryChainDto {
  @IsOptional() @IsString() keyword?: string;
  @IsOptional() @IsString() chainId?: string;
}
class DailyReportDto {
  @IsOptional() @IsString() date?: string;
}

@Controller('assistant')
export class AssistantController {
  constructor(private readonly assistantService: AssistantService) {}

  @Post('diagnosis')
  async diagnosis(
    @Body() body: StockCodeBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.diagnosis(body.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('should-buy')
  async shouldBuy(
    @Body() body: StockCodeBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.shouldBuy(body.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('should-sell')
  async shouldSell(
    @Body() body: StockCodeBodyDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.assistantService.shouldSell(body.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('industry-chain')
  async getIndustryChain(@Body() body: IndustryChainDto, @Req() req: any) {
    const data = await this.assistantService.getIndustryChain(body.keyword, body.chainId);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('daily-report')
  async generateDailyReport(@Body() body: DailyReportDto, @Req() req: any) {
    const data = await this.assistantService.generateDailyReport(body.date);
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}
