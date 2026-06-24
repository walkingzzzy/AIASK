import { AlertCircle, CheckCircle2, FileText, Loader2, Play, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import type { Tone, UnknownRecord } from "../types";
import { Button, StatusBadge } from "./ui";

export interface ActionIntent {
  id: string;
  action: string;
  payload?: UnknownRecord;
  side_effect?: string;
  risk_level?: "low" | "medium" | "high";
  status: "pending" | "approved" | "denied" | "completed" | "failed";
  created_at?: string;
  reason?: string;
}

export function GatedActionButton({
  action,
  payload,
  onCreateIntent,
  controlAvailable,
  requiresApproval = false,
  riskLevel = "medium",
  buttonTestId,
  children
}: {
  action: string;
  payload?: UnknownRecord;
  onCreateIntent: (action: string, payload?: UnknownRecord) => Promise<void>;
  controlAvailable: boolean;
  requiresApproval?: boolean;
  riskLevel?: "low" | "medium" | "high";
  buttonTestId?: string;
  children: ReactNode;
}) {
  const [busy, setBusy] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const riskTone: Record<string, Tone> = {
    low: "success",
    medium: "warning",
    high: "danger"
  };

  async function handleClick() {
    if (!controlAvailable) return;
    if (requiresApproval) {
      setShowPreview(true);
      return;
    }
    setBusy(true);
    try {
      await onCreateIntent(action, payload);
    } finally {
      setBusy(false);
    }
  }

  async function confirmIntent() {
    setBusy(true);
    try {
      await onCreateIntent(action, payload);
      setShowPreview(false);
    } finally {
      setBusy(false);
    }
  }

  if (showPreview) {
    return (
      <div className="intent-preview" data-testid="intent-preview">
        <div className="intent-preview-header">
          <ShieldCheck size={20} />
          <strong>Confirm controlled action</strong>
        </div>
        <div className="intent-preview-body">
          <p>Action: {action}</p>
          <StatusBadge tone={riskTone[riskLevel]}>Risk: {riskLevel}</StatusBadge>
          {payload ? (
            <details>
              <summary>Payload preview</summary>
              <pre>{JSON.stringify(payload, null, 2)}</pre>
            </details>
          ) : null}
        </div>
        <div className="intent-preview-actions">
          <Button data-testid="intent-preview-cancel" onClick={() => setShowPreview(false)}>
            Cancel
          </Button>
          <Button data-testid="intent-preview-confirm" tone="warning" busy={busy} onClick={() => void confirmIntent()}>
            Confirm and create intent
          </Button>
        </div>
      </div>
    );
  }

  return (
    <Button
      data-testid={buttonTestId}
      tone={controlAvailable ? riskTone[riskLevel] : "neutral"}
      disabled={!controlAvailable || busy}
      busy={busy}
      onClick={() => void handleClick()}
      title={!controlAvailable ? "Requires control token" : ""}
    >
      {children}
    </Button>
  );
}

export function IntentStatusBadge({ status }: { status: ActionIntent["status"] }) {
  const statusConfig: Record<ActionIntent["status"], { tone: Tone; label: string; icon: ReactNode }> = {
    pending: { tone: "warning", label: "Pending", icon: <Loader2 size={14} className="spin" /> },
    approved: { tone: "success", label: "Approved", icon: <CheckCircle2 size={14} /> },
    denied: { tone: "danger", label: "Denied", icon: <XCircle size={14} /> },
    completed: { tone: "success", label: "Completed", icon: <CheckCircle2 size={14} /> },
    failed: { tone: "danger", label: "Failed", icon: <AlertCircle size={14} /> }
  };

  const config = statusConfig[status];
  return (
    <StatusBadge tone={config.tone}>
      {config.icon}
      {config.label}
    </StatusBadge>
  );
}

export function IntentCard({
  intent,
  onApprove,
  onDeny,
  canManage
}: {
  intent: ActionIntent;
  onApprove?: (id: string) => Promise<void>;
  onDeny?: (id: string) => Promise<void>;
  canManage: boolean;
}) {
  const [busy, setBusy] = useState(false);

  async function handleApprove() {
    if (!onApprove) return;
    setBusy(true);
    try {
      await onApprove(intent.id);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeny() {
    if (!onDeny) return;
    setBusy(true);
    try {
      await onDeny(intent.id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="intent-card">
      <div className="intent-card-header">
        <div>
          <strong>{intent.action}</strong>
          <small>ID: {intent.id}</small>
        </div>
        <IntentStatusBadge status={intent.status} />
      </div>

      {intent.payload ? (
        <details className="intent-payload">
          <summary>
            <FileText size={14} />
            Payload details
          </summary>
          <pre>{JSON.stringify(intent.payload, null, 2)}</pre>
        </details>
      ) : null}

      {intent.side_effect ? <p className="intent-side-effect">Side effect: {intent.side_effect}</p> : null}
      {intent.reason ? <p className="intent-reason">Reason: {intent.reason}</p> : null}

      {intent.status === "pending" && canManage && onApprove && onDeny ? (
        <div className="intent-card-actions">
          <Button tone="danger" busy={busy} onClick={() => void handleDeny()}>
            Deny
          </Button>
          <Button tone="success" busy={busy} onClick={() => void handleApprove()}>
            Approve
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function ApprovalQueue({
  intents,
  onApprove,
  onDeny,
  canManage
}: {
  intents: ActionIntent[];
  onApprove?: (id: string) => Promise<void>;
  onDeny?: (id: string) => Promise<void>;
  canManage: boolean;
}) {
  const pending = intents.filter((intent) => intent.status === "pending");

  if (pending.length === 0) {
    return (
      <div className="state">
        <CheckCircle2 size={24} />
        <strong>No pending intents</strong>
        <p>There are no actions waiting for review right now.</p>
      </div>
    );
  }

  return (
    <div className="approval-queue">
      <div className="approval-queue-header">
        <strong>Pending queue ({pending.length})</strong>
        {!canManage ? <StatusBadge tone="gated">Approval permissions required</StatusBadge> : null}
      </div>
      <div className="intent-list">
        {pending.map((intent) => (
          <IntentCard key={intent.id} intent={intent} onApprove={onApprove} onDeny={onDeny} canManage={canManage} />
        ))}
      </div>
    </div>
  );
}

export function DryRunPreview({
  title,
  changes,
  onConfirm,
  onCancel,
  busy
}: {
  title: string;
  changes: { label: string; before?: string; after: string }[];
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return (
    <div className="dry-run-preview" data-testid="dry-run-preview">
      <div className="dry-run-header">
        <Play size={20} />
        <strong>{title}</strong>
      </div>
      <div className="dry-run-changes">
        {changes.map((change, index) => (
          <div key={index} className="dry-run-change">
            <strong>{change.label}</strong>
            {change.before ? (
              <div className="diff">
                <code className="before">{change.before}</code>
                <span>{">"}</span>
                <code className="after">{change.after}</code>
              </div>
            ) : (
              <code>{change.after}</code>
            )}
          </div>
        ))}
      </div>
      <div className="dry-run-actions">
        <Button data-testid="dry-run-cancel" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button data-testid="dry-run-confirm" tone="warning" busy={busy} onClick={onConfirm}>
          Confirm action
        </Button>
      </div>
    </div>
  );
}
