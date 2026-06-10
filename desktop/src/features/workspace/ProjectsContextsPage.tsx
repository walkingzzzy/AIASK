import { Database, FolderGit2, RefreshCw, ShieldCheck, Zap } from "lucide-react";
import { StatusBadge } from "../../components/shared";
import type { HealthDetailed, MainView } from "../../types";

export function ProjectsContextsPage({
  agentMode,
  apiToken,
  controlToken,
  defaultEndpoint,
  endpoint,
  health,
  mockMode,
  onOpenView,
  onRefresh,
  profileName,
  status,
  userId
}: {
  agentMode: "finance_safe" | "hermes_full";
  apiToken: string;
  controlToken: string;
  defaultEndpoint: string;
  endpoint: string;
  health: HealthDetailed | null;
  mockMode: boolean;
  onOpenView: (view: MainView) => void;
  onRefresh: () => void;
  profileName?: string;
  status: string;
  userId?: string;
}) {
  return (
    <section className="capabilities-workspace optimization-page">
      <header className="capabilities-header">
        <div>
          <span>工作区</span>
          <h1>项目 / 上下文</h1>
          <p>集中查看当前 Agent 端点、后端模式、操作员画像和线程任务所需的就绪门控。</p>
        </div>
        <div className="header-actions">
          <StatusBadge status={mockMode ? "mock" : "live"} label={mockMode ? "Mock 数据" : "真实后端"} />
          <StatusBadge status={status === "AIASK_ONLINE" ? "ready" : status} label={status === "AIASK_ONLINE" ? "在线" : status} />
          <button className="small-button" onClick={onRefresh} type="button">
            <RefreshCw size={14} />
            同步
          </button>
        </div>
      </header>

      <div className="capabilities-body">
        <div className="optimization-grid">
          <article className="optimization-card">
            <FolderGit2 size={18} />
            <span>上下文</span>
            <h2>{profileName || "本地工作区"}</h2>
            <p>用户：{userId || "local"}</p>
            <p>模式：{agentMode}</p>
          </article>
          <article className="optimization-card">
            <Database size={18} />
            <span>Agent 端点</span>
            <h2>{endpoint}</h2>
            <p>默认：{defaultEndpoint}</p>
            <p>服务：{health?.service || "未加载"}</p>
          </article>
          <article className="optimization-card">
            <ShieldCheck size={18} />
            <span>权限</span>
            <h2>{controlToken.trim() ? "控制令牌就绪" : "控制令牌门控"}</h2>
            <p>API 令牌：{apiToken.trim() ? "已配置" : "缺失"}</p>
            <p>完整模式：{health?.hermes?.full_mode_active ? "已激活" : "未激活"}</p>
          </article>
        </div>

        <div className="capability-grid two">
          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>推荐动作</span>
                <h3>保持上下文可见</h3>
              </div>
              <Zap size={18} />
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={() => onOpenView("settings")} type="button">打开设置</button>
              <button className="small-button" onClick={() => onOpenView("readiness-health")} type="button">准备度 / 健康</button>
              <button className="small-button" onClick={() => onOpenView("workbench")} type="button">返回工作台</button>
            </div>
          </section>
          <section className="capability-section">
            <div className="section-header">
              <div>
                <span>设计说明</span>
                <h3>线程优先上下文</h3>
              </div>
            </div>
            <p className="muted">
              此页是当前桌面客户端的轻量项目/上下文中枢，将 Mock/真实后端、Agent 端点、画像、令牌和完整模式状态放在同一处，
              不新增后端依赖。
            </p>
          </section>
        </div>
      </div>
    </section>
  );
}
