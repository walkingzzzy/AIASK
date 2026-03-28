'use client';

import type { CopilotActionMeta, CopilotActionPayload, CopilotActionScope } from '@/lib/copilot-types';

export type PageActionDefinition = CopilotActionMeta & {
  run: (payload?: CopilotActionPayload) => Promise<unknown> | unknown;
};

type ActionHandler = {
  meta: CopilotActionMeta;
  run: PageActionDefinition['run'];
};

class PageActionBus {
  private handlers = new Map<string, ActionHandler>();

  register(action: PageActionDefinition) {
    this.handlers.set(action.id, {
      meta: {
        id: action.id,
        label: action.label,
        description: action.description,
        keywords: action.keywords,
        scope: action.scope,
        pageKey: action.pageKey,
      },
      run: action.run,
    });

    return () => {
      const current = this.handlers.get(action.id);
      if (current?.run === action.run) {
        this.handlers.delete(action.id);
      }
    };
  }

  async execute(id: string, payload?: CopilotActionPayload) {
    const handler = this.handlers.get(id);
    if (!handler) {
      throw new Error(`未找到可执行动作: ${id}`);
    }
    return handler.run(payload);
  }

  list(scope?: CopilotActionScope) {
    const items = Array.from(this.handlers.values()).map((item) => item.meta);
    if (!scope) return items;
    return items.filter((item) => item.scope === scope);
  }
}

export const pageActionBus = new PageActionBus();
