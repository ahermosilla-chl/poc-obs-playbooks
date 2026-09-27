/**
 * Marks content as demo/mock. 0.1 has no real sources or intelligence
 * (see docs/ROADMAP.md), so any visible insight must carry this badge.
 */
export function DemoBadge() {
  return (
    <span className="border-border-subtle bg-background-glass text-text-muted rounded-full border px-2 py-0.5 text-xs font-medium tracking-wide">
      demo
    </span>
  );
}
