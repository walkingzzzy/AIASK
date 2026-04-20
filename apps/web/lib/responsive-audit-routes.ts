import catalog from '@/e2e/realworld/catalog.json';

export type ResponsiveBudgetClass = 'overview' | 'workspace' | 'table';
export type ResponsiveRouteFamily =
  | 'auth-home-admin'
  | 'market-research'
  | 'strategy-quant'
  | 'trading-ops'
  | 'utility';
export type ResponsiveDynamicResolver = 'strategy-market-first-detail' | 'execution-first-artifact';

export type ResponsiveAuditRoute = {
  surfaceId: string;
  label: string;
  group: string;
  route: string;
  auth: 'public' | 'user' | 'admin';
  mutationRisk: string;
  emptyStatePolicy: string;
  scenarioSet: string[];
  seedDependencies: string[];
  path: string;
  family: ResponsiveRouteFamily;
  requiresAuth: boolean;
  budgetClass: ResponsiveBudgetClass;
  dynamicResolver?: ResponsiveDynamicResolver;
};

export const responsiveAuditRoutes = catalog as ResponsiveAuditRoute[];

export const responsiveBudgetLimitByClass: Record<ResponsiveBudgetClass, number> = {
  overview: 2,
  workspace: 3,
  table: 3,
};
