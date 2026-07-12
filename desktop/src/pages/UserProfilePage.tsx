import { Save, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAsyncResource } from "../hooks/useAsyncResource";
import { Button, JsonPanel, PageShell, Panel, StatusBadge } from "../components/ui";
import { dataObject, metric, statusTone, valueOf } from "./pageUtils";
import type { PageProps } from "./pageUtils";
import type { UnknownRecord } from "../types";

type UserProfileForm = {
  user_id: string;
  profile_name: string;
  investment_style: string;
  risk_tolerance: number;
  preferred_sectors: string;
  investment_horizon: string;
  experience_level: string;
  tags: string;
  frequent_queries: string;
  preferred_models: string;
  active_hours: string;
  common_stocks: string;
};

function splitCsv(value: string) {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toCsv(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)).join(", ") : "";
}

function toBehaviorString(listValue: unknown) {
  return Array.isArray(listValue) ? listValue.map((item) => String(item)).join(", ") : "";
}

function buildForm(profile: UnknownRecord): UserProfileForm {
  const preferences = dataObject(profile.preferences, {});
  const behavior = dataObject(profile.behavior, {});
  return {
    user_id: valueOf(profile, ["user_id"], "local"),
    profile_name: valueOf(profile, ["profile_name", "display_name"], "Local Operator"),
    investment_style: valueOf(preferences, ["investment_style"], "balanced"),
    risk_tolerance: Number(preferences.risk_tolerance ?? 3),
    preferred_sectors: toCsv(preferences.preferred_sectors),
    investment_horizon: valueOf(preferences, ["investment_horizon"], "medium"),
    experience_level: valueOf(preferences, ["experience_level"], "intermediate"),
    tags: toCsv(preferences.tags),
    frequent_queries: toBehaviorString(behavior.frequent_queries),
    preferred_models: toBehaviorString(behavior.preferred_models),
    active_hours: toBehaviorString(behavior.active_hours),
    common_stocks: toBehaviorString(behavior.common_stocks)
  };
}

function styleLabel(value: string) {
  const labels: Record<string, string> = {
    aggressive: "积极",
    balanced: "均衡",
    conservative: "稳健"
  };
  return labels[value] || value;
}

function horizonLabel(value: string) {
  const labels: Record<string, string> = {
    short: "短期",
    medium: "中期",
    long: "长期"
  };
  return labels[value] || value;
}

function experienceLabel(value: string) {
  const labels: Record<string, string> = {
    beginner: "新手",
    intermediate: "有经验",
    advanced: "资深"
  };
  return labels[value] || value;
}

export function UserProfilePage({ api, settings }: PageProps) {
  const profile = useAsyncResource(() => api.localProfile(), [api]);
  const [form, setForm] = useState<UserProfileForm>({
    user_id: settings?.userId || "local",
    profile_name: "Local Operator",
    investment_style: "balanced",
    risk_tolerance: 3,
    preferred_sectors: "",
    investment_horizon: "medium",
    experience_level: "intermediate",
    tags: "",
    frequent_queries: "",
    preferred_models: "",
    active_hours: "",
    common_stocks: ""
  });
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<unknown>(null);

  const profileData = useMemo(() => dataObject(profile.data, {}), [profile.data]);

  useEffect(() => {
    if (!profile.data) return;
    setForm(buildForm(profileData));
  }, [profile.data, profileData]);

  async function saveProfile() {
    setSaving(true);
    try {
      const payload = {
        user_id: form.user_id.trim() || settings?.userId || "local",
        profile_name: form.profile_name.trim() || "Local Operator",
        preferences: {
          investment_style: form.investment_style,
          risk_tolerance: Number(form.risk_tolerance || 3),
          preferred_sectors: splitCsv(form.preferred_sectors),
          investment_horizon: form.investment_horizon,
          experience_level: form.experience_level,
          tags: splitCsv(form.tags)
        },
        behavior: {
          frequent_queries: splitCsv(form.frequent_queries),
          preferred_models: splitCsv(form.preferred_models),
          active_hours: splitCsv(form.active_hours).map((item) => Number(item)).filter((item) => Number.isFinite(item)),
          common_stocks: splitCsv(form.common_stocks)
        }
      };
      const response = await api.saveLocalProfile(payload);
      setResult(response);
      await profile.reload();
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageShell
      title="个人资料"
      description="管理本地投资画像、行业偏好、行为记忆和工作台可复用上下文。"
      badge={
        <StatusBadge tone={profile.error ? "danger" : profile.loading ? "warning" : "success"}>
          <UserRound size={14} />
          {profile.error ? "资料降级" : profile.loading ? "正在加载资料" : "资料已就绪"}
        </StatusBadge>
      }
      actions={
        <Button icon={<Save size={16} />} tone="success" onClick={() => void saveProfile()} busy={saving}>
          保存资料
        </Button>
      }
      metrics={[
        metric("用户", form.user_id || "-", "info"),
        metric("风格", styleLabel(form.investment_style), statusTone(form.investment_style)),
        metric("风险", form.risk_tolerance, form.risk_tolerance >= 4 ? "warning" : "success"),
        metric("行业", splitCsv(form.preferred_sectors).length, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="投资偏好">
          <div className="form-grid">
            <label className="field">
              <span>用户 ID</span>
              <input value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} />
            </label>
            <label className="field">
              <span>资料名称</span>
              <input value={form.profile_name} onChange={(event) => setForm({ ...form, profile_name: event.target.value })} />
            </label>
            <label className="field">
              <span>投资风格</span>
              <select value={form.investment_style} onChange={(event) => setForm({ ...form, investment_style: event.target.value })}>
                <option value="aggressive">积极</option>
                <option value="balanced">均衡</option>
                <option value="conservative">稳健</option>
              </select>
            </label>
            <label className="field">
              <span>风险承受度</span>
              <select
                value={String(form.risk_tolerance)}
                onChange={(event) => setForm({ ...form, risk_tolerance: Number(event.target.value) })}
              >
                {[1, 2, 3, 4, 5].map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>偏好行业</span>
              <input
                value={form.preferred_sectors}
                onChange={(event) => setForm({ ...form, preferred_sectors: event.target.value })}
                placeholder="人工智能、半导体、白酒"
              />
            </label>
            <label className="field">
              <span>投资周期</span>
              <select value={form.investment_horizon} onChange={(event) => setForm({ ...form, investment_horizon: event.target.value })}>
                <option value="short">{horizonLabel("short")}</option>
                <option value="medium">{horizonLabel("medium")}</option>
                <option value="long">{horizonLabel("long")}</option>
              </select>
            </label>
            <label className="field">
              <span>经验水平</span>
              <select value={form.experience_level} onChange={(event) => setForm({ ...form, experience_level: event.target.value })}>
                <option value="beginner">{experienceLabel("beginner")}</option>
                <option value="intermediate">{experienceLabel("intermediate")}</option>
                <option value="advanced">{experienceLabel("advanced")}</option>
              </select>
            </label>
            <label className="field">
              <span>标签</span>
              <input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="波段、宏观、估值" />
            </label>
          </div>
        </Panel>

        <Panel title="行为记忆">
          <div className="form-grid">
            <label className="field">
              <span>常用问题</span>
              <textarea
                value={form.frequent_queries}
                onChange={(event) => setForm({ ...form, frequent_queries: event.target.value })}
                placeholder="市场广度、股票雷达、数据可用性"
              />
            </label>
            <label className="field">
              <span>偏好模型</span>
              <textarea
                value={form.preferred_models}
                onChange={(event) => setForm({ ...form, preferred_models: event.target.value })}
                placeholder="gpt-4.1-compatible, qwen2.5:latest"
              />
            </label>
            <label className="field">
              <span>活跃时间</span>
              <textarea value={form.active_hours} onChange={(event) => setForm({ ...form, active_hours: event.target.value })} placeholder="9, 10, 14" />
            </label>
            <label className="field">
              <span>常看股票</span>
              <textarea
                value={form.common_stocks}
                onChange={(event) => setForm({ ...form, common_stocks: event.target.value })}
                placeholder="600519, 300750, 宁德时代"
              />
            </label>
          </div>
        </Panel>
      </div>

      <JsonPanel title="资料证据" data={{ loaded: profile.data, saved: result }} />
    </PageShell>
  );
}
