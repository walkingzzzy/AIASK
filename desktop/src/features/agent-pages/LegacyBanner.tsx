import { ArrowRight, History } from "lucide-react";
import type { MainView } from "../../types";

export function LegacyBanner({
  title,
  description,
  replacementView,
  replacementLabel,
  onOpenReplacement,
}: {
  title: string;
  description: string;
  replacementView?: MainView;
  replacementLabel?: string;
  onOpenReplacement?: (view: MainView) => void;
}) {
  return (
    <div className="notice info legacy-banner">
      <History size={15} />
      <div className="legacy-banner-copy">
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      {replacementLabel && replacementView && onOpenReplacement && (
        <button className="small-button" onClick={() => onOpenReplacement(replacementView)} type="button">
          <ArrowRight size={13} />
          {replacementLabel}
        </button>
      )}
    </div>
  );
}
