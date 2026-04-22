import { Module } from '@nestjs/common';
import { BehaviorController } from './behavior.controller';
import { BehaviorService } from './behavior.service';
import { BehaviorStore } from './behavior.store';

@Module({
  controllers: [BehaviorController],
  providers: [BehaviorStore, BehaviorService],
  exports: [BehaviorService],
})
export class BehaviorModule {}
