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
      title="User Profile"
      description="Manage local investment profile, sector preferences, behavior memory, and reusable context for the workbench."
      badge={
        <StatusBadge tone={profile.error ? "danger" : profile.loading ? "warning" : "success"}>
          <UserRound size={14} />
          {profile.error ? "Profile degraded" : profile.loading ? "Loading profile" : "Profile ready"}
        </StatusBadge>
      }
      actions={
        <Button icon={<Save size={16} />} tone="success" onClick={() => void saveProfile()} busy={saving}>
          Save profile
        </Button>
      }
      metrics={[
        metric("User", form.user_id || "-", "info"),
        metric("Style", form.investment_style, statusTone(form.investment_style)),
        metric("Risk", form.risk_tolerance, form.risk_tolerance >= 4 ? "warning" : "success"),
        metric("Sectors", splitCsv(form.preferred_sectors).length, "info")
      ]}
    >
      <div className="grid-2">
        <Panel title="Profile preferences">
          <div className="form-grid">
            <label className="field">
              <span>User ID</span>
              <input value={form.user_id} onChange={(event) => setForm({ ...form, user_id: event.target.value })} />
            </label>
            <label className="field">
              <span>Profile name</span>
              <input value={form.profile_name} onChange={(event) => setForm({ ...form, profile_name: event.target.value })} />
            </label>
            <label className="field">
              <span>Investment style</span>
              <select value={form.investment_style} onChange={(event) => setForm({ ...form, investment_style: event.target.value })}>
                <option value="aggressive">aggressive</option>
                <option value="balanced">balanced</option>
                <option value="conservative">conservative</option>
              </select>
            </label>
            <label className="field">
              <span>Risk tolerance</span>
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
              <span>Preferred sectors</span>
              <input
                value={form.preferred_sectors}
                onChange={(event) => setForm({ ...form, preferred_sectors: event.target.value })}
                placeholder="AI, semiconductors, liquor"
              />
            </label>
            <label className="field">
              <span>Investment horizon</span>
              <select value={form.investment_horizon} onChange={(event) => setForm({ ...form, investment_horizon: event.target.value })}>
                <option value="short">short</option>
                <option value="medium">medium</option>
                <option value="long">long</option>
              </select>
            </label>
            <label className="field">
              <span>Experience level</span>
              <select value={form.experience_level} onChange={(event) => setForm({ ...form, experience_level: event.target.value })}>
                <option value="beginner">beginner</option>
                <option value="intermediate">intermediate</option>
                <option value="advanced">advanced</option>
              </select>
            </label>
            <label className="field">
              <span>Tags</span>
              <input value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="swing, macro, valuation" />
            </label>
          </div>
        </Panel>

        <Panel title="Behavior memory">
          <div className="form-grid">
            <label className="field">
              <span>Frequent queries</span>
              <textarea
                value={form.frequent_queries}
                onChange={(event) => setForm({ ...form, frequent_queries: event.target.value })}
                placeholder="market breadth, stock radar, data readiness"
              />
            </label>
            <label className="field">
              <span>Preferred models</span>
              <textarea
                value={form.preferred_models}
                onChange={(event) => setForm({ ...form, preferred_models: event.target.value })}
                placeholder="gpt-4.1-compatible, qwen2.5:latest"
              />
            </label>
            <label className="field">
              <span>Active hours</span>
              <textarea value={form.active_hours} onChange={(event) => setForm({ ...form, active_hours: event.target.value })} placeholder="9, 10, 14" />
            </label>
            <label className="field">
              <span>Common stocks</span>
              <textarea
                value={form.common_stocks}
                onChange={(event) => setForm({ ...form, common_stocks: event.target.value })}
                placeholder="600519, 300750, 宁德时代"
              />
            </label>
          </div>
        </Panel>
      </div>

      <JsonPanel title="Profile evidence" data={{ loaded: profile.data, saved: result }} />
    </PageShell>
  );
}
