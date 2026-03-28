'use client';

import { useEffect, useMemo, useRef } from 'react';
import { pageActionBus, type PageActionDefinition } from '@/lib/page-action-bus';
import { useCopilotStore } from '@/store/copilot-store';

function buildMetaSignature(actions: PageActionDefinition[]) {
  return actions
    .map((action) =>
      [
        action.id,
        action.label,
        action.description ?? '',
        action.scope,
        action.pageKey ?? '',
        (action.keywords ?? []).join('|'),
      ].join('::'),
    )
    .join('||');
}

export function usePageActions(actions: PageActionDefinition[]) {
  const setPageActions = useCopilotStore((state) => state.setPageActions);
  const actionsRef = useRef(new Map<string, PageActionDefinition>());

  const metas = useMemo(
    () =>
      actions.map((action) => ({
        id: action.id,
        label: action.label,
        description: action.description,
        keywords: action.keywords,
        scope: action.scope,
        pageKey: action.pageKey,
      })),
    [actions],
  );
  const metaSignature = useMemo(() => buildMetaSignature(actions), [actions]);

  useEffect(() => {
    actionsRef.current = new Map(actions.map((action) => [action.id, action]));
  }, [actions]);

  useEffect(() => {
    setPageActions(metas);
    const unregisters = metas.map((meta) =>
      pageActionBus.register({
        ...meta,
        run: (payload) => {
          const action = actionsRef.current.get(meta.id);
          if (!action) {
            throw new Error(`未找到页面动作实现: ${meta.id}`);
          }
          return action.run(payload);
        },
      }),
    );

    return () => {
      unregisters.forEach((dispose) => dispose());
      setPageActions([]);
    };
  }, [metaSignature, metas, setPageActions]);
}
