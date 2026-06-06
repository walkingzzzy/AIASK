import { CheckCircle, XCircle, AlertCircle, Clock, ExternalLink } from "lucide-react";
import { StatusBadge } from "./shared";

interface OAuthServerStatus {
  server: string;
  status: "authenticated" | "expired" | "missing" | "error";
  expires_at?: string;
  last_auth_at?: string;
  error_message?: string;
}

interface McpOAuthStatusProps {
  oauthServers: OAuthServerStatus[];
  onReauthorize: (server: string) => void;
}

export function McpOAuthStatus({ oauthServers, onReauthorize }: McpOAuthStatusProps) {
  if (!oauthServers.length) {
    return (
      <div className="notice">
        <AlertCircle size={14} />
        <span>暂无需要 OAuth 认证的 MCP 服务器。</span>
      </div>
    );
  }

  return (
    <div className="mcp-oauth-status">
      <h4>OAuth 认证状态</h4>
      <div className="oauth-servers-list">
        {oauthServers.map((server) => (
          <div key={server.server} className="oauth-server-card">
            <div className="oauth-server-header">
              <strong>{server.server}</strong>
              <StatusBadge
                status={server.status}
                label={getStatusLabel(server.status)}
              />
            </div>

            <div className="oauth-server-details">
              {server.status === "authenticated" && server.expires_at && (
                <div className="oauth-detail-row">
                  <Clock size={13} />
                  <span>过期时间: {formatDateTime(server.expires_at)}</span>
                </div>
              )}

              {server.last_auth_at && (
                <div className="oauth-detail-row">
                  <CheckCircle size={13} />
                  <span>最后认证: {formatDateTime(server.last_auth_at)}</span>
                </div>
              )}

              {server.error_message && (
                <div className="oauth-detail-row error">
                  <XCircle size={13} />
                  <span>{server.error_message}</span>
                </div>
              )}
            </div>

            {(server.status === "expired" || server.status === "missing" || server.status === "error") && (
              <button
                className="small-button"
                onClick={() => onReauthorize(server.server)}
                type="button"
              >
                <ExternalLink size={13} />
                重新认证
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function getStatusLabel(status: string): string {
  switch (status) {
    case "authenticated": return "已认证";
    case "expired": return "已过期";
    case "missing": return "未认证";
    case "error": return "错误";
    default: return status;
  }
}

function formatDateTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return dateStr;
  }
}
