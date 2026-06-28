import { useCallback, useRef, useState } from "react";

/**
 * useDragReorder - 原生 HTML5 拖拽排序状态机,零依赖。
 *
 * 配合任意列表/表格行使用:调用方在每行上绑定 ...dragHandleProps(index)
 * (或直接 spread 到 <tr draggable>),onReorder 在拖拽完成时回调。
 *
 * 状态:
 * - dragIndex: 正在拖动的行
 * - overIndex: 当前悬停目标行
 *
 * 事件约定:
 * - onDragStart 必须设 effectAllowed="move",否则 Firefox 不触发 drop
 * - onDragOver 必须 preventDefault,否则不触发 drop
 * - onDragEnd 兜底清空(drop 未发生时也要复位)
 */
export interface UseDragReorderOptions<T> {
  ids: string[];
  onReorder: (nextIds: string[]) => void | Promise<void>;
  enabled?: boolean;
}

export interface DragHandleProps {
  draggable: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragOver: (e: React.DragEvent) => void;
  onDragLeave: (e: React.DragEvent) => void;
  onDrop: (e: React.DragEvent) => void;
  onDragEnd: (e: React.DragEvent) => void;
}

export function useDragReorder<T>({ ids, onReorder, enabled = true }: UseDragReorderOptions<T>) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  // 拖拽中用 ref 暂存,避免闭包陈旧
  const dragIndexRef = useRef<number | null>(null);

  const handleDragStart = useCallback(
    (index: number) => (e: React.DragEvent) => {
      if (!enabled) return;
      dragIndexRef.current = index;
      setDragIndex(index);
      e.dataTransfer.effectAllowed = "move";
      // Firefox 需要 setData 才能触发 drag
      try {
        e.dataTransfer.setData("text/plain", String(index));
      } catch {
        /* ignore */
      }
    },
    [enabled]
  );

  const handleDragOver = useCallback(
    (index: number) => (e: React.DragEvent) => {
      if (!enabled) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (dragIndexRef.current !== null && dragIndexRef.current !== index) {
        setOverIndex(index);
      }
    },
    [enabled]
  );

  const handleDragLeave = useCallback(
    (index: number) => (e: React.DragEvent) => {
      if (!enabled) return;
      // 只在离开当前行到外部时清掉 overIndex,避免行间切换闪烁
      if (overIndex === index) {
        setOverIndex(null);
      }
    },
    [enabled, overIndex]
  );

  const handleDrop = useCallback(
    (index: number) => (e: React.DragEvent) => {
      if (!enabled) return;
      e.preventDefault();
      const from = dragIndexRef.current;
      if (from === null || from === index) {
        dragIndexRef.current = null;
        setDragIndex(null);
        setOverIndex(null);
        return;
      }
      const next = [...ids];
      const [moved] = next.splice(from, 1);
      next.splice(index, 0, moved);
      dragIndexRef.current = null;
      setDragIndex(null);
      setOverIndex(null);
      void onReorder(next);
    },
    [enabled, ids, onReorder]
  );

  const handleDragEnd = useCallback(() => {
    dragIndexRef.current = null;
    setDragIndex(null);
    setOverIndex(null);
  }, []);

  /** 绑定到某一行:spread {...rowProps(index)} 到 <tr> 或 <li> */
  const rowProps = useCallback(
    (index: number): DragHandleProps => ({
      draggable: enabled,
      onDragStart: handleDragStart(index),
      onDragOver: handleDragOver(index),
      onDragLeave: handleDragLeave(index),
      onDrop: handleDrop(index),
      onDragEnd: handleDragEnd
    }),
    [enabled, handleDragStart, handleDragOver, handleDragLeave, handleDrop, handleDragEnd]
  );

  /** 该行是否正在被拖动(用于降低透明度) */
  const isDragging = (index: number) => dragIndex === index;
  /** 该行是否是悬停目标(用于上边框高亮) */
  const isDragOver = (index: number) => overIndex === index;

  return { rowProps, isDragging, isDragOver, dragIndex, overIndex };
}
