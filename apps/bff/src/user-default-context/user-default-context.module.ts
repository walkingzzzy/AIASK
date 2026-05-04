import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { WatchlistModule } from '../watchlist/watchlist.module';
import { PaperTradingModule } from '../paper-trading/paper-trading.module';
import { UserDefaultContextController } from './user-default-context.controller';
import { UserDefaultContextService } from './user-default-context.service';

@Module({
  imports: [AuthModule, WatchlistModule, PaperTradingModule],
  controllers: [UserDefaultContextController],
  providers: [UserDefaultContextService],
})
export class UserDefaultContextModule {}
