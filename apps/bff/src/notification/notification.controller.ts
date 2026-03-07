import { Body, Controller, Delete, Get, Post, Query, Req } from '@nestjs/common';
import { IsArray, IsEnum, IsNumber, IsOptional, IsString } from 'class-validator';
import { Type } from 'class-transformer';
import { NotificationService, NotificationType } from './notification.service';

class ListNotificationsDto {
    @IsOptional()
    @IsEnum(['alert', 'signal', 'trade', 'system', 'news'])
    type?: NotificationType;

    @IsOptional()
    @Type(() => Number)
    @IsNumber()
    limit?: number;

    @IsOptional()
    @Type(() => Number)
    @IsNumber()
    offset?: number;
}

class MarkReadDto {
    @IsArray()
    @IsString({ each: true })
    ids!: string[];
}

class DeleteNotificationsDto {
    @IsArray()
    @IsString({ each: true })
    ids!: string[];
}

@Controller('notifications')
export class NotificationController {
    constructor(private readonly notificationService: NotificationService) { }

    private userId(req: { user?: { id?: string; sub?: string } }) {
        return String(req.user?.sub ?? req.user?.id ?? '');
    }

    @Get('list')
    async list(@Req() req: { user?: { id?: string; sub?: string } }, @Query() query: ListNotificationsDto) {
        const result = await this.notificationService.list(this.userId(req), {
            type: query.type,
            limit: query.limit,
            offset: query.offset,
        });
        return { success: true, data: result };
    }

    @Get('unread-count')
    async unreadCount(@Req() req: { user?: { id?: string; sub?: string } }) {
        const count = await this.notificationService.countUnread(this.userId(req));
        return { success: true, data: { count } };
    }

    @Post('mark-read')
    async markRead(@Req() req: { user?: { id?: string; sub?: string } }, @Body() body: MarkReadDto) {
        const count = await this.notificationService.markRead(this.userId(req), body.ids);
        return { success: true, data: { markedCount: count } };
    }

    @Post('mark-all-read')
    async markAllRead(@Req() req: { user?: { id?: string; sub?: string } }) {
        const count = await this.notificationService.markAllRead(this.userId(req));
        return { success: true, data: { markedCount: count } };
    }

    @Delete('delete')
    async remove(@Req() req: { user?: { id?: string; sub?: string } }, @Body() body: DeleteNotificationsDto) {
        const count = await this.notificationService.remove(this.userId(req), body.ids);
        return { success: true, data: { deletedCount: count } };
    }
}
