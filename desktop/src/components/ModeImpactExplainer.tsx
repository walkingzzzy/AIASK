import { Info, AlertTriangle, Shield, Zap } from "lucide-react";

interface ModeImpact {
  mode: "finance_safe" | "api_safe" | "full";
  tools_available: number;
  tools_blocked: number;
  side_effects_allowed: string[];
  confirmations_required: boolean;
  risk_level: "low" | "medium" | "high";
  recommendations: string[];
}

interface ModeImpactExplainerProps {
  currentMode: string;
  impacts: ModeImpact[];
  onModeSelect?: (mode: string) => void;
}

export function ModeImpactExplainer({
  currentMode,
  impacts,
  onModeSelect
}: ModeImpactExplainerProps) {
  return (
    <div className="mode-impact-explainer">
      <h4>
        <Info size={16} />
        模式影响说明
      </h4>

      <div className="mode-cards">
        {impacts.map((impact) => (
          <div
            key={impact.mode}
            className={`mode-card ${impact.mode === currentMode ? "active" : ""} risk-${impact.risk_level}`}
          >
            <div className="mode-card-header">
              <div>
                <strong>{getModeLabel(impact.mode)}</strong>
                <span className="mode-badge">{getRiskLabel(impact.risk_level)}</span>
              </div>
              {getModeIcon(impact.mode)}
            </div>

            <div className="mode-stats">
              <div className="stat-item">
                <span className="stat-label">可用工具</span>
                <span className="stat-value ok">{impact.tools_available}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">受限工具</span>
                <span className="stat-value muted">{impact.tools_blocked}</span>
              </div>
            </div>

            <div className="mode-features">
              <div className="feature-item">
                <span className="feature-label">允许的副作用：</span>
                <span className="feature-value">
                  {impact.side_effects_allowed.length > 0
                    ? impact.side_effects_allowed.join(", ")
                    : "无"}
                </span>
              </div>
              <div className="feature-item">
                <span className="feature-label">需要确认：</span>
                <span className="feature-value">
                  {impact.confirmations_required ? "是" : "否"}
                </span>
              </div>
            </div>

            {impact.recommendations.length > 0 && (
              <div className="mode-recommendations">
                <h5>建议：</h5>
                <ul>
                  {impact.recommendations.map((rec, idx) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}

            {onModeSelect && impact.mode !== currentMode && (
              <button
                className="small-button"
                onClick={() => onModeSelect(impact.mode)}
                type="button"
              >
                切换到此模式
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="mode-warning">
        <AlertTriangle size={14} />
        <p>
          <strong>注意：</strong>
          切换模式会影响可用工具和安全策略。建议在测试环境中先验证，生产环境谨慎切换。
        </p>
      </div>
    </div>
  );
}

function getModeLabel(mode: string): string {
  const labels: Record<string, string> = {
    finance_safe: "金融安全模式",
    api_safe: "API 安全模式",
    full: "完整模式"
  };
  return labels[mode] || mode;
}

function getRiskLabel(risk: string): string {
  const labels: Record<string, string> = {
    low: "低风险",
    medium: "中风险",
    high: "高风险"
  };
  return labels[risk] || risk;
}

function getModeIcon(mode: string) {
  switch (mode) {
    case "finance_safe":
      return <Shield size={20} className="mode-icon" />;
    case "api_safe":
      return <Shield size={20} className="mode-icon" />;
    case "full":
      return <Zap size={20} className="mode-icon" />;
    default:
      return null;
  }
}
