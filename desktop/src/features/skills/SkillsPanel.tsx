import { useMemo, useState } from "react";
import type { CapabilityWorkbenchPayload, SkillView } from "../../types";
import { JsonPanel, StatusBadge } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import { formatApiError } from "../../api";

export function SkillsPanel({
  payload,
  skillsPayload: directSkillsPayload,
  controlToken,
  endpoint,
  apiToken = "",
  onRefresh,
  compact = false
}: {
  payload?: CapabilityWorkbenchPayload | null;
  skillsPayload?: CapabilityWorkbenchPayload["skills"] | null;
  controlToken: string;
  endpoint?: string;
  apiToken?: string;
  onRefresh?: () => Promise<unknown>;
  compact?: boolean;
}) {
  const [selected, setSelected] = useState<string>("");
  const [skillName, setSkillName] = useState("");
  const [description, setDescription] = useState("");
  const [content, setContent] = useState("# Skill\n");
  const [actionResult, setActionResult] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const skillsPayload = directSkillsPayload || payload?.skills;
  const skills = useMemo(() => (Array.isArray(skillsPayload?.skills) ? (skillsPayload.skills as SkillView[]) : []), [skillsPayload]);
  const active = skills.find((skill) => skill.name === selected) || skills[0] || null;
  const api = useMemo(() => (endpoint ? new AiaskApi({ endpoint, apiToken, controlToken }) : null), [apiToken, controlToken, endpoint]);

  async function runSkillAction(action: "install" | "update" | "delete", nameValue = skillName || active?.name || "") {
    if (!api || !nameValue.trim()) return;
    setBusy(true);
    try {
      const result =
        action === "delete"
          ? await api.skillDelete(nameValue.trim())
          : action === "update"
            ? await api.skillUpdate(nameValue.trim(), { description, content })
            : await api.skillInstall({ name: nameValue.trim(), description, content });
      setActionResult(result);
      await onRefresh?.();
    } catch (error) {
      setActionResult({ success: false, error: formatApiError(error) });
    } finally {
      setBusy(false);
    }
  }

  if (skillsPayload?.gated) {
    return (
      <div className="capability-stack">
        <div className="capability-banner">
          <div>
            <span>Skills</span>
            <h2>Native AIASK skills</h2>
            <p>{skillsPayload.reason || "Control token required to inspect skills."}</p>
          </div>
          <StatusBadge status="gated" label="gated" />
        </div>
      </div>
    );
  }

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>Skills</span>
          <h2>{skills.length} installed skills</h2>
          <p>Skills are native AIASK files. Write operations require a control token and stay out of normal chat flow.</p>
        </div>
        <StatusBadge status="ready" label={skills.length ? "ready" : "ready / empty"} />
      </div>

      {!controlToken.trim() && <div className="notice warn">Connect with a control token to install, update, or delete skills.</div>}

      <section className={`capability-grid ${compact ? "" : "two"}`}>
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{skillsPayload?.root || "-"}</span>
              <h3>Installed</h3>
            </div>
          </div>
          <div className="mini-list selectable">
            {skills.map((skill) => (
              <button className={active?.name === skill.name ? "active" : ""} key={skill.name} onClick={() => setSelected(skill.name)} type="button">
                <strong>{skill.name}</strong>
                <span>{skill.description || skill.path || "No description"}</span>
              </button>
            ))}
            {!skills.length && <p className="muted">No skills installed.</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>Selected skill</span>
              <h3>{active?.name || "No skill selected"}</h3>
            </div>
            <StatusBadge status={active ? "implemented" : "not_required"} label={active ? "ready" : "empty"} />
          </div>
          {active ? (
            <div className="kv-grid">
              <span>Name</span>
              <strong>{active.name}</strong>
              <span>Description</span>
              <strong>{active.description || "-"}</strong>
              <span>Path</span>
              <strong>{active.path || "-"}</strong>
              <span>Updated</span>
              <strong>{active.updated_at || "-"}</strong>
            </div>
          ) : (
            <p className="muted">Select a skill to inspect metadata.</p>
          )}
          <details className="raw-details">
            <summary>Raw skill snapshot</summary>
            <JsonPanel value={skillsPayload} />
          </details>
        </div>
      </section>

      {!compact && (
        <section className="capability-grid two">
          <div className="capability-section">
            <div className="section-header">
              <div>
                <span>Control</span>
                <h3>Install or update skill</h3>
              </div>
              <StatusBadge status={controlToken.trim() ? "ready" : "gated"} />
            </div>
            <label className="field-row">
              <span>Name</span>
              <input value={skillName} onChange={(event) => setSkillName(event.target.value)} placeholder={active?.name || "skill-name"} />
            </label>
            <label className="field-row">
              <span>Description</span>
              <input value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="field-row">
              <span>Content</span>
              <textarea value={content} onChange={(event) => setContent(event.target.value)} />
            </label>
            <div className="button-row">
              <button className="primary-button" disabled={busy || !controlToken.trim() || !skillName.trim()} onClick={() => runSkillAction("install")} type="button">
                Install
              </button>
              <button className="small-button" disabled={busy || !controlToken.trim() || !(skillName || active?.name)} onClick={() => runSkillAction("update", skillName || active?.name || "")} type="button">
                Update
              </button>
              <button className="small-button danger" disabled={busy || !controlToken.trim() || !(skillName || active?.name)} onClick={() => runSkillAction("delete", skillName || active?.name || "")} type="button">
                Delete
              </button>
            </div>
          </div>
          <div className="capability-section">
            <div className="section-header">
              <div>
                <span>Last action</span>
                <h3>Result</h3>
              </div>
              <StatusBadge status={actionResult ? "ready" : "not_loaded"} />
            </div>
            <JsonPanel value={actionResult || { status: "no_action" }} />
          </div>
        </section>
      )}
    </div>
  );
}
