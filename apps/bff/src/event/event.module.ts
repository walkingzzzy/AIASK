import { Module } from '@nestjs/common';
import { EventController } from './event.controller';
import { EventService } from './event.service';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { NotificationModule } from '../notification/notification.module';
import { WatchlistModule } from '../watchlist/watchlist.module';

@Module({
  imports: [McpGatewayModule, WatchlistModule, NotificationModule],
  controllers: [EventController],
  providers: [EventService],
})
export class EventModule {}
