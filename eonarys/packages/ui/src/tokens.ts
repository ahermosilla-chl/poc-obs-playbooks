/**
 * Design tokens for EONARYS (see docs/DESIGN_SYSTEM.md). This is the single
 * source of truth — components must reference these, not hardcode values.
 */
export const tokens = {
  color: {
    background: {
      base: '#05070d',
      surface: '#0b1120',
      glass: 'rgba(15, 23, 42, 0.55)',
    },
    accent: {
      primary: '#22d3ee',
      warm: '#f59e0b',
    },
    text: {
      primary: '#e6edf7',
      muted: '#8b96ac',
    },
    border: {
      subtle: 'rgba(148, 163, 184, 0.12)',
    },
  },
  radius: {
    md: '0.75rem',
    lg: '1.25rem',
  },
} as const;
