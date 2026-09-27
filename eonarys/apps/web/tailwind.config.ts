import type { Config } from 'tailwindcss';
// Imported from the tokens module directly (not the package's index) so that
// the Tailwind config loader does not have to resolve the UI package's React
// component tree just to read plain data tokens.
import { tokens } from '@eonarys/ui/src/tokens';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: tokens.color.background,
        accent: tokens.color.accent,
        text: tokens.color.text,
        border: tokens.color.border,
      },
      borderRadius: {
        md: tokens.radius.md,
        lg: tokens.radius.lg,
      },
    },
  },
  plugins: [],
};

export default config;
