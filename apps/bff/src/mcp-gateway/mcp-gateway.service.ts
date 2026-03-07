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

interface PooledConnection {
  id: number;
  client: Client;
  transport: StdioClientTransport;
  busy: boolean;
  connectPromise: Promise<void> | null;
}

@Injectable()
export class McpGatewayService implements OnModuleDestroy {
  private readonly logger = new Logger(McpGatewayService.name);

  private pool: PooledConnection[] = [];
  private readonly poolSize: number;
  private waitQueue: Array<{ resolve: (conn: PooledConnection) => void }> = [];
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
    const expectedTools = Number(this.configService.get<string>('MCP_EXPECTED_TOOLS', '171'));

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
    const conn = await this.acquire();
    try {
      const result = await conn.client.callTool({ name, arguments: args });
      return this.normalizeToolResult(result);
    } catch (error) {
      if (this.isTransportError(error)) {
        this.logger.warn(`Transport error on pool[${conn.id}], recycling connection`);
        await this.recycleConnection(conn);
      }
      throw error;
    } finally {
      this.release(conn);
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
    conn.busy = false;
    const waiter = this.waitQueue.shift();
    if (waiter) {
      conn.busy = true;
      waiter.resolve(conn);
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
    const env: Record<string, string> = {
      ...Object.entries(process.env).reduce<Record<string, string>>((acc, [k, v]) => {
        if (typeof v === 'string') acc[k] = v;
        return acc;
      }, {}),
      PYTHONPATH:
        this.configService.get<string>('MCP_STDIO_PYTHONPATH') || resolve(cwd, 'src'),
      PYTHONIOENCODING:
        this.configService.get<string>('MCP_STDIO_PYTHONIOENCODING', 'utf-8'),
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

    this.logger.log(`MCP pool connection[${id}] established`);
    return { id, client, transport, busy: false, connectPromise: null };
  }

  private async recycleConnection(conn: PooledConnection): Promise<void> {
    try { await conn.transport.close(); } catch { /* ignore */ }

    const idx = this.pool.indexOf(conn);
    if (idx !== -1) {
      this.pool.splice(idx, 1);
    }

    try {
      const fresh = await this.createConnection(conn.id);
      fresh.busy = conn.busy;
      this.pool.push(fresh);

      Object.assign(conn, {
        client: fresh.client,
        transport: fresh.transport,
      });
    } catch (err) {
      this.logger.error(`Failed to recycle pool[${conn.id}]: ${err}`);
    }
  }

  private async disposeAll(): Promise<void> {
    for (const conn of this.pool) {
      try {
        await conn.transport.close();
      } catch { /* ignore */ }
    }
    this.pool = [];
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

  private normalizeToolResult(result: unknown): unknown {
    if (!result || typeof result !== 'object') return result;

    const node = result as Record<string, unknown>;

    if ('structuredContent' in node && node.structuredContent !== undefined) {
      return node.structuredContent;
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
          return JSON.parse(textBlock.text);
        } catch {
          return textBlock.text;
        }
      }
    }

    return result;
  }
}
