export const PUBLIC_PATHS = new Set(['/login', '/register']);

export function isPublicPathname(pathname?: string | null) {
  if (!pathname) return false;
  return PUBLIC_PATHS.has(pathname);
}
