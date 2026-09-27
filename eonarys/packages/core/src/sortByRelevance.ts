import type { ContextCard } from './types';

const URGENCY_WEIGHT: Record<ContextCard['urgency'], number> = {
  high: 0,
  medium: 1,
  low: 2,
};

/**
 * Orders context cards for the Dynamic Context Surface: urgency first, then
 * temporal proximity. This is the minimal piece of logic that keeps the
 * home a data-driven surface rather than a hardcoded layout.
 */
export function sortByRelevance(cards: readonly ContextCard[]): ContextCard[] {
  return [...cards].sort((a, b) => {
    const urgencyDelta = URGENCY_WEIGHT[a.urgency] - URGENCY_WEIGHT[b.urgency];
    if (urgencyDelta !== 0) return urgencyDelta;
    return new Date(a.relevantAt).getTime() - new Date(b.relevantAt).getTime();
  });
}
