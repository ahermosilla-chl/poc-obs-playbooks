import { describe, expect, it } from 'vitest';
import { sortByRelevance } from './sortByRelevance';
import type { ContextCard } from './types';

function makeCard(overrides: Partial<ContextCard>): ContextCard {
  return {
    id: 'id',
    title: 'title',
    summary: 'summary',
    domain: 'general',
    urgency: 'low',
    relevantAt: '2026-01-01T00:00:00.000Z',
    evidence: 'fact',
    isDemo: true,
    ...overrides,
  };
}

describe('sortByRelevance', () => {
  it('orders high urgency before medium and low', () => {
    const low = makeCard({ id: 'low', urgency: 'low' });
    const high = makeCard({ id: 'high', urgency: 'high' });
    const medium = makeCard({ id: 'medium', urgency: 'medium' });

    const result = sortByRelevance([low, medium, high]);

    expect(result.map((card) => card.id)).toEqual(['high', 'medium', 'low']);
  });

  it('breaks ties within the same urgency by temporal proximity', () => {
    const later = makeCard({
      id: 'later',
      urgency: 'high',
      relevantAt: '2026-03-01T00:00:00.000Z',
    });
    const sooner = makeCard({
      id: 'sooner',
      urgency: 'high',
      relevantAt: '2026-01-15T00:00:00.000Z',
    });

    const result = sortByRelevance([later, sooner]);

    expect(result.map((card) => card.id)).toEqual(['sooner', 'later']);
  });

  it('does not mutate the input array', () => {
    const cards = [makeCard({ id: 'a', urgency: 'low' }), makeCard({ id: 'b', urgency: 'high' })];
    const original = [...cards];

    sortByRelevance(cards);

    expect(cards).toEqual(original);
  });
});
