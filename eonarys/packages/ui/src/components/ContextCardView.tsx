import type { ContextCard } from '@eonarys/core';
import { DemoBadge } from './DemoBadge';

const EVIDENCE_LABEL: Record<ContextCard['evidence'], string> = {
  fact: 'Hecho',
  inference: 'Inferencia',
  estimate: 'Estimación',
};

export interface ContextCardViewProps {
  card: ContextCard;
}

/**
 * Renders a single context card in the Dynamic Context Surface. Intentionally
 * domain-agnostic layout — no per-domain component variants (see
 * docs/PRODUCT.md, Dynamic Context Surface).
 */
export function ContextCardView({ card }: ContextCardViewProps) {
  return (
    <article
      className="border-border-subtle bg-background-glass flex flex-col gap-3 rounded-lg border p-5 backdrop-blur-sm"
      aria-labelledby={`context-card-${card.id}-title`}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-accent-primary text-xs uppercase tracking-wide">{card.domain}</span>
        {card.isDemo && <DemoBadge />}
      </div>
      <h3 id={`context-card-${card.id}-title`} className="text-text-primary text-lg font-semibold">
        {card.title}
      </h3>
      <p className="text-text-muted text-sm">{card.summary}</p>
      <div className="text-text-muted mt-auto flex items-center gap-2 text-xs">
        <span>{EVIDENCE_LABEL[card.evidence]}</span>
        {card.confidence !== undefined && (
          <span>· {Math.round(card.confidence * 100)}% confianza</span>
        )}
      </div>
    </article>
  );
}
