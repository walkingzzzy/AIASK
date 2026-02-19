import { Body, Controller, Delete, Get, Post, Query, Req } from '@nestjs/common';
import { IsNumberString, IsOptional, IsString, Matches } from 'class-validator';
import { PortfolioService } from './portfolio.service';

class CreatePortfolioDto {
  @IsString()
  name!: string;

  @IsOptional()
  @IsString()
  description?: string;

  @IsOptional()
  @IsNumberString({}, { message: 'initialCapital 必须为数字字符串' })
  initialCapital?: string;
}

class PortfolioIdDto {
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId!: string;
}

class AddHoldingDto {
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId!: string;

  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsNumberString({}, { message: 'shares 必须为数字字符串' })
  shares!: string;

  @IsNumberString({}, { message: 'costPrice 必须为数字字符串' })
  costPrice!: string;
}

class RemoveHoldingDto {
  @IsNumberString({}, { message: 'portfolioId 必须为数字字符串' })
  portfolioId!: string;

  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;
}

@Controller('portfolio')
export class PortfolioController {
  constructor(private readonly portfolioService: PortfolioService) {}

  @Get('list')
  async list(@Req() req: { traceId?: string; headers?: Record<string, string | undefined> }) {
    const data = await this.portfolioService.list();
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('create')
  async create(
    @Body() body: CreatePortfolioDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.create({
      name: body.name,
      description: body.description,
      initialCapital: body.initialCapital ? Number(body.initialCapital) : undefined,
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Get('get')
  async get(
    @Query() query: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.get(Number(query.portfolioId));
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('add-holding')
  async addHolding(
    @Body() body: AddHoldingDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.addHolding({
      portfolioId: Number(body.portfolioId),
      code: body.code,
      shares: Number(body.shares),
      costPrice: Number(body.costPrice),
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Delete('remove-holding')
  async removeHolding(
    @Query() query: RemoveHoldingDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.removeHolding(Number(query.portfolioId), query.code);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('optimize')
  async optimize(
    @Body() body: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.optimize(Number(body.portfolioId));
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('risk-analysis')
  async riskAnalysis(
    @Body() body: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.riskAnalysis(Number(body.portfolioId));
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }

  @Post('stress-test')
  async stressTest(
    @Body() body: PortfolioIdDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.portfolioService.stressTest(Number(body.portfolioId));
    const traceId = req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';
    return { success: true, data, traceId: String(traceId) };
  }
}

