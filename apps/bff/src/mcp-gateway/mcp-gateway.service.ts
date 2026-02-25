import { Injectable, OnModuleDestroy } from '@nestjs/common';
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
};

@Injectable()
export class McpGatewayService implements OnModuleDestroy {
  private client: Client | null = null;
  private transport: StdioClientTransport | null = null;
  private connected = false;
  private connectPromise: Promise<void> | null = null;

  /* ── Semaphore: serialize stdio calls (concurrency=1) ── */
  private semaphoreQueue: Array<{ resolve: () => void }> = [];
  private semaphoreRunning = 0;
  private readonly maxConcurrency = 1;

  constructor(private readonly configService: ConfigService) {}

  async onModuleDestroy(): Promise<void> {
    await this.disposeClient();
  }

  async checkAvailableTools(): Promise<McpHealth> {
    const expectedTools = Number(this.configService.get<string>('MCP_EXPECTED_TOOLS', '158'));

    try {
      await this.ensureConnected();
      const tools = await this.client!.listTools();
      const count = Array.isArray(tools?.tools) ? tools.tools.length : null;
      if (count !== null) {
        return {
          reachable: true,
          toolCount: count,
          expectedTools,
          matched: count === expectedTools,
          source: 'stdio',
          message: 'ok',
        };
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
    };
  }

  async callTool(name: string, args: Record<string, unknown> = {}): Promise<unknown> {
    await this.acquire();
    try {
      await this.ensureConnected();
      const result = await this.client!.callTool({ name, arguments: args });
      return this.normalizeToolResult(result);
    } catch (error) {
      if (this.isTransportError(error)) await this.disposeClient();
      throw error;
    } finally {
      this.release();
    }
  }

  /* ── Semaphore helpers ── */
  private async acquire(): Promise<void> {
    if (this.semaphoreRunning < this.maxConcurrency) {
      this.semaphoreRunning++;
      return;
    }
    return new Promise<void>((resolve) => {
      this.semaphoreQueue.push({ resolve });
    });
  }

  private release(): void {
    const next = this.semaphoreQueue.shift();
    if (next) {
      next.resolve();
    } else {
      this.semaphoreRunning--;
    }
  }

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

  private async ensureConnected(): Promise<void> {
    if (this.connected && this.client) return;
    if (this.connectPromise) {
      await this.connectPromise;
      return;
    }

    this.connectPromise = this.connectInternal();
    try {
      await this.connectPromise;
    } finally {
      this.connectPromise = null;
    }
  }

  private async connectInternal(): Promise<void> {
    await this.disposeClient();

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
        this.configService.get<string>('MCP_STDIO_PYTHONPATH') ||
        resolve(cwd, 'src'),
      PYTHONIOENCODING:
        this.configService.get<string>('MCP_STDIO_PYTHONIOENCODING', 'utf-8'),
    };

    this.transport = new StdioClientTransport({
      command,
      args,
      cwd,
      env,
      stderr: 'inherit',
    });

    this.client = new Client({ name: 'aiask-bff', version: '0.1.0' }, { capabilities: {} });

    try {
      await this.client.connect(this.transport);
      this.connected = true;
    } catch (error) {
      await this.disposeClient();
      throw error;
    }
  }

  private async disposeClient(): Promise<void> {
    this.connected = false;
    this.client = null;

    if (this.transport) {
      try {
        await this.transport.close();
      } catch {
        // ignore close errors
      }
    }

    this.transport = null;
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

  private extractToolCount(payload: unknown): number | null {
    const queue: unknown[] = [payload];

    while (queue.length > 0) {
      const current = queue.shift();
      if (!current || typeof current !== 'object') continue;

      const node = current as Record<string, unknown>;

      if (Array.isArray(node.tools)) {
        return node.tools.length;
      }

      if (Array.isArray(node.data) && node.data.every((item) => typeof item === 'object')) {
        queue.push(...node.data);
      }

      for (const value of Object.values(node)) {
        if (Array.isArray(value)) {
          queue.push(...value);
        } else if (typeof value === 'object' && value !== null) {
          queue.push(value);
        } else if (typeof value === 'string' && value.includes('"tools"')) {
          try {
            const parsed = JSON.parse(value) as Record<string, unknown>;
            if (Array.isArray(parsed.tools)) return parsed.tools.length;
          } catch {
            // ignore non-json string
          }
        }
      }
    }

    return null;
  }
}

