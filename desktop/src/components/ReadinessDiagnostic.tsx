import { CheckCircle, XCircle, AlertTriangle, ArrowRight, Info } from "lucide-react";

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
  const criticalIssues = results.filter(r => r.status === "error");
  const warnings = results.filter(r => r.status === "warning");

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

      {criticalIssues.length > 0 && (
        <div className="diagnostic-section critical">
          <h4><XCircle size={16} /> 严重问题（需立即处理）</h4>
          {criticalIssues.map((result, idx) => (
            <DiagnosticCard key={idx} result={result} onNavigate={onNavigate} />
          ))}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="diagnostic-section warnings">
          <h4><AlertTriangle size={16} /> 警告（建议处理）</h4>
          {warnings.map((result, idx) => (
            <DiagnosticCard key={idx} result={result} onNavigate={onNavigate} />
          ))}
        </div>
      )}

      {results.every(r => r.status === "healthy") && (
        <div className="diagnostic-section healthy">
          <CheckCircle size={20} />
          <h4>系统运行正常</h4>
          <p>所有检查项均通过，无需采取行动。</p>
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
  return (
    <div className={`diagnostic-card ${result.status}`}>
      <div className="diagnostic-header">
        <span className="diagnostic-category">{result.category}</span>
        <strong>{result.title}</strong>
      </div>

      <p className="diagnostic-message">{result.message}</p>

      {result.fix_suggestions.length > 0 && (
        <div className="fix-suggestions">
          <h5><Info size={13} /> 修复建议：</h5>
          <ol>
            {result.fix_suggestions.map((suggestion, idx) => (
              <li key={idx}>{suggestion}</li>
            ))}
          </ol>
        </div>
      )}

      {result.related_page && onNavigate && (
        <button
          className="small-button"
          onClick={() => onNavigate(result.related_page!)}
          type="button"
        >
          <ArrowRight size={13} />
          前往 {result.related_page}
        </button>
      )}
    </div>
  );
}

function calculateHealthScore(results: DiagnosticResult[]): number {
  if (results.length === 0) return 100;

  const totalWeight = results.length;
  const healthyWeight = results.filter(r => r.status === "healthy").length;
  const warningWeight = results.filter(r => r.status === "warning").length * 0.7;
  const errorWeight = results.filter(r => r.status === "error").length * 0;

  return Math.round(((healthyWeight + warningWeight + errorWeight) / totalWeight) * 100);
}

function getScoreClass(score: number): string {
  if (score >= 80) return "healthy";
  if (score >= 50) return "warning";
  return "error";
}
