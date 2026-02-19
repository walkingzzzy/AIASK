import { Body, Controller, Delete, Get, Post, Query, Req } from '@nestjs/common';
import { IsIn, IsNumberString, IsOptional, IsString, Matches } from 'class-validator';
import { AlertsService } from './alerts.service';

class CreateAlertDto {
  @IsString()
  @Matches(/^\d{6}$/, { message: 'code 必须为 6 位数字' })
  code!: string;

  @IsString()
  indicator!: string;

  @IsString()
  @IsIn(['>', '<', '>=', '<=', '=='], { message: 'condition 仅支持 > < >= <= ==' })
  condition!: '>' | '<' | '>=' | '<=' | '==';

  @IsNumberString({}, { message: 'value 必须为数字字符串' })
  value!: string;
}

class ListAlertsDto {
  @IsOptional()
  @IsString()
  status?: string;
}

class DeleteAlertDto {
  @IsString()
  alertId!: string;
}

@Controller('alerts')
export class AlertsController {
  constructor(private readonly alertsService: AlertsService) {}

  @Post('create')
  async create(
    @Body() body: CreateAlertDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.alertsService.create({
      code: body.code,
      indicator: body.indicator,
      condition: body.condition,
      value: Number(body.value),
    });
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return { success: true, data, traceId: String(traceId) };
  }

  @Get('list')
  async list(
    @Query() query: ListAlertsDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.alertsService.list(query.status ?? 'active');
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return { success: true, data, traceId: String(traceId) };
  }

  @Delete('delete')
  async remove(
    @Query() query: DeleteAlertDto,
    @Req() req: { traceId?: string; headers?: Record<string, string | undefined> },
  ) {
    const data = await this.alertsService.remove(query.alertId);
    const traceId =
      req.traceId || req.headers?.['x-trace-id'] || req.headers?.['x-request-id'] || 'UNKNOWN';

    return { success: true, data, traceId: String(traceId) };
  }
}

