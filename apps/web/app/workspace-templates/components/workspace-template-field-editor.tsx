import { Badge, SectionCard } from '@/components/ui';
import type {
  WorkspaceContextOverrides,
  WorkspaceTemplateFieldDefinition,
} from '@/store/workbench-store';
import type { WorkspaceSharedContext } from '@aiask/shared-types';
import { contextChips, type TemplateFieldErrors } from './workspace-template-support';

type TemplateFieldEditorProps = {
  title: string;
  description: string;
  fields: WorkspaceTemplateFieldDefinition[] | undefined;
  overrides: WorkspaceContextOverrides;
  effectiveContext: WorkspaceSharedContext;
  errors: TemplateFieldErrors;
  onChange: (key: keyof WorkspaceSharedContext, value: string) => void;
  onReset: () => void;
};

export function TemplateFieldEditor({
  title,
  description,
  fields,
  overrides,
  effectiveContext,
  errors,
  onChange,
  onReset,
}: TemplateFieldEditorProps) {
  const chips = contextChips(effectiveContext);
  const errorCount = Object.keys(errors).length;

  return (
    <SectionCard className="mt-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-text-primary">{title}</div>
          <div className="mt-1 text-xs leading-5 text-text-secondary">{description}</div>
        </div>
        <div className="flex items-center gap-2">
          {errorCount > 0 ? <Badge variant="warning">{errorCount} 个待修正</Badge> : null}
          <button
            type="button"
            onClick={onReset}
            className="rounded border border-glass-border px-3 py-1 text-xs text-text-secondary"
          >
            重置参数
          </button>
        </div>
      </div>

      {fields?.length ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {fields.map((field) => {
            const value = overrides[field.key];
            const placeholderValue = effectiveContext[field.key];
            const placeholder =
              placeholderValue != null && placeholderValue !== ''
                ? String(placeholderValue)
                : (field.placeholder ?? '');

            if (field.input === 'select') {
              return (
                <label key={field.key} className="grid gap-1 text-xs text-text-secondary">
                  <span>{field.label}</span>
                  <select
                    value={typeof value === 'string' ? value : ''}
                    onChange={(event) => onChange(field.key, event.target.value)}
                    className="rounded border border-glass-border px-2 py-2 text-sm text-text-primary"
                  >
                    <option value="">沿用当前工作区</option>
                    {field.options?.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  {field.description ? <span>{field.description}</span> : null}
                  {errors[field.key] ? <span className="text-[11px] text-danger">{errors[field.key]}</span> : null}
                </label>
              );
            }

            return (
              <label key={field.key} className="grid gap-1 text-xs text-text-secondary">
                <span>{field.label}</span>
                <input
                  type={field.input === 'number' ? 'number' : 'text'}
                  value={value == null ? '' : String(value)}
                  onChange={(event) => onChange(field.key, event.target.value)}
                  placeholder={placeholder}
                  min={field.min}
                  max={field.max}
                  className="rounded border border-glass-border px-2 py-2 text-sm text-text-primary"
                />
                {field.description ? <span>{field.description}</span> : null}
                {errors[field.key] ? <span className="text-[11px] text-danger">{errors[field.key]}</span> : null}
              </label>
            );
          })}
        </div>
      ) : (
        <div className="mt-3 text-xs text-text-secondary">当前模板没有额外参数，将直接沿用当前工作区上下文。</div>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {chips.length > 0 ? (
          chips.map((chip) => (
            <Badge key={`${title}-${chip}`} variant="neutral">
              {chip}
            </Badge>
          ))
        ) : (
          <span className="text-xs text-text-secondary">当前参数下还没有形成有效上下文。</span>
        )}
      </div>
    </SectionCard>
  );
}
