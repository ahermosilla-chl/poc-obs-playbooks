import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import HomePage from './page';
import { mockContextCards } from '@/lib/mockContextCards';

describe('HomePage', () => {
  it('renders the EONARYS wordmark and the principle line', () => {
    render(<HomePage />);

    expect(screen.getByText('EONARYS')).toBeInTheDocument();
    expect(screen.getByText('EONARYS analiza. Tú decides.')).toBeInTheDocument();
  });

  it('renders the conceptual prompt, disabled in 0.1', () => {
    render(<HomePage />);

    const input = screen.getByLabelText('¿Qué tienes en mente?');
    expect(input).toBeDisabled();
  });

  it('renders every mock context card, each marked as demo', () => {
    render(<HomePage />);

    for (const card of mockContextCards) {
      expect(screen.getByText(card.title)).toBeInTheDocument();
    }
    expect(screen.getAllByText('demo')).toHaveLength(mockContextCards.length);
  });
});
