import { Controller, Get, Query } from '@nestjs/common';
import { Type } from 'class-transformer';
import { IsInt, IsOptional, Max, Min } from 'class-validator';
import { AuditStore } from './audit.store';
import { Roles } from '../rbac/roles.decorator';

class ListAuditQueryDto {
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(200)
  limit?: number;
}

@Controller('audit')
export class AuditController {
  constructor(private readonly auditStore: AuditStore) {}

  @Get('logs')
  @Roles('admin')
  async listLogs(@Query() query: ListAuditQueryDto) {
    const limit = query.limit ?? 20;
    return {
      success: true,
      data: {
        items: await this.auditStore.list(limit),
        limit,
      },
    };
  }
}

