import { AlertTriangle, ArrowRight, CheckCircle, Info, XCircle } from "lucide-react";

interface DiagnosticResult {
  category: string;
  status: "healthy" | "warning" | "error";
  title: string;
  message: string;
  fix_suggestions: string[];
  related_page?: string;
}

interface ReadinessDiagnosticProps {
  results: DiagnosticResult[];
  onNavigate?: (page: string) => void;
}

export function ReadinessDiagnostic({ results, onNavigate }: ReadinessDiagnosticProps) {
  const healthScore = calculateHealthScore(results);
  const criticalIssues = results.filter((result) => result.status === "error");
  const warnings = results.filter((result) => result.status === "warning");

  return (
    <div className="readiness-diagnostic">
      <div className="diagnostic-summary">
        <div className="health-score">
          <h3>系统健康评分</h3>
          <div className={`score-circle ${getScoreClass(healthScore)}`}>
            <span className="score-value">{healthScore}</span>
            <span className="score-label">/100</span>
          </div>
        </div>

        <div className="issue-summary">
          <div className="issue-count error">
            <XCircle size={18} />
            <span>{criticalIssues.length} 个严重问题</span>
          </div>
          <div className="issue-count warning">
            <AlertTriangle size={18} />
            <span>{warnings.length} 个警告</span>
          </div>
        </div>
      </div>

      {!!criticalIssues.length && (
        <div className="diagnostic-section critical">
          <h4>
            <XCircle size={16} /> 严重问题
          </h4>
          {criticalIssues.map((result, index) => (
            <DiagnosticCard key={`${result.category}-${index}`} result={result} onNavigate={onNavigate} />
          ))}
        </div>
      )}

      {!!warnings.length && (
        <div className="diagnostic-section warnings">
          <h4>
            <AlertTriangle size={16} /> 建议处理
          </h4>
          {warnings.map((result, index) => (
            <DiagnosticCard key={`${result.category}-${index}`} result={result} onNavigate={onNavigate} />
          ))}
        </div>
      )}

      {results.every((result) => result.status === "healthy") && (
        <div className="diagnostic-section healthy">
          <CheckCircle size={20} />
          <h4>系统运行正常</h4>
          <p>所有检查项均通过，暂无需要处理的事项。</p>
        </div>
      )}
    </div>
  );
}

function DiagnosticCard({
  result,
  onNavigate
}: {
  result: DiagnosticResult;
  onNavigate?: (page: string) => void;
}) {
  const relatedPageLabel = result.related_page ? readinessPageLabel(result.related_page) : "";

  return (
    <div className={`diagnostic-card ${result.status}`}>
      <div className="diagnostic-header">
        <span className="diagnostic-category">{result.category}</span>
        <strong>{result.title}</strong>
      </div>

      <p className="diagnostic-message">{result.message}</p>

      {!!result.fix_suggestions.length && (
        <div className="fix-suggestions">
          <h5>
            <Info size={13} /> 修复建议
          </h5>
          <ol>
            {result.fix_suggestions.map((suggestion, index) => (
              <li key={`${suggestion}-${index}`}>{suggestion}</li>
            ))}
          </ol>
        </div>
      )}

      {result.related_page && onNavigate && (
        <button className="small-button" onClick={() => onNavigate(result.related_page!)} type="button">
          <ArrowRight size={13} />
          前往 {relatedPageLabel}
        </button>
      )}
    </div>
  );
}

function readinessPageLabel(page: string): string {
  const normalized = page.toLowerCase();
  if (normalized.includes("mcp") || normalized.includes("connector")) return "MCP / 连接器";
  if (normalized.includes("gateway")) return "Gateway";
  if (normalized.includes("tool") || normalized.includes("approval") || normalized.includes("intent")) return "工具 / 意图 / 审批";
  if (normalized.includes("financial manager")) return "金融经理台";
  if (normalized.includes("financial") || normalized.includes("finance")) return "金融实验室";
  if (normalized.includes("plugin") || normalized.includes("skill")) return "插件 / 技能";
  if (normalized.includes("setting") || normalized.includes("connection") || normalized.includes("control token")) return "设置";
  if (normalized.includes("readiness") || normalized.includes("health")) return "准备度 / 健康";
  return page;
}

function calculateHealthScore(results: DiagnosticResult[]): number {
  if (results.length === 0) return 100;

  const healthyWeight = results.filter((result) => result.status === "healthy").length;
  const warningWeight = results.filter((result) => result.status === "warning").length * 0.7;
  return Math.round(((healthyWeight + warningWeight) / results.length) * 100);
}

function getScoreClass(score: number): string {
  if (score >= 80) return "healthy";
  if (score >= 50) return "warning";
  return "error";
}
