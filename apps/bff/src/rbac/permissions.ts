/**
 * T-036: RBAC Permissions Matrix
 * Defines the 4-level role hierarchy and permission matrix.
 */

/**
 * Application roles (ordered by privilege level).
 *
 * NOTE: The runtime auth system currently only assigns 'admin' | 'user'
 * (see roles.decorator.ts). The expanded roles below are aspirational and
 * will be enforced once the user management module supports role assignment.
 */
export type AppRole = 'admin' | 'trader' | 'analyst' | 'viewer';

export const ROLE_HIERARCHY: Record<AppRole, number> = {
    admin: 4,
    trader: 3,
    analyst: 2,
    viewer: 1,
};

/** Permission actions */
export type PermAction = 'read' | 'write' | 'execute' | 'admin';

/** Module-level permissions */
export interface ModulePermission {
    module: string;
    roles: Partial<Record<AppRole, PermAction[]>>;
}

/** Full permission matrix */
export const PERMISSION_MATRIX: ModulePermission[] = [
    {
        module: 'dashboard',
        roles: { admin: ['read', 'write', 'admin'], trader: ['read', 'write'], analyst: ['read', 'write'], viewer: ['read'] },
    },
    {
        module: 'market',
        roles: { admin: ['read'], trader: ['read'], analyst: ['read'], viewer: ['read'] },
    },
    {
        module: 'stock',
        roles: { admin: ['read'], trader: ['read'], analyst: ['read', 'write'], viewer: ['read'] },
    },
    {
        module: 'watchlist',
        roles: { admin: ['read', 'write'], trader: ['read', 'write'], analyst: ['read', 'write'], viewer: ['read'] },
    },
    {
        module: 'paper-trading',
        roles: { admin: ['read', 'write', 'execute'], trader: ['read', 'write', 'execute'], analyst: ['read'], viewer: [] },
    },
    {
        module: 'portfolio',
        roles: { admin: ['read', 'write'], trader: ['read', 'write'], analyst: ['read'], viewer: ['read'] },
    },
    {
        module: 'backtest',
        roles: { admin: ['read', 'write', 'execute'], trader: ['read', 'write', 'execute'], analyst: ['read', 'write', 'execute'], viewer: ['read'] },
    },
    {
        module: 'alerts',
        roles: { admin: ['read', 'write'], trader: ['read', 'write'], analyst: ['read', 'write'], viewer: ['read'] },
    },
    {
        module: 'notifications',
        roles: { admin: ['read', 'write'], trader: ['read', 'write'], analyst: ['read', 'write'], viewer: ['read'] },
    },
    {
        module: 'admin',
        roles: { admin: ['read', 'write', 'execute', 'admin'], trader: [], analyst: [], viewer: [] },
    },
    {
        module: 'users',
        roles: { admin: ['read', 'write', 'admin'], trader: [], analyst: [], viewer: [] },
    },
    {
        module: 'audit',
        roles: { admin: ['read'], trader: [], analyst: [], viewer: [] },
    },
    {
        module: 'cache',
        roles: { admin: ['read', 'write', 'execute'], trader: [], analyst: [], viewer: [] },
    },
];

/** Check if a role has permission for a module/action */
export function hasPermission(role: AppRole, module: string, action: PermAction): boolean {
    const entry = PERMISSION_MATRIX.find((p) => p.module === module);
    if (!entry) return false;
    const perms = entry.roles[role] ?? [];
    return perms.includes(action);
}

/** Check if role has at least the given level */
export function hasMinRole(userRole: AppRole, requiredRole: AppRole): boolean {
    return (ROLE_HIERARCHY[userRole] ?? 0) >= (ROLE_HIERARCHY[requiredRole] ?? 0);
}

/** Role display names */
export const ROLE_LABELS: Record<AppRole, string> = {
    admin: '管理员',
    trader: '交易员',
    analyst: '分析师',
    viewer: '观察者',
};
