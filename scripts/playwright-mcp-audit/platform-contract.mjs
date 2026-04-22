export function isInScopeSurface(surface) {
  return surface?.auth === 'user' || surface?.auth === 'admin';
}

function normalizeStringArray(value) {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

export function normalizeSurfaceContract(surface) {
  const surfaceId = String(surface?.surfaceId || '');
  const inScope = isInScopeSurface(surface);
  const mutationMode = String(surface?.mutationMode || 'none');
  const prerequisites = normalizeStringArray(surface?.prerequisites);

  return {
    ...surface,
    inScope,
    proofMode: String(surface?.proofMode || 'route-read'),
    mutationMode,
    readProofRequired: surface?.readProofRequired !== false && inScope,
    writeProofRequired:
      surface?.writeProofRequired != null ? Boolean(surface.writeProofRequired) && inScope : mutationMode !== 'none' && inScope,
    prerequisites,
    seedDependencies: normalizeStringArray(surface?.seedDependencies),
    scenarioSet: normalizeStringArray(surface?.scenarioSet),
    seedStrategy: String(surface?.seedStrategy || (prerequisites.length > 0 ? 'api-seed' : 'none')),
    cleanupStrategy: String(surface?.cleanupStrategy || (mutationMode !== 'none' && inScope ? 'env-restore' : 'none')),
    artifactKey: String(surface?.artifactKey || surfaceId),
  };
}

export function deriveAcceptanceStatus(result) {
  if (!result) return 'unavailable';
  if (result.status === 'blocked') {
    return result.acceptanceStatus || 'prerequisite_missing';
  }
  if (result.status === 'failed') {
    return result.acceptanceStatus || 'unavailable';
  }
  return result.acceptanceStatus || null;
}

export function summarizeSurfaceOutcome(surfaceResults) {
  const inScope = surfaceResults.filter((item) => item.inScope);
  const outOfScope = surfaceResults.filter((item) => !item.inScope);
  const countByStatus = (items, status) => items.filter((item) => item.status === status).length;

  return {
    total: surfaceResults.length,
    inScope: {
      total: inScope.length,
      passed: countByStatus(inScope, 'passed'),
      failed: countByStatus(inScope, 'failed'),
      blocked: countByStatus(inScope, 'blocked'),
    },
    outOfScope: {
      total: outOfScope.length,
      passed: countByStatus(outOfScope, 'passed'),
      failed: countByStatus(outOfScope, 'failed'),
      blocked: countByStatus(outOfScope, 'blocked'),
    },
  };
}
