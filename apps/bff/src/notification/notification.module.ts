import { Module } from '@nestjs/common';
import { CommonCacheModule } from '../common/cache.module';
import { WsModule } from '../ws/ws.module';
import { NotificationController } from './notification.controller';
import { NotificationService } from './notification.service';
import { NotificationBridgeService } from './notification-bridge.service';

@Module({
    imports: [CommonCacheModule, WsModule],
    controllers: [NotificationController],
    providers: [NotificationService, NotificationBridgeService],
    exports: [NotificationService, NotificationBridgeService],
})
export class NotificationModule { }
