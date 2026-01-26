type ManagerHelpPayload = {
    actions: string[];
    description?: string;
    notes?: string[];
};

const HELP_ACTIONS = new Set(['help', 'list', 'describe', 'actions']);

export const buildManagerHelp = (action: unknown, payload: ManagerHelpPayload) => {
    const normalized = typeof action === 'string' ? action.trim().toLowerCase() : '';
    if (normalized && !HELP_ACTIONS.has(normalized)) {
        return null;
    }

    const data: Record<string, unknown> = { actions: payload.actions };
    if (payload.description) data.description = payload.description;
    if (payload.notes && payload.notes.length > 0) data.notes = payload.notes;

    return { success: true, data };
};
