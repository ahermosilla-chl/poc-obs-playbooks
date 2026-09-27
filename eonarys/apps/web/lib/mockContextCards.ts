import type { ContextCard } from '@eonarys/core';

/**
 * Demo/mock context cards for the 0.1 conceptual home. None of this is
 * derived from real sources — 0.2+ replaces this with the real Situation
 * Engine output (see docs/ROADMAP.md). Every card is explicitly marked
 * isDemo: true and must stay that way until real sources exist.
 */
export const mockContextCards: ContextCard[] = [
  {
    id: 'trip-buenos-aires',
    title: 'Viaje a Buenos Aires coincide con dos compromisos laborales',
    summary:
      'Tu vuelo del 14 al 18 de octubre se superpone con una revisión de proyecto y podría modificar tus gastos de ese mes.',
    domain: 'Viaje',
    urgency: 'high',
    relevantAt: '2026-10-14T00:00:00.000Z',
    evidence: 'inference',
    confidence: 0.82,
    isDemo: true,
  },
  {
    id: 'budget-extraordinary',
    title: 'Semana con gasto por encima de lo habitual',
    summary: 'Esta semana estimamos un 30% más de gasto que tu promedio de los últimos tres meses.',
    domain: 'Gastos',
    urgency: 'medium',
    relevantAt: '2026-09-29T00:00:00.000Z',
    evidence: 'estimate',
    confidence: 0.65,
    isDemo: true,
  },
  {
    id: 'project-deadline',
    title: 'Fecha importante de proyecto la próxima semana',
    summary: 'El hito "Entrega beta" está marcado para el 3 de octubre.',
    domain: 'Trabajo',
    urgency: 'medium',
    relevantAt: '2026-10-03T00:00:00.000Z',
    evidence: 'fact',
    isDemo: true,
  },
  {
    id: 'pending-decision',
    title: 'Decisión pendiente: renovación de contrato',
    summary: 'Tienes una decisión sin resolver desde hace 12 días.',
    domain: 'Decisiones',
    urgency: 'low',
    relevantAt: '2026-10-10T00:00:00.000Z',
    evidence: 'fact',
    isDemo: true,
  },
];
