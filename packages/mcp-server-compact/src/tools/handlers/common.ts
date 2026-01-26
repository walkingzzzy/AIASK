import { ToolHandler } from '../../types/tools.js';

export const notImplementedHandler: ToolHandler = async () => ({ success: false, error: 'Not implemented', degraded: true });
