import './instrument';
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { SentryGlobalFilter } from '@sentry/nestjs/setup';
import * as cookieParser from 'cookie-parser';
import { AppModule } from './app.module';
import { GlobalHttpExceptionFilter } from './common/global-http-exception.filter';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.use(cookieParser());

  const corsOrigin = process.env.CORS_ORIGIN
    ? process.env.CORS_ORIGIN.split(',').map((v) => v.trim()).filter(Boolean)
    : ['http://localhost:3000', 'http://127.0.0.1:3000'];

  app.enableCors({
    origin: corsOrigin,
    credentials: true,
  });

  const config = app.get(ConfigService);
  const port = Number(config.get('BFF_PORT', 3001));

  app.setGlobalPrefix('api');
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  app.useGlobalFilters(new SentryGlobalFilter(), new GlobalHttpExceptionFilter());

  app.enableShutdownHooks();
  await app.listen(port);
  const logger = app.get(ConfigService) && new (await import('@nestjs/common')).Logger('Bootstrap');
  logger?.log(`BFF listening on http://127.0.0.1:${port}/api`);
}

void bootstrap();
