import { Controller, Get, Query, Req } from '@nestjs/common';
import { ExportService } from './export.service';

@Controller('export')
export class ExportController {
  constructor(private readonly exportService: ExportService) {}

  @Get('my-data')
  async myData(@Req() req: { user?: { id?: string; sub?: string } }) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    return { success: true, data: await this.exportService.exportUserData(userId) };
  }

  @Get('report')
  async report(@Req() req: { user?: { id?: string; sub?: string } }, @Query('period') period?: string) {
    const userId = String(req.user?.sub ?? req.user?.id ?? '');
    return { success: true, data: await this.exportService.generateReport(userId, period ?? 'monthly') };
  }
}

