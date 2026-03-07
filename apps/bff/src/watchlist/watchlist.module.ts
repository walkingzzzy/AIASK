import { Module } from '@nestjs/common';
import { McpGatewayModule } from '../mcp-gateway/mcp-gateway.module';
import { CommonCacheModule } from '../common/cache.module';
import { WatchlistController } from './watchlist.controller';
import { WatchlistService } from './watchlist.service';

@Module({
    imports: [McpGatewayModule, CommonCacheModule],
    controllers: [WatchlistController],
    providers: [WatchlistService],
    exports: [WatchlistService],
})
export class WatchlistModule { }
