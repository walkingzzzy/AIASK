export const EMPTY_SURFACE_DETAIL_ID = '__empty__';

export function isSurfacePlaceholderId(value: string | null | undefined) {
  return String(value ?? '').trim() === EMPTY_SURFACE_DETAIL_ID;
}

export function buildStrategyDetailPlaceholderHref() {
  return `/strategy-market/${EMPTY_SURFACE_DETAIL_ID}?state=empty`;
}

export function buildExecutionArtifactDetailHref(
  artifactId: string | null | undefined,
  accountId?: string | null,
) {
  const normalizedArtifactId = typeof artifactId === 'string' && artifactId.trim()
    ? artifactId.trim()
    : EMPTY_SURFACE_DETAIL_ID;
  const query = new URLSearchParams();
  if (typeof accountId === 'string' && accountId.trim()) {
    query.set('account_id', accountId.trim());
  }
  if (normalizedArtifactId === EMPTY_SURFACE_DETAIL_ID) {
    query.set('state', 'empty');
  }
  return `/execution/artifacts/${encodeURIComponent(normalizedArtifactId)}${query.toString() ? `?${query.toString()}` : ''}`;
}
