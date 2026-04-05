import { Badge, SectionCard } from '@/components/ui';
import {
  WORKSPACE_TASK_TEMPLATES,
  previewTaskTemplate,
  previewWorkspaceBlueprint,
  type WorkspaceBlueprintId,
  type WorkspaceTaskTemplateId,
} from '@/store/workbench-store';
import { BLUEPRINT_OPTIONS, TEMPLATE_OPTIONS } from './workspace-template-support';

type BlueprintOption = (typeof BLUEPRINT_OPTIONS)[number];
type TemplateOption = (typeof TEMPLATE_OPTIONS)[number];
type BlueprintPreview = ReturnType<typeof previewWorkspaceBlueprint>;
type TaskTemplatePreview = ReturnType<typeof previewTaskTemplate>;

type BlueprintCatalogCardProps = {
  selectedBlueprintId: WorkspaceBlueprintId;
  onSelect: (blueprintId: WorkspaceBlueprintId) => void;
};

export function BlueprintCatalogCard({ selectedBlueprintId, onSelect }: BlueprintCatalogCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-text-primary">工作区模板</div>
        <Badge variant="info">{BLUEPRINT_OPTIONS.length} 个模板</Badge>
      </div>

      <div className="mt-3 grid gap-3">
        {BLUEPRINT_OPTIONS.map((blueprint) => (
          <div
            key={blueprint.id}
            className={`rounded-xl border p-3 ${selectedBlueprintId === blueprint.id ? 'border-primary bg-primary/5' : 'border-glass-border bg-surface-alt/40'}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">{blueprint.label}</div>
                <div className="mt-1 text-xs leading-5 text-text-secondary">{blueprint.description}</div>
              </div>
              <button
                type="button"
                onClick={() => onSelect(blueprint.id)}
                className="rounded border border-glass-border px-3 py-1 text-xs"
              >
                预览
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="neutral">布局 {blueprint.layoutPreset}</Badge>
              <Badge variant="neutral">任务 {WORKSPACE_TASK_TEMPLATES[blueprint.taskTemplateId].label}</Badge>
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

type BlueprintPreviewCardProps = {
  selectedBlueprint: BlueprintOption;
  selectedBlueprintPreview: BlueprintPreview;
  hasBlueprintErrors: boolean;
  onCreateBlueprint: (blueprintId: WorkspaceBlueprintId) => void;
};

export function BlueprintPreviewCard({
  selectedBlueprint,
  selectedBlueprintPreview,
  hasBlueprintErrors,
  onCreateBlueprint,
}: BlueprintPreviewCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-text-primary">{selectedBlueprint.label}</div>
          <div className="mt-1 text-xs text-text-secondary">
            将创建工作区：{selectedBlueprintPreview.workspaceName}
          </div>
        </div>
        <button
          type="button"
          onClick={() => onCreateBlueprint(selectedBlueprint.id)}
          disabled={hasBlueprintErrors}
          className="rounded border border-primary px-3 py-1.5 text-xs text-primary"
        >
          创建工作区
        </button>
      </div>
      <div className="mt-3 space-y-2">
        {selectedBlueprintPreview.steps.map((step, index) => (
          <div
            key={`${selectedBlueprint.id}-${index + 1}`}
            className="rounded-xl border border-glass-border bg-surface/60 px-3 py-2"
          >
            <div className="text-xs font-medium text-text-primary">
              步骤 {index + 1} · {step.pageKey}
            </div>
            <div className="mt-1 text-sm text-text-primary">{step.title}</div>
            {step.kind ? <div className="mt-1 text-[11px] text-text-secondary">任务类型：{step.kind}</div> : null}
            {step.href ? <div className="mt-1 break-all text-[11px] text-text-muted">{step.href}</div> : null}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

type TaskTemplateCatalogCardProps = {
  selectedTemplateId: WorkspaceTaskTemplateId;
  onSelect: (templateId: WorkspaceTaskTemplateId) => void;
};

export function TaskTemplateCatalogCard({ selectedTemplateId, onSelect }: TaskTemplateCatalogCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-text-primary">任务模板</div>
        <Badge variant="info">{TEMPLATE_OPTIONS.length} 个模板</Badge>
      </div>

      <div className="mt-3 grid gap-3">
        {TEMPLATE_OPTIONS.map((template) => (
          <div
            key={template.id}
            className={`rounded-xl border p-3 ${selectedTemplateId === template.id ? 'border-primary bg-primary/5' : 'border-glass-border bg-surface-alt/40'}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-text-primary">{template.label}</div>
                <div className="mt-1 text-xs leading-5 text-text-secondary">{template.description}</div>
              </div>
              <button
                type="button"
                onClick={() => onSelect(template.id)}
                className="rounded border border-glass-border px-3 py-1 text-xs"
              >
                预览
              </button>
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

type TaskTemplatePreviewCardProps = {
  activeWorkspaceName: string;
  selectedTemplate: TemplateOption;
  selectedTemplatePreview: TaskTemplatePreview;
  hasTemplateErrors: boolean;
  onApplyTemplate: (templateId: WorkspaceTaskTemplateId) => void;
};

export function TaskTemplatePreviewCard({
  activeWorkspaceName,
  selectedTemplate,
  selectedTemplatePreview,
  hasTemplateErrors,
  onApplyTemplate,
}: TaskTemplatePreviewCardProps) {
  return (
    <SectionCard className="p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-text-primary">{selectedTemplate.label}</div>
          <div className="mt-1 text-xs text-text-secondary">
            将向当前工作区 {activeWorkspaceName} 注入以下步骤
          </div>
        </div>
        <button
          type="button"
          onClick={() => onApplyTemplate(selectedTemplate.id)}
          disabled={hasTemplateErrors}
          className="rounded border border-primary px-3 py-1.5 text-xs text-primary"
        >
          注入当前工作区
        </button>
      </div>
      <div className="mt-3 space-y-2">
        {selectedTemplatePreview.steps.map((step, index) => (
          <div
            key={`${selectedTemplate.id}-${index + 1}`}
            className="rounded-xl border border-glass-border bg-surface/60 px-3 py-2"
          >
            <div className="text-xs font-medium text-text-primary">
              步骤 {index + 1} · {step.pageKey}
            </div>
            <div className="mt-1 text-sm text-text-primary">{step.title}</div>
            {step.kind ? <div className="mt-1 text-[11px] text-text-secondary">任务类型：{step.kind}</div> : null}
            {step.href ? <div className="mt-1 break-all text-[11px] text-text-muted">{step.href}</div> : null}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}
