import {
  BadGatewayException,
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
  ServiceUnavailableException,
} from '@nestjs/common';
import { Observable, catchError, throwError } from 'rxjs';

@Injectable()
export class DegradeInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const http = context.switchToHttp();
    const request = http.getRequest<{ url?: string }>();

    return next.handle().pipe(
      catchError((error: unknown) => {
        if (!(error instanceof BadGatewayException)) {
          return throwError(() => error);
        }

        const response = error.getResponse();
        const detail = typeof response === 'object' && response !== null
          ? response
          : { message: String(response) };

        return throwError(
          () =>
            new ServiceUnavailableException({
              code: 'MCP_UNAVAILABLE',
              message: '上游能力暂不可用',
              degraded: true,
              acceptanceStatus: 'degraded',
              detail: {
                upstream: detail,
                fallback: {
                  enabled: true,
                  status: 'degraded',
                  fallback_reason: 'mcp_bad_gateway',
                  source_chain: ['mcp_gateway', 'none'],
                  path: request.url ?? 'UNKNOWN',
                },
              },
            }),
        );
      }),
    );
  }
}
