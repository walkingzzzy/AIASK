export const DEEP_ANALYSIS_TASKS = [
  'quick_scan',
  'deep_analysis',
  'recover_gaps',
  'rebuild_report',
  'trade_plan',
] as const;

export type DeepAnalysisTask = typeof DEEP_ANALYSIS_TASKS[number];

export type AnalysisStage = {
  stage: string;
  status: string;
  success: boolean;
  detail?: Record<string, unknown>;
  updated_at?: string;
};

export type AnalysisEvidenceItem = {
  evidence_id: string;
  section: string;
  kind: string;
  label: string;
  statement: string;
  value: unknown;
  source: string;
  source_field: string;
};

export type AnalysisEvidence = {
  version?: string;
  code?: string;
  task?: string;
  evidence?: AnalysisEvidenceItem[];
  summary?: {
    count?: number;
    sections?: string[];
    fact_count?: number;
    inference_count?: number;
  };
};

export type AnalysisGapItem = {
  field: string;
  severity: string;
  message: string;
  recovery_action: string;
};

export type AnalysisGapReport = {
  run_id: string;
  code?: string;
  status: string;
  blocked: boolean;
  resolution_message?: string | null;
  critical_missing?: AnalysisGapItem[];
  non_critical_missing?: AnalysisGapItem[];
  fallback_flags?: string[];
  recovery_actions?: string[];
  checked_at?: string;
  candidates?: Array<Record<string, unknown>>;
};

export type AnalysisSection = {
  key: string;
  title: string;
  narrative: string;
  evidence_ids: string[];
};

export type AnalysisAgentReview = {
  run_id: string;
  reviewer: string;
  verdict: string;
  cited_evidence_ids?: string[];
  risks?: string[];
  conflicts?: string[];
  next_actions?: string[];
  checked_at?: string;
};

export type AnalysisSynthesis = {
  run_id: string;
  code?: string;
  task?: string;
  digest?: string;
  sections?: AnalysisSection[];
  summary?: {
    action?: string;
    confidence?: number | string | null;
    gap_status?: string;
  };
};

export type AnalysisSummaryCard = {
  title: string;
  subtitle?: string;
  bullets?: string[];
};

export type AnalysisPerspectiveCard = {
  key: string;
  title: string;
  value?: unknown;
  note?: string;
};

export type AnalysisReportBundle = {
  run_id: string;
  code?: string;
  task?: string;
  summary_card?: AnalysisSummaryCard;
  one_paragraph_digest?: string;
  perspective_cards?: AnalysisPerspectiveCard[];
  sections?: AnalysisSection[];
  standalone_html?: string;
  manifest?: Record<string, unknown>;
  found?: boolean;
  error?: string;
};

export type AnalysisRunSummary = {
  run_id: string;
  code?: string;
  name?: string;
  market?: string;
  current_stage?: string;
  report_ready?: boolean;
  digest?: string;
  gap_count?: number;
  artifact_ids?: Record<string, string>;
  resource_uris?: Record<string, string | null | undefined>;
  updated_at?: string;
};

export type DeepAnalysisRunResponse = {
  task: string;
  status: string;
  steps: AnalysisStage[];
  summary: AnalysisRunSummary;
  run_id?: string;
  code?: string;
  name?: string;
  market?: string;
  analysis_input?: Record<string, unknown>;
  analysis_evidence?: AnalysisEvidence | null;
  analysis_gap_report?: AnalysisGapReport | null;
  analysis_agent_review?: AnalysisAgentReview | null;
  analysis_synthesis?: AnalysisSynthesis | null;
  analysis_report_bundle?: AnalysisReportBundle | null;
  trade_plan?: Record<string, unknown> | null;
  found?: boolean;
  error?: string;
};
