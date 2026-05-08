import type { FrontendDataEffect } from '@/lib/data-effects';

export type SurfaceAuditProofStatus = 'passed' | 'failed' | 'partial' | 'not-run';
export type SurfaceAuditArtifactKind = 'network' | 'dom' | 'snapshot' | 'screenshot' | 'console' | 'note';

export type SurfaceAuditArtifact = {
  kind: SurfaceAuditArtifactKind;
  label: string;
  summary: string;
  href?: string;
  ref?: string;
};

export type SurfaceAuditProof = {
  status: SurfaceAuditProofStatus;
  summary: string;
  evidence: readonly string[];
};

export type SurfaceAuditDefect = {
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  summary: string;
  suspectedLayer: 'frontend' | 'bff' | 'mcp' | 'backend' | 'unknown';
  effects: readonly FrontendDataEffect[];
};

export type SurfaceAuditResult = {
  surfaceId: string;
  family: string;
  proofMode: string;
  artifacts: readonly SurfaceAuditArtifact[];
  read: SurfaceAuditProof;
  source: SurfaceAuditProof;
  dependency: SurfaceAuditProof;
  stale: SurfaceAuditProof;
  defects: readonly SurfaceAuditDefect[];
  auditedAt: string;
};
