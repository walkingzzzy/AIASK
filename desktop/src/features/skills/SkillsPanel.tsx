import { useMemo, useState } from "react";
import type { CapabilityWorkbenchPayload, SkillView } from "../../types";
import { JsonPanel, StatusBadge, localizeBlockedReason } from "../../components/shared";
import { AiaskApi } from "../../services/aiaskApi";
import { formatApiError } from "../../api";

export function SkillsPanel({
  payload,
  skillsPayload: directSkillsPayload,
  controlToken,
  endpoint,
  apiToken = "",
  onRefresh,
  compact = false,
  management = false,
  onApplyToChat
}: {
  payload?: CapabilityWorkbenchPayload | null;
  skillsPayload?: CapabilityWorkbenchPayload["skills"] | null;
  controlToken: string;
  endpoint?: string;
  apiToken?: string;
  onRefresh?: () => Promise<unknown>;
  compact?: boolean;
  management?: boolean;
  onApplyToChat?: (skill: SkillView | null) => void;
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
  const recommendedPrompt = active
    ? `请使用 ${active.name} 技能协助我完成：${active.description || "分析当前任务并给出可执行建议。"}`
    : "请选择一个技能后，可把推荐 prompt 带回对话。";

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
            <span>技能</span>
            <h2>AIASK 原生技能</h2>
            <p>{localizeBlockedReason(skillsPayload.reason) || "需要控制令牌才能查看技能。"}</p>
          </div>
          <StatusBadge status="gated" label="受限" />
        </div>
      </div>
    );
  }

  return (
    <div className="capability-stack">
      <div className="capability-banner">
        <div>
          <span>技能</span>
          <h2>已安装 {skills.length} 个技能</h2>
          <p>
            {management
              ? "这里用于安装、更新或删除 AIASK 原生技能；写入操作需要控制令牌。"
              : "选择技能、查看说明，并把推荐 prompt 带回对话。安装、更新、删除放在设置的技能管理中。"}
          </p>
        </div>
        <StatusBadge status="ready" label={skills.length ? "就绪" : "就绪 / 空"} />
      </div>

      {management && !controlToken.trim() && <div className="notice warn">请连接控制令牌后再安装、更新或删除技能。</div>}

      <section className={`capability-grid ${compact ? "" : "two"}`}>
        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>{skillsPayload?.root || "-"}</span>
              <h3>已安装</h3>
            </div>
          </div>
          <div className="mini-list selectable">
            {skills.map((skill) => (
              <button className={active?.name === skill.name ? "active" : ""} key={skill.name} onClick={() => setSelected(skill.name)} type="button">
                <strong>{skill.name}</strong>
                <span>{skill.description || skill.path || "暂无描述"}</span>
              </button>
            ))}
            {!skills.length && <p className="muted">尚未安装技能。</p>}
          </div>
        </div>

        <div className="capability-section">
          <div className="section-header">
            <div>
              <span>所选技能</span>
              <h3>{active?.name || "未选择技能"}</h3>
            </div>
            <StatusBadge status={active ? "implemented" : "not_required"} label={active ? "就绪" : "空"} />
          </div>
          {active ? (
            <>
              <div className="kv-grid">
                <span>名称</span>
                <strong>{active.name}</strong>
                <span>描述</span>
                <strong>{active.description || "-"}</strong>
                {management && (
                  <>
                    <span>路径</span>
                    <strong>{active.path || "-"}</strong>
                    <span>更新时间</span>
                    <strong>{active.updated_at || "-"}</strong>
                  </>
                )}
              </div>
              {!management && (
                <div className="skill-use-panel">
                  <strong>推荐 prompt</strong>
                  <p>{recommendedPrompt}</p>
                  <button className="primary-button" disabled={!active || !onApplyToChat} onClick={() => onApplyToChat?.(active)} type="button">
                    应用到对话
                  </button>
                </div>
              )}
            </>
          ) : (
            <p className="muted">请选择一个技能查看元数据。</p>
          )}
          {management && (
            <details className="raw-details">
              <summary>原始技能快照</summary>
              <JsonPanel value={skillsPayload} />
            </details>
          )}
        </div>
      </section>

      {management && !compact && (
        <section className="capability-grid two">
          <div className="capability-section">
            <div className="section-header">
              <div>
                <span>控制</span>
                <h3>安装或更新技能</h3>
              </div>
              <StatusBadge status={controlToken.trim() ? "ready" : "gated"} />
            </div>
            <label className="field-row">
              <span>名称</span>
              <input value={skillName} onChange={(event) => setSkillName(event.target.value)} placeholder={active?.name || "skill-name"} />
            </label>
            <label className="field-row">
              <span>描述</span>
              <input value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="field-row">
              <span>内容</span>
              <textarea value={content} onChange={(event) => setContent(event.target.value)} />
            </label>
            <div className="button-row">
              <button className="primary-button" disabled={busy || !controlToken.trim() || !skillName.trim()} onClick={() => runSkillAction("install")} type="button">
                安装
              </button>
              <button className="small-button" disabled={busy || !controlToken.trim() || !(skillName || active?.name)} onClick={() => runSkillAction("update", skillName || active?.name || "")} type="button">
                更新
              </button>
              <button className="small-button danger" disabled={busy || !controlToken.trim() || !(skillName || active?.name)} onClick={() => runSkillAction("delete", skillName || active?.name || "")} type="button">
                删除
              </button>
            </div>
          </div>
          <div className="capability-section">
            <div className="section-header">
              <div>
                <span>最近操作</span>
                <h3>结果</h3>
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
