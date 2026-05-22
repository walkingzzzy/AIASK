import type { SettingsFieldSchema } from "../types";

export function AutoField({
  schema,
  value,
  onChange
}: {
  schema: SettingsFieldSchema;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field-row auto-field">
      <span>{schema.label}</span>
      {schema.type === "select" ? (
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          {(schema.options || []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={schema.type === "password" ? "password" : "text"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={schema.description || schema.label}
        />
      )}
      {schema.description && <small>{schema.description}</small>}
    </label>
  );
}
