import {
  BadGatewayException,
  CallHandler,
  ExecutionContext,
  Injectable,
  NestInterceptor,
  ServiceUnavailableException,
} from '@nestjs/common';
import type { AcceptanceStatus } from '@aiask/shared-types';
import { Observable, catchError, throwError } from 'rxjs';
import { McpGatewayService } from '../mcp-gateway/mcp-gateway.service';
import { buildMcpTransportFailureDetail } from '../mcp-gateway/mcp-transport.contract';
import { buildUnavailableException } from './acceptance';

const DEGRADED_ROUTE_PREFIXES = ['/health', '/observability', '/admin', '/audit'];

function allowsDegradedResponse(pathname: string) {
  return DEGRADED_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

@Injectable()
export class DegradeInterceptor implements NestInterceptor {
  constructor(private readonly mcpGatewayService: McpGatewayService) {}

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
        const pathname = String(request.url ?? 'UNKNOWN').split('?')[0];
        const transportDetail = buildMcpTransportFailureDetail(
          this.mcpGatewayService.getTransportSnapshot(),
          {
            acceptanceStatus: allowsDegradedResponse(pathname) ? 'degraded' : 'unavailable',
            path: pathname,
            upstream: detail,
          },
        );

        if (!allowsDegradedResponse(pathname)) {
          return throwError(() =>
            buildUnavailableException(
              transportDetail,
              { code: 'MCP_UNAVAILABLE' },
            ),
          );
        }

        return throwError(
          () =>
            new ServiceUnavailableException({
              code: 'MCP_UNAVAILABLE',
              message: '上游能力暂不可用',
              degraded: true,
              acceptanceStatus: 'degraded' satisfies AcceptanceStatus,
              detail: transportDetail,
            }),
        );
      }),
    );
  }
}
