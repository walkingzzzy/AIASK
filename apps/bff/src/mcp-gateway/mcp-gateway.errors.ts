export type McpGatewayTimeoutScope = 'resource_read' | 'tool_call' | 'transport_connect';

export class McpGatewayTimeoutError extends Error {
  constructor(
    message: string,
    readonly scope: McpGatewayTimeoutScope,
  ) {
    super(message);
    this.name = 'McpGatewayTimeoutError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
