import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { PaperTradingModule } from '../paper-trading/paper-trading.module';
import { WatchlistModule } from '../watchlist/watchlist.module';
import { ResearchModule } from '../research/research.module';
import { NotificationModule } from '../notification/notification.module';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { ExportController } from './export.controller';
import { ExportService } from './export.service';

@Module({
  imports: [AuthModule, PaperTradingModule, WatchlistModule, ResearchModule, NotificationModule, McpGatewayModule],
  controllers: [ExportController],
  providers: [ExportService],
  exports: [ExportService],
})
export class ExportModule {}

