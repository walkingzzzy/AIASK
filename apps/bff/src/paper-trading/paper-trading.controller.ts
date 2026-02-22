import { Body, Controller, Delete, Get, Post, Query, Req } from '@nestjs/common';
import { IsInt, IsNumber, IsOptional, IsString, Min } from 'class-validator';
import { Type } from 'class-transformer';
import { Throttle } from '@nestjs/throttler';
import { PaperTradingService } from './paper-trading.service';

class PlaceOrderDto {
  @IsString() code!: string;
  @IsString() direction!: string;
  @Type(() => Number) @IsInt() @Min(1) quantity!: number;
  @IsOptional() @Type(() => Number) @IsNumber() price?: number;
  @IsOptional() @IsString() order_type?: string;
  @IsOptional() @Type(() => Number) @IsNumber() stop_price?: number;
  @IsOptional() @IsString() account_id?: string;
}

class CancelOrderDto {
  @IsString() order_id!: string;
}

class RiskRulesDto {
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @Type(() => Number) @IsNumber() max_position_pct?: number;
  @IsOptional() @Type(() => Number) @IsNumber() max_drawdown_pct?: number;
  @IsOptional() @Type(() => Number) @IsNumber() stop_loss_pct?: number;
}

class OrderEventsQueryDto {
  @IsOptional() @IsString() order_id?: string;
  @IsOptional() @IsString() account_id?: string;
  @IsOptional() @Type(() => Number) @IsInt() @Min(1) limit?: number;
}

type Req_ = { traceId?: string; headers?: Record<string, string | undefined>; user?: { id?: string } };

function traceId(req: Req_): string {
  return String(req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN');
}

function userId(req: Req_): string {
  return req.user?.id || 'default';
}

@Controller('paper-trading')
export class PaperTradingController {
  constructor(private readonly svc: PaperTradingService) {}

  @Get('accounts')
  async listAccounts(@Req() req: Req_) {
    const data = await this.svc.listAccounts(userId(req));
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('summary')
  async summary(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.summary(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('positions')
  async positions(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.positions(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('orders')
  async orders(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.orders(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('order-events')
  async orderEvents(@Query() query: OrderEventsQueryDto, @Req() req: Req_) {
    const data = await this.svc.orderEvents(userId(req), query);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('pending-orders')
  async pendingOrders(@Query('account_id') accountId: string, @Req() req: Req_) {
    const data = await this.svc.pendingOrders(userId(req), accountId);
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('order')
  @Throttle({ default: { ttl: 1000, limit: 10 } })
  async placeOrder(@Body() body: PlaceOrderDto, @Req() req: Req_) {
    const data = await this.svc.placeOrder(userId(req), body);
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('cancel')
  async cancelOrder(@Body() body: CancelOrderDto, @Req() req: Req_) {
    const data = await this.svc.cancelOrder(userId(req), body.order_id);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('nav-history')
  async navHistory(
    @Query('account_id') accountId: string,
    @Query('limit') limit: string,
    @Req() req: Req_,
  ) {
    const data = await this.svc.navHistory(userId(req), accountId, limit ? Number(limit) : undefined);
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('matching-status')
  async matchingStatus(@Req() req: Req_) {
    const data = await this.svc.matchingStatus();
    return { success: true, data, traceId: traceId(req) };
  }

  @Get('nav-status')
  async navStatus(@Req() req: Req_) {
    const data = await this.svc.navStatus();
    return { success: true, data, traceId: traceId(req) };
  }

  @Post('risk-rules')
  async setRiskRules(@Body() body: RiskRulesDto, @Req() req: Req_) {
    const data = await this.svc.setRiskRules(userId(req), body);
    return { success: true, data, traceId: traceId(req) };
  }
}
