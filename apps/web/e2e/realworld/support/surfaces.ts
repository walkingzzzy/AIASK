import rawCatalog from '../catalog.json';
import type { FixtureBundle, SurfaceSpec } from '../contracts';

const SURFACES = rawCatalog as SurfaceSpec[];

if (SURFACES.length !== 54) {
  throw new Error(`realworld catalog must contain 54 surfaces, received ${SURFACES.length}`);
}

const SURFACE_MAP = new Map(SURFACES.map((surface) => [surface.surfaceId, surface]));

export function listSurfaces() {
  return SURFACES;
}

export function getSurface(surfaceId: string) {
  const surface = SURFACE_MAP.get(surfaceId);
  if (!surface) {
    throw new Error(`unknown surface: ${surfaceId}`);
  }
  return surface;
}

export function pickSurfaces(surfaceIds: string[]) {
  return surfaceIds.map((surfaceId) => getSurface(surfaceId));
}

export function resolveSurfaceRoute(surface: SurfaceSpec, bundle: FixtureBundle) {
  if (surface.surfaceId === 'execution') {
    return `/execution?execution_id=${encodeURIComponent(bundle.execution.executionId)}&account_id=${encodeURIComponent(bundle.execution.accountId)}`;
  }

  if (surface.surfaceId === 'performance' || surface.surfaceId === 'performance-review-workbench') {
    return `/performance?mode=account&account_id=${encodeURIComponent(bundle.execution.accountId)}`;
  }

  return surface.route
    .replace(':strategyId', encodeURIComponent(bundle.strategy.id))
    .replace(':artifactId', encodeURIComponent(bundle.execution.artifactId));
}
