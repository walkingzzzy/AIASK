import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { CommonCacheModule } from '../common/cache.module';
import { WsModule } from '../ws/ws.module';
import { NotificationController } from './notification.controller';
import { NotificationService } from './notification.service';
import { NotificationBridgeService } from './notification-bridge.service';

@Module({
    imports: [CommonCacheModule, WsModule, AuthModule],
    controllers: [NotificationController],
    providers: [NotificationService, NotificationBridgeService],
    exports: [NotificationService, NotificationBridgeService],
})
export class NotificationModule { }
