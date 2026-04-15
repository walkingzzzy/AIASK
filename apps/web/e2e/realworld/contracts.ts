export type SurfaceAuth = 'public' | 'user' | 'admin';
export type MutationRisk = 'none' | 'low' | 'medium' | 'high';
export type EmptyStatePolicy = 'allow-empty' | 'seed-required' | 'error-state-required';
export type ScenarioId = 'single' | 'workflow';

export type SurfaceSpec = {
  surfaceId: string;
  label: string;
  group: string;
  route: string;
  auth: SurfaceAuth;
  seedDependencies: string[];
  mutationRisk: MutationRisk;
  emptyStatePolicy: EmptyStatePolicy;
  scenarioSet: ScenarioId[];
};

export type FixtureCredentials = {
  username: string;
  password: string;
  userId?: string;
};

export type FixtureBundle = {
  runId: string;
  envName: string;
  browser: string;
  resetMode: string;
  baseUrl: string;
  apiBaseUrl: string;
  wsUrl: string;
  users: {
    admin: FixtureCredentials;
    demo: FixtureCredentials;
    browser: FixtureCredentials;
  };
  strategy: {
    id: string;
    route: string;
    name: string;
  };
  execution: {
    artifactId: string;
    executionId: string;
    accountId: string;
  };
  portfolio: {
    portfolioId: string;
    name: string;
  };
  watchlist: {
    groupId: string;
    groupName: string;
    codes: string[];
  };
  alerts: {
    alertId: string;
    code: string;
  };
  notifications: {
    userId: string;
    ids: string[];
  };
  admin: {
    deadLetterIds: string[];
    cacheKeys: string[];
  };
};

export type ReportAttachment = {
  name: string;
  path: string | null;
  contentType?: string | null;
};

export type ReportRow = {
  browser: string;
  surfaceId: string;
  scenarioId: string;
  title: string;
  route: string;
  auth: SurfaceAuth;
  mutationRisk: MutationRisk;
  status: string;
  durationMs: number;
  failureType: string | null;
  error: string | null;
  requestSummary: string[];
  consoleSummary: string[];
  attachments: ReportAttachment[];
};
