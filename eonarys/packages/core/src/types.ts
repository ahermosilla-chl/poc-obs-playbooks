/**
 * A single card in the Dynamic Context Surface (see docs/DESIGN_SYSTEM.md).
 * Intentionally domain-agnostic: EONARYS does not model fixed sections like
 * "Finance" or "Travel" (see docs/PRODUCT.md, Dynamic Context Surface).
 */
export interface ContextCard {
  id: string;
  title: string;
  summary: string;
  /** Free-form domain label used for display only, never for fixed layout. */
  domain: string;
  urgency: 'low' | 'medium' | 'high';
  /** ISO 8601 date this card is most relevant to. */
  relevantAt: string;
  evidence: EvidenceLevel;
  /** Required when evidence is 'inference' or 'estimate' (see docs/PRODUCT.md, Evidence + Confidence). */
  confidence?: number;
  /** 0.1 shows only demo/mock content; this must always be true until real sources exist. */
  isDemo: true;
}

export type EvidenceLevel = 'fact' | 'inference' | 'estimate';
