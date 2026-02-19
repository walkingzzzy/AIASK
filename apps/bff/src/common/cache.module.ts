import { Global, Module } from '@nestjs/common';
import { CommonCacheService } from './cache.service';

@Global()
@Module({
  providers: [CommonCacheService],
  exports: [CommonCacheService],
})
export class CommonCacheModule {}

