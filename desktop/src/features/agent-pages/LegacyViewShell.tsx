import type { ReactNode } from "react";
import type { MainView } from "../../types";
import { LegacyBanner } from "./LegacyBanner";

export function LegacyViewShell({
  title,
  description,
  replacementView,
  replacementLabel,
  onOpenReplacement,
  children,
}: {
  title: string;
  description: string;
  replacementView?: MainView;
  replacementLabel?: string;
  onOpenReplacement?: (view: MainView) => void;
  children: ReactNode;
}) {
  return (
    <div className="legacy-view-shell">
      <div className="capabilities-body legacy-shell-body">
        <div className="capability-stack">
          <LegacyBanner
            description={description}
            title={title}
            replacementLabel={replacementLabel}
            replacementView={replacementView}
            onOpenReplacement={onOpenReplacement}
          />
        </div>
      </div>
      {children}
    </div>
  );
}
