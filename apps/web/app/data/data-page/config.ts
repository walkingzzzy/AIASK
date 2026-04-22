export const TABS = [
  { key: 'option', label: '期权链' },
  { key: 'calendar', label: '交易日历' },
  { key: 'ipo', label: 'IPO' },
  { key: 'cb', label: '可转债' },
  { key: 'capital', label: '股本' },
  { key: 'resource', label: '资源对象' },
] as const;

export const RESOURCE_PRESETS = [
  {
    key: 'toolCatalog',
    label: '工具目录',
    requiresId: false,
    inputLabel: '对象标识',
    placeholder: '工具目录不需要额外 ID',
    description: '查看 AI 工具目录、必填参数、输出摘要和副作用级别。',
  },
  {
    key: 'workflowGuide',
    label: '工作流指南',
    requiresId: true,
    inputLabel: '指南名称',
    placeholder: '输入工作流指南名称',
    description: '查看标准工作流模板、步骤要求和输出契约。',
  },
  {
    key: 'runSnapshot',
    label: 'Run 快照',
    requiresId: true,
    inputLabel: 'Run ID',
    placeholder: '输入 Run ID',
    description: '回看一次运行的 linege、artifact 和关键摘要。',
  },
  {
    key: 'datasetQuality',
    label: 'Dataset 质量',
    requiresId: true,
    inputLabel: 'Dataset ID',
    placeholder: '输入 Dataset ID',
    description: '查看数据集质量状态、校验标记和修复建议。',
  },
  {
    key: 'datasetProfile',
    label: 'Dataset 档案',
    requiresId: true,
    inputLabel: 'Dataset ID',
    placeholder: '输入 Dataset ID',
    description: '查看 dataset profile、lineage 和最新验证快照。',
  },
  {
    key: 'factorProfile',
    label: 'Factor 档案',
    requiresId: true,
    inputLabel: 'Factor ID',
    placeholder: '输入 Factor ID',
    description: '查看因子候选、验证结果、注册状态与衰减信息。',
  },
  {
    key: 'modelProfile',
    label: 'Model 档案',
    requiresId: true,
    inputLabel: 'Model ID',
    placeholder: '输入 Model ID',
    description: '查看模型 profile、校准信息和 champion/challenger 关系。',
  },
  {
    key: 'strategyGovernance',
    label: '策略治理',
    requiresId: true,
    inputLabel: 'Strategy ID',
    placeholder: '输入 Strategy ID',
    description: '查看策略审查状态、门禁结果与上线风险摘要。',
  },
  {
    key: 'experimentSummary',
    label: '实验摘要',
    requiresId: true,
    inputLabel: 'Experiment ID',
    placeholder: '输入 Experiment ID',
    description: '查看实验对象、关键指标和 artifact 关联关系。',
  },
  {
    key: 'governanceReport',
    label: '治理总览',
    requiresId: false,
    inputLabel: '对象标识',
    placeholder: '治理总览不需要额外 ID',
    description: '查看系统级治理、风险与告警概览。',
  },
] as const;

export const HERO_PRIMARY_BUTTON_CLS =
  'inline-flex cursor-pointer items-center justify-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-white shadow-[0_20px_40px_-24px_rgba(11,107,203,0.52)] transition hover:-translate-y-0.5 hover:shadow-[0_24px_46px_-24px_rgba(11,107,203,0.58)] disabled:cursor-not-allowed disabled:opacity-50';
export const HERO_SECONDARY_BUTTON_CLS =
  'action-chip cursor-pointer text-sm text-text-primary shadow-[0_16px_32px_-24px_rgba(15,23,42,0.28)]';
export const CHIP_BUTTON_CLS = 'action-chip cursor-pointer text-xs text-text-primary';
export const NOTE_CARD_CLS = 'metric-tile rounded-[22px] p-3 text-xs text-text-secondary';
export const SIDE_PANEL_CLS = 'panel-soft rounded-[28px] p-4 sm:p-5';
export const FIELD_CLS =
  'h-11 rounded-[20px] border border-white/65 bg-white/55 px-4 text-sm text-text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.75)] outline-none transition placeholder:text-text-muted focus:border-primary/45 focus:bg-white/72';

export type Tab = (typeof TABS)[number]['key'];
export type ResourceKey = (typeof RESOURCE_PRESETS)[number]['key'];
