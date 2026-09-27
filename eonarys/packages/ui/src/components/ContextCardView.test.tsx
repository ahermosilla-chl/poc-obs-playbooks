import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ContextCard } from '@eonarys/core';
import { ContextCardView } from './ContextCardView';

const card: ContextCard = {
  id: 'trip-1',
  title: 'Viaje a Buenos Aires',
  summary: 'Coincide con dos compromisos laborales.',
  domain: 'Viaje',
  urgency: 'high',
  relevantAt: '2026-10-01T00:00:00.000Z',
  evidence: 'inference',
  confidence: 0.82,
  isDemo: true,
};

describe('ContextCardView', () => {
  it('renders the card title, summary and domain', () => {
    render(<ContextCardView card={card} />);

    expect(screen.getByRole('heading', { name: card.title })).toBeInTheDocument();
    expect(screen.getByText(card.summary)).toBeInTheDocument();
    expect(screen.getByText('Viaje')).toBeInTheDocument();
  });

  it('shows the demo badge when the card is marked as demo', () => {
    render(<ContextCardView card={card} />);

    expect(screen.getByText('demo')).toBeInTheDocument();
  });

  it('shows the evidence label and confidence for inferences', () => {
    render(<ContextCardView card={card} />);

    expect(screen.getByText('Inferencia')).toBeInTheDocument();
    expect(screen.getByText('· 82% confianza')).toBeInTheDocument();
  });
});
