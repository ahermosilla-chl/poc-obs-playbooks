import { describe, expect, it } from 'vitest';
import { getGreeting } from './greeting';

describe('getGreeting', () => {
  it('returns "Buenos días" in the morning', () => {
    expect(getGreeting(new Date('2026-01-01T08:00:00'))).toBe('Buenos días');
  });

  it('returns "Buenas tardes" in the afternoon', () => {
    expect(getGreeting(new Date('2026-01-01T15:00:00'))).toBe('Buenas tardes');
  });

  it('returns "Buenas noches" at night', () => {
    expect(getGreeting(new Date('2026-01-01T22:00:00'))).toBe('Buenas noches');
  });

  it('returns "Buenas noches" late at night / early morning', () => {
    expect(getGreeting(new Date('2026-01-01T03:00:00'))).toBe('Buenas noches');
  });
});
