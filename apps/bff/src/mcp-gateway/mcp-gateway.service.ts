import { Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

type McpHealth = {
  reachable: boolean;
  toolCount: number | null;
  expectedTools: number;
  matched: boolean;
  source: string;
  message: string;
  poolSize?: number;
  activeConnections?: number;
};

type McpStartupProfile = 'full' | 'tool-only';

interface PooledConnection {
  id: number;
  client: Client;
  transport: StdioClientTransport;
  busy: boolean;
  connectPromise: Promise<void> | null;
}

type DedicatedWaiter = { resolve: (conn: PooledConnection) => void };

@Injectable()
export class McpGatewayService implements OnModuleDestroy {
  private readonly logger = new Logger(McpGatewayService.name);
  private static readonly DEDICATED_TOOL_CONNECTIONS = new Set(['alerts_manager']);

  private pool: PooledConnection[] = [];
  private readonly poolSize: number;
  private waitQueue: Array<{ resolve: (conn: PooledConnection) => void }> = [];
  private dedicatedConnections = new Map<string, PooledConnection>();
  private dedicatedWaitQueues = new Map<string, DedicatedWaiter[]>();
  private initialized = false;

  constructor(private readonly configService: ConfigService) {
    this.poolSize = Math.max(
      1,
      Number(this.configService.get<string>('MCP_POOL_SIZE', '3')),
    );
  }

  async onModuleDestroy(): Promise<void> {
    await this.disposeAll();
  }

  async checkAvailableTools(): Promise<McpHealth> {
    const defaultExpectedTools = process.platform === 'win32' ? '171' : '134';
    const expectedTools = Number(
      this.configService.get<string>('MCP_EXPECTED_TOOLS', defaultExpectedTools),
    );

    try {
      const conn = await this.acquire();
      try {
        const tools = await conn.client.listTools();
        const count = Array.isArray(tools?.tools) ? tools.tools.length : null;
        if (count !== null) {
          return {
            reachable: true,
            toolCount: count,
            expectedTools,
            matched: count === expectedTools,
            source: 'stdio',
            message: 'ok',
            poolSize: this.poolSize,
            activeConnections: this.pool.length,
          };
        }
      } finally {
        this.release(conn);
      }
    } catch {
      // ignore and fallthrough
    }

    return {
      reachable: false,
      toolCount: null,
      expectedTools,
      matched: false,
      source: 'none',
      message: 'MCP not reachable or available_tools response format unknown',
      poolSize: this.poolSize,
      activeConnections: this.pool.length,
    };
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
    const dedicated = McpGatewayService.DEDICATED_TOOL_CONNECTIONS.has(name);
    const conn = dedicated ? await this.acquireDedicated(name) : await this.acquire();
    try {
      const result = await conn.client.callTool({ name, arguments: args });
      return this.normalizeToolResult(result);
    } catch (error) {
      if (this.isTransportError(error)) {
        this.logger.warn(`Transport error on pool[${conn.id}], recycling connection`);
        await this.recycleConnection(conn, dedicated ? name : undefined);
      }
      throw error;
    } finally {
      if (dedicated) this.releaseDedicated(name, conn);
      else this.release(conn);
    }
  }

  /* ── Pool Management ── */

  private async acquire(): Promise<PooledConnection> {
    if (!this.initialized) {
      await this.initPool();
    }

    const idle = this.pool.find((c) => !c.busy);
    if (idle) {
      idle.busy = true;
      return idle;
    }

    if (this.pool.length < this.poolSize) {
      const conn = await this.createConnection(this.pool.length);
      conn.busy = true;
      this.pool.push(conn);
      return conn;
    }

    return new Promise<PooledConnection>((resolve) => {
      this.waitQueue.push({ resolve });
    });
  }

  private release(conn: PooledConnection): void {
    if (!this.pool.includes(conn)) {
      const waiter = this.waitQueue.shift();
      if (waiter) {
        void this.acquire()
          .then((nextConn) => waiter.resolve(nextConn))
          .catch((error) => {
            this.logger.error(`Failed to reacquire MCP connection for waiter: ${String(error)}`);
            this.waitQueue.unshift(waiter);
          });
      }
      return;
    }

    conn.busy = false;
    const waiter = this.waitQueue.shift();
    if (waiter) {
      conn.busy = true;
      waiter.resolve(conn);
    }
  }

  private async acquireDedicated(toolName: string): Promise<PooledConnection> {
    const existing = this.dedicatedConnections.get(toolName);
    if (existing) {
      if (!existing.busy) {
        existing.busy = true;
        return existing;
      }
      return new Promise<PooledConnection>((resolve) => {
        const queue = this.dedicatedWaitQueues.get(toolName) ?? [];
        queue.push({ resolve });
        this.dedicatedWaitQueues.set(toolName, queue);
      });
    }

    const conn = await this.createConnection(this.poolSize + this.dedicatedConnections.size);
    conn.busy = true;
    this.dedicatedConnections.set(toolName, conn);
    this.logger.log(`MCP dedicated connection[${conn.id}] assigned to ${toolName}`);
    return conn;
  }

  private releaseDedicated(toolName: string, conn: PooledConnection): void {
    const current = this.dedicatedConnections.get(toolName);
    if (current !== conn) return;

    conn.busy = false;
    const queue = this.dedicatedWaitQueues.get(toolName);
    const waiter = queue?.shift();
    if (waiter) {
      conn.busy = true;
      waiter.resolve(conn);
    }
    if (queue && queue.length === 0) {
      this.dedicatedWaitQueues.delete(toolName);
    }
  }

  private async initPool(): Promise<void> {
    if (this.initialized) return;
    this.initialized = true;

    const first = await this.createConnection(0);
    this.pool.push(first);
    this.logger.log(`MCP pool initialized (1/${this.poolSize} connections, lazy expansion)`);
  }

  private async createConnection(id: number): Promise<PooledConnection> {
    const cwd = this.resolveMcpCwd();
    const command = this.configService.get<string>('MCP_STDIO_COMMAND', 'python');
    const args = this.parseArgs(
      this.configService.get<string>('MCP_STDIO_ARGS', '["-m","akshare_mcp.server"]'),
    );
    const startupProfile = this.resolveStartupProfile(id);
    const env: Record<string, string> = {
      ...Object.entries(process.env).reduce<Record<string, string>>((acc, [k, v]) => {
        if (typeof v === 'string') acc[k] = v;
        return acc;
      }, {}),
      PYTHONPATH:
        this.configService.get<string>('MCP_STDIO_PYTHONPATH') || resolve(cwd, 'src'),
      PYTHONIOENCODING:
        this.configService.get<string>('MCP_STDIO_PYTHONIOENCODING', 'utf-8'),
      AKSHARE_MCP_STARTUP_PROFILE: startupProfile,
      AKSHARE_MCP_CONNECTION_SLOT: String(id),
    };

    const transport = new StdioClientTransport({
      command,
      args,
      cwd,
      env,
      stderr: 'inherit',
    });

    const client = new Client(
      { name: `aiask-bff-pool-${id}`, version: '0.1.0' },
      { capabilities: {} },
    );

    try {
      await client.connect(transport);
    } catch (error) {
      try { await transport.close(); } catch { /* ignore */ }
      throw error;
    }

    this.logger.log(`MCP pool connection[${id}] established (profile=${startupProfile})`);
    return { id, client, transport, busy: false, connectPromise: null };
  }

  private async recycleConnection(conn: PooledConnection, dedicatedTool?: string): Promise<void> {
    try { await conn.transport.close(); } catch { /* ignore */ }

    try {
      const fresh = await this.createConnection(conn.id);
      conn.client = fresh.client;
      conn.transport = fresh.transport;
      conn.connectPromise = fresh.connectPromise;
    } catch (err) {
      if (dedicatedTool) {
        this.dedicatedConnections.delete(dedicatedTool);
      } else {
        const idx = this.pool.indexOf(conn);
        if (idx !== -1) {
          this.pool.splice(idx, 1);
        }
      }
      this.logger.error(`Failed to recycle pool[${conn.id}]: ${err}`);
    }
  }

  private async disposeAll(): Promise<void> {
    for (const conn of this.pool) {
      try {
        await conn.transport.close();
      } catch { /* ignore */ }
    }
    for (const conn of this.dedicatedConnections.values()) {
      try {
        await conn.transport.close();
      } catch { /* ignore */ }
    }
    this.pool = [];
    this.dedicatedConnections.clear();
    this.dedicatedWaitQueues.clear();
    this.initialized = false;
  }

  /* ── Utilities ── */

  private isTransportError(error: unknown): boolean {
    if (!error || typeof error !== 'object') return true;
    const msg = String((error as Error).message ?? '').toLowerCase();
    return (
      msg.includes('epipe') ||
      msg.includes('connection') ||
      msg.includes('closed') ||
      msg.includes('transport') ||
      msg.includes('econnreset') ||
      msg.includes('econnrefused') ||
      msg.includes('broken pipe')
    );
  }

  private resolveMcpCwd(): string {
    const configured = this.configService.get<string>('MCP_STDIO_CWD');
    if (configured && configured.trim().length > 0) {
      return configured.trim();
    }

    const fromRepoRoot = resolve(process.cwd(), 'packages', 'akshare-mcp');
    if (existsSync(fromRepoRoot)) return fromRepoRoot;

    const fromAppDir = resolve(process.cwd(), '..', '..', 'packages', 'akshare-mcp');
    if (existsSync(fromAppDir)) return fromAppDir;

    return fromRepoRoot;
  }

  private parseArgs(raw: string): string[] {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.every((item) => typeof item === 'string')) {
        return parsed;
      }
    } catch {
      // fallback below
    }

    return raw
      .split(' ')
      .map((part) => part.trim())
      .filter((part) => part.length > 0);
  }

  private resolveStartupProfile(id: number): McpStartupProfile {
    const raw = this.configService.get<string>('MCP_STDIO_STARTUP_PROFILE', 'balanced').trim().toLowerCase();
    if (raw === 'full') return 'full';
    if (raw === 'tool-only' || raw === 'tool_only' || raw === 'worker') return 'tool-only';
    return id === 0 ? 'full' : 'tool-only';
  }

  private withFallbackMetaDefaults(payload: unknown): unknown {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      return payload;
    }

    const node = payload as Record<string, unknown>;
    const hasFallbackShape =
      'backend_requested' in node ||
      'backend_used' in node ||
      'fallback_used' in node ||
      'fallback_reason' in node ||
      'latency_ms' in node ||
      'source' in node;

    if (!hasFallbackShape) {
      const nestedData = node.data;
      if (nestedData && typeof nestedData === 'object' && !Array.isArray(nestedData)) {
        const normalizedData = this.withFallbackMetaDefaults(nestedData) as Record<string, unknown>;
        const nestedHasFallbackShape =
          normalizedData &&
          typeof normalizedData === 'object' &&
          !Array.isArray(normalizedData) &&
          ('backend_requested' in normalizedData ||
            'backend_used' in normalizedData ||
            'fallback_used' in normalizedData ||
            'fallback_reason' in normalizedData ||
            'latency_ms' in normalizedData);

        if (nestedHasFallbackShape) {
          return {
            ...node,
            data: normalizedData,
            backend_requested: normalizedData.backend_requested ?? null,
            backend_used: normalizedData.backend_used ?? null,
            fallback_used:
              typeof normalizedData.fallback_used === 'boolean'
                ? normalizedData.fallback_used
                : false,
            fallback_reason: normalizedData.fallback_reason ?? null,
            latency_ms:
              typeof normalizedData.latency_ms === 'number'
                ? normalizedData.latency_ms
                : 0,
          };
        }
      }

      return payload;
    }

    const backendRequested =
      typeof node.backend_requested === 'string' && node.backend_requested.length > 0
        ? node.backend_requested
        : typeof node.backend_used === 'string' && node.backend_used.length > 0
          ? node.backend_used
          : typeof node.source === 'string' && node.source.length > 0
            ? node.source
            : 'unknown';

    const backendUsed =
      typeof node.backend_used === 'string' && node.backend_used.length > 0
        ? node.backend_used
        : typeof node.source === 'string' && node.source.length > 0
          ? node.source
          : 'unknown';

    const fallbackUsed =
      typeof node.fallback_used === 'boolean'
        ? node.fallback_used
        : backendRequested !== backendUsed;

    const latencyMs = typeof node.latency_ms === 'number' ? node.latency_ms : 0;

    return {
      ...node,
      backend_requested: backendRequested,
      backend_used: backendUsed,
      fallback_used: fallbackUsed,
      fallback_reason: node.fallback_reason ?? null,
      latency_ms: latencyMs,
    };
  }

  private normalizeToolResult(result: unknown): unknown {
    if (!result || typeof result !== 'object') return result;

    const node = result as Record<string, unknown>;

    if ('structuredContent' in node && node.structuredContent !== undefined) {
      return this.withFallbackMetaDefaults(node.structuredContent);
    }

    if (Array.isArray(node.content)) {
      const textBlock = node.content.find(
        (item) =>
          item &&
          typeof item === 'object' &&
          (item as Record<string, unknown>).type === 'text' &&
          typeof (item as Record<string, unknown>).text === 'string',
      ) as Record<string, unknown> | undefined;

      if (textBlock?.text && typeof textBlock.text === 'string') {
        try {
          return this.withFallbackMetaDefaults(JSON.parse(textBlock.text));
        } catch {
          return textBlock.text;
        }
      }
    }

    return this.withFallbackMetaDefaults(result);
  }
}
