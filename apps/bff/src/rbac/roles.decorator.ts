import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'roles';
export type AppRole = 'admin' | 'user';

/**
 * Mark an endpoint as requiring one of the specified roles.
 * Evaluated by {@link RolesGuard} which is registered as a global guard.
 */
export const Roles = (...roles: AppRole[]) => SetMetadata(ROLES_KEY, roles);

