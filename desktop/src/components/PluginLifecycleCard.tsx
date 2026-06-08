import { CheckCircle, XCircle, AlertCircle, Play, Power, Settings } from "lucide-react";
import { StatusBadge } from "./shared";

type PluginLifecycleStatus =
  | "not_installed"
  | "installed_disabled"
  | "installed_enabled"
  | "configured"
  | "ready"
  | "testing"
  | "error";

interface PluginLifecycleState {
  status: PluginLifecycleStatus;
  is_installed: boolean;
  is_enabled: boolean;
  is_configured: boolean;
  is_ready: boolean;
  test_passed?: boolean;
  dependencies_met: boolean;
  config_valid: boolean;
  error_message?: string;
}

interface PluginLifecycleCardProps {
  name: string;
  state: PluginLifecycleState;
  onToggle: () => void;
  onConfigure: () => void;
  onTest: () => void;
  disabled?: boolean;
}

function testIdPart(value: unknown): string {
  return String(value || "unknown")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unknown";
}

export function PluginLifecycleCard({
  name,
  state,
  onToggle,
  onConfigure,
  onTest,
  disabled = false
}: PluginLifecycleCardProps) {
  const pluginTestId = testIdPart(name);
  const toggleLabel = `${state.is_enabled ? "禁用插件" : "启用插件"} ${name}`;
  const configureLabel = `配置插件 ${name}`;
  const testLabel = `测试插件 ${name}`;
  const lifecycleSteps = [
    { key: "installed", label: "已安装", met: state.is_installed },
    { key: "enabled", label: "已启用", met: state.is_enabled },
    { key: "configured", label: "已配置", met: state.is_configured },
    { key: "dependencies", label: "依赖满足", met: state.dependencies_met },
    { key: "ready", label: "就绪", met: state.is_ready }
  ];

  return (
    <div className={`plugin-lifecycle-card ${state.status}`}>
      <div className="plugin-header">
        <strong>{name}</strong>
        <StatusBadge status={state.status} label={getStatusLabel(state.status)} />
      </div>

      {/* 生命周期进度条 */}
      <div className="lifecycle-progress">
        {lifecycleSteps.map((step, idx) => (
          <div key={step.key} className={`lifecycle-step ${step.met ? "met" : "unmet"}`}>
            {step.met ? (
              <CheckCircle size={14} />
            ) : (
              <div className="step-dot" />
            )}
            <span>{step.label}</span>
            {idx < lifecycleSteps.length - 1 && (
              <div className={`step-connector ${step.met && lifecycleSteps[idx + 1].met ? "met" : ""}`} />
            )}
          </div>
        ))}
      </div>

      {/* 错误信息 */}
      {state.error_message && (
        <div className="plugin-error">
          <XCircle size={13} />
          <span>{state.error_message}</span>
        </div>
      )}

      {/* 配置状态详情 */}
      <div className="plugin-status-details">
        {!state.dependencies_met && (
          <div className="status-warning">
            <AlertCircle size={13} />
            <span>依赖未满足</span>
          </div>
        )}
        {state.is_configured && !state.config_valid && (
          <div className="status-warning">
            <AlertCircle size={13} />
            <span>配置无效</span>
          </div>
        )}
        {state.test_passed === false && (
          <div className="status-warning">
            <XCircle size={13} />
            <span>测试失败</span>
          </div>
        )}
      </div>

      {/* 快速操作 */}
      <div className="plugin-quick-actions">
        <button
          aria-label={toggleLabel}
          className="small-button"
          data-testid={`plugin-toggle-${pluginTestId}`}
          disabled={disabled}
          onClick={onToggle}
          type="button"
          title={state.is_enabled ? "禁用插件" : "启用插件"}
        >
          <Power size={13} />
          {state.is_enabled ? "禁用" : "启用"}
        </button>

        {state.is_enabled && (
          <>
            <button
              aria-label={configureLabel}
              className="small-button"
              data-testid={`plugin-configure-${pluginTestId}`}
              disabled={disabled}
              onClick={onConfigure}
              type="button"
            >
              <Settings size={13} />
              配置
            </button>

            <button
              aria-label={testLabel}
              className="small-button"
              data-testid={`plugin-test-${pluginTestId}`}
              onClick={onTest}
              type="button"
              disabled={disabled || !state.is_configured}
            >
              <Play size={13} />
              测试
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function getStatusLabel(status: PluginLifecycleStatus): string {
  const labels: Record<PluginLifecycleStatus, string> = {
    not_installed: "未安装",
    installed_disabled: "已禁用",
    installed_enabled: "已启用",
    configured: "已配置",
    ready: "就绪",
    testing: "测试中",
    error: "错误"
  };
  return labels[status] || status;
}

// 从现有 PluginSummaryView 推断生命周期状态
export function inferPluginLifecycleState(plugin: {
  name: string;
  enabled: boolean;
  ready?: boolean;
  tools?: unknown[];
  error?: string;
}): PluginLifecycleState {
  const is_installed = true; // 如果能看到就说明已安装
  const is_enabled = plugin.enabled;
  const has_tools = (plugin.tools?.length || 0) > 0;
  const is_configured = has_tools; // 简化判断
  const is_ready = plugin.ready === true;
  const has_error = !!plugin.error;

  let status: PluginLifecycleStatus;
  if (has_error) {
    status = "error";
  } else if (is_ready) {
    status = "ready";
  } else if (is_configured) {
    status = "configured";
  } else if (is_enabled) {
    status = "installed_enabled";
  } else {
    status = "installed_disabled";
  }

  return {
    status,
    is_installed,
    is_enabled,
    is_configured,
    is_ready,
    dependencies_met: true, // 需要后端支持
    config_valid: true, // 需要后端支持
    error_message: plugin.error
  };
}
