const XML_REASONING_PATTERN = /<\s*(think|reasoning|analysis)\b[^>]*>/i;
const ENGLISH_PLANNING_PATTERN = /^\s*(i need to|let me|first i'll|first i will|i should)\b/i;
const CHINESE_PLANNING_PATTERN = /^\s*(用户问的是|我需要先|先调用|接下来我会|我先分析)/;
const TOOL_PLANNING_PATTERN =
  /(tool[_\s-]?call|function[_\s-]?call|reasoning_chain|调用(?:工具|函数)|工具选择|参数组织|先(?:调用|使用).{0,16}(?:工具|函数))/i;

export const CHAT_REASONING_REPLACEMENT =
  '已省略内部分析过程，下面只展示可直接给你的结论与建议。';

export function containsReasoningLeak(text: string | null | undefined) {
  const value = String(text ?? '').trim();
  if (!value) return false;
  return (
    XML_REASONING_PATTERN.test(value)
    || ENGLISH_PLANNING_PATTERN.test(value)
    || CHINESE_PLANNING_PATTERN.test(value)
    || TOOL_PLANNING_PATTERN.test(value)
  );
}

export function sanitizeReasoningDelta(
  text: string | null | undefined,
  hasInsertedReplacement: boolean,
): { content: string; replaced: boolean } {
  const value = String(text ?? '');
  if (!value) {
    return { content: '', replaced: hasInsertedReplacement };
  }
  if (!containsReasoningLeak(value)) {
    return { content: value, replaced: hasInsertedReplacement };
  }
  if (hasInsertedReplacement) {
    return { content: '', replaced: true };
  }
  return {
    content: CHAT_REASONING_REPLACEMENT,
    replaced: true,
  };
}
