export type FundFlowTab =
  | 'stock'
  | 'sector'
  | 'concept'
  | 'north'
  | 'dragon'
  | 'margin'
  | 'block-trades'
  | 'north-detail';

export const FUND_FLOW_TABS: Array<{ key: FundFlowTab; label: string }> = [
  { key: 'stock', label: '个股资金流' },
  { key: 'sector', label: '板块资金流' },
  { key: 'concept', label: '概念资金流' },
  { key: 'north', label: '北向资金' },
  { key: 'dragon', label: '龙虎榜' },
  { key: 'margin', label: '融资融券' },
  { key: 'block-trades', label: '大宗交易' },
  { key: 'north-detail', label: '北向明细' },
];

export const FUND_FLOW_HERO_NOTES = [
  '先用板块、概念和北向资金判断“钱在往哪流”，再决定是否回到个股或研究页深入。',
  '个股资金流、龙虎榜和融资融券更适合做交易验证，板块与概念榜更适合找方向。',
  '如果你只想看外资偏好，优先走“北向资金”与“北向明细”这条组合路径。',
];
