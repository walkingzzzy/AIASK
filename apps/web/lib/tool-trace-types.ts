export type ChatToolTraceItemKind = 'mcp' | 'local_context' | 'client_action';
export type ChatToolTraceItemStatus = 'pending' | 'success' | 'error';
export type ChatToolTraceStatus = 'empty' | 'running' | 'completed' | 'partial_error';
export type ChatToolTraceEvidenceMode =
  | 'mcp_supported'
  | 'tool_supported'
  | 'page_context_supported'
  | 'advisory_only';

export type ChatToolTraceScope = {
  mode?: string;
  pageKey?: string;
  objectType?: string;
  objectId?: string;
  stockCode?: string;
};

export type ChatToolTraceItem = {
  id: string;
  referenceLabel: string;
  kind: ChatToolTraceItemKind;
  toolName: string;
  status: ChatToolTraceItemStatus;
  startedAt: string;
  finishedAt?: string;
  durationMs?: number;
  inputSummary: string[];
  outputSummary: string[];
  errorMessage?: string;
  citedInAnswer?: boolean;
};

export type ChatToolTraceAnswerReference = {
  itemId: string;
  referenceLabel: string;
  toolName: string;
  evidenceSummary: string;
};

export type ChatToolTrace = {
  schemaVersion: 'tool_trace.v1';
  id: string;
  visibility: 'owner_only';
  generatedAt: string;
  status: ChatToolTraceStatus;
  scope: ChatToolTraceScope;
  items: ChatToolTraceItem[];
  answerReferences: ChatToolTraceAnswerReference[];
  evidenceMode: ChatToolTraceEvidenceMode;
  advisoryOnly: boolean;
  advisoryReason?: string;
};
