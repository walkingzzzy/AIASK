/**
 * ExtensionPanel - 右侧扩展栏组件
 * 提供金融联动、运行详情、工具帮助等上下文面板
 */

import { X, ChevronRight, ChevronLeft, Info, TrendingUp, FileText, Clock } from "lucide-react";
import { useState } from "react";
import { Button, JsonPanel, StatusBadge } from "./ui";
import type { UnknownRecord } from "../types";

function asText(value: unknown, fallback = "N/A") {
  if (value === undefined || value === null || value === "") return fallback;
  return String(value);
}

function statusToneFromValue(value: unknown): "success" | "danger" | "warning" {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "success" || normalized === "completed" || normalized === "ready") return "success";
  if (normalized === "error" || normalized === "failed") return "danger";
  return "warning";
}

function joinValues(value: unknown) {
  return Array.isArray(value) ? value.map((item) => String(item)).join("、") : asText(value);
}

export interface ExtensionPanelProps {
  title: string;
  defaultOpen?: boolean;
  width?: number;
  position?: "left" | "right";
  children: React.ReactNode;
}

/**
 * 可折叠的扩展面板
 *
 * @example
 * <ExtensionPanel title="运行详情" defaultOpen width={360}>
 *   <RunDetails runId={selectedRun.id} />
 * </ExtensionPanel>
 */
export function ExtensionPanel({ title, defaultOpen = false, width = 320, position = "right", children }: ExtensionPanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <aside
      className={`extension-panel extension-panel-${position} ${open ? "open" : "closed"}`}
      style={{ width: open ? `${width}px` : "48px" }}
    >
      <button className="extension-panel-toggle" onClick={() => setOpen(!open)} aria-label={open ? "折叠面板" : "展开面板"}>
        {position === "right" ? (open ? <ChevronRight size={20} /> : <ChevronLeft size={20} />) : open ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
      </button>

      {open && (
        <div className="extension-panel-content">
          <div className="extension-panel-header">
            <h3>{title}</h3>
            <button onClick={() => setOpen(false)} aria-label="关闭面板">
              <X size={18} />
            </button>
          </div>
          <div className="extension-panel-body">{children}</div>
        </div>
      )}
    </aside>
  );
}

/**
 * 金融联动面板 - 展示股票相关数据
 */
export interface FinancialContextProps {
  code: string;
  data: {
    name?: string;
    price?: number;
    change?: number;
    changePercent?: number;
    volume?: number;
    marketCap?: number;
    pe?: number;
    pb?: number;
  };
  relatedTools?: string[];
  recentRuns?: UnknownRecord[];
}

export function FinancialContext({ code, data, relatedTools, recentRuns }: FinancialContextProps) {
  return (
    <div className="financial-context">
      <div className="financial-context-header">
        <div>
          <h4>{data.name || code}</h4>
          <span className="stock-code">{code}</span>
        </div>
        {data.price !== undefined && (
          <div className="financial-context-price">
            <strong>¥{data.price.toFixed(2)}</strong>
            {data.changePercent !== undefined && (
              <StatusBadge tone={data.changePercent >= 0 ? "success" : "danger"}>
                {data.changePercent >= 0 ? "+" : ""}
                {data.changePercent.toFixed(2)}%
              </StatusBadge>
            )}
          </div>
        )}
      </div>

      <div className="financial-context-metrics">
        {data.volume !== undefined && (
          <div className="metric-item">
            <span>成交量</span>
            <strong>{(data.volume / 10000).toFixed(2)}万</strong>
          </div>
        )}
        {data.marketCap !== undefined && (
          <div className="metric-item">
            <span>市值</span>
            <strong>{(data.marketCap / 100000000).toFixed(2)}亿</strong>
          </div>
        )}
        {data.pe !== undefined && (
          <div className="metric-item">
            <span>市盈率</span>
            <strong>{data.pe.toFixed(2)}</strong>
          </div>
        )}
        {data.pb !== undefined && (
          <div className="metric-item">
            <span>市净率</span>
            <strong>{data.pb.toFixed(2)}</strong>
          </div>
        )}
      </div>

      {relatedTools && relatedTools.length > 0 && (
        <div className="financial-context-section">
          <h5>
            <Info size={14} />
            相关工具
          </h5>
          <div className="tool-chips">
            {relatedTools.map((tool) => (
              <span key={tool} className="tool-chip">
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      {recentRuns && recentRuns.length > 0 && (
        <div className="financial-context-section">
          <h5>
            <Clock size={14} />
            最近运行
          </h5>
          <div className="recent-runs-list">
            {recentRuns.slice(0, 3).map((run, i) => (
              <div key={i} className="recent-run-item">
                <FileText size={14} />
                <span>{asText(run.name || run.id)}</span>
                <StatusBadge tone={statusToneFromValue(run.status)}>{asText(run.status, "unknown")}</StatusBadge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * 运行详情面板 - 展示运行的完整上下文
 */
export interface RunDetailsProps {
  run: UnknownRecord;
}

export function RunDetails({ run }: RunDetailsProps) {
  return (
    <div className="run-details">
      <div className="run-details-header">
        <h4>{asText(run.name || run.id)}</h4>
        <StatusBadge tone={statusToneFromValue(run.status)}>{asText(run.status, "unknown")}</StatusBadge>
      </div>

      <div className="run-details-meta">
        <div className="meta-item">
          <span>运行ID</span>
          <code>{asText(run.id)}</code>
        </div>
        <div className="meta-item">
          <span>开始时间</span>
          <strong>{asText(run.start_time)}</strong>
        </div>
        {Boolean(run.end_time) && (
          <div className="meta-item">
            <span>结束时间</span>
            <strong>{asText(run.end_time)}</strong>
          </div>
        )}
        {Boolean(run.duration) && (
          <div className="meta-item">
            <span>耗时</span>
            <strong>{asText(run.duration)}s</strong>
          </div>
        )}
      </div>

      {Boolean(run.input) && (
        <div className="run-details-section">
          <h5>输入参数</h5>
          <JsonPanel data={run.input} />
        </div>
      )}

      {Boolean(run.output) && (
        <div className="run-details-section">
          <h5>输出结果</h5>
          <JsonPanel data={run.output} />
        </div>
      )}

      {Boolean(run.error) && (
        <div className="run-details-error">
          <h5>错误信息</h5>
          <pre>{asText(run.error)}</pre>
        </div>
      )}
    </div>
  );
}

/**
 * 工具帮助面板 - 展示工具的schema和示例
 */
export interface ToolHelpProps {
  tool: UnknownRecord;
}

export function ToolHelp({ tool }: ToolHelpProps) {
  return (
    <div className="tool-help">
      <div className="tool-help-header">
        <h4>{asText(tool.name)}</h4>
        <StatusBadge>{asText(tool.category, "未分类")}</StatusBadge>
      </div>

      {Boolean(tool.description) && (
        <div className="tool-help-description">
          <p>{asText(tool.description)}</p>
        </div>
      )}

      {Boolean(tool.schema) && (
        <div className="tool-help-section">
          <h5>参数说明</h5>
          <JsonPanel data={tool.schema} />
        </div>
      )}

      {Boolean(tool.examples) && (
        <div className="tool-help-section">
          <h5>使用示例</h5>
          <pre className="tool-help-examples">{JSON.stringify(tool.examples, null, 2)}</pre>
        </div>
      )}

      {Boolean(tool.risk_level) && (
        <div className="tool-help-warning">
          <Info size={16} />
          <div>
            <strong>风险等级：{asText(tool.risk_level)}</strong>
            {Boolean(tool.side_effects) && <p>副作用：{joinValues(tool.side_effects)}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
