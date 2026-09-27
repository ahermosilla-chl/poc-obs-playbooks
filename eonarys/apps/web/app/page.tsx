import { sortByRelevance } from '@eonarys/core';
import { ContextCardView } from '@eonarys/ui';
import { getGreeting } from '@/lib/greeting';
import { mockContextCards } from '@/lib/mockContextCards';

export default function HomePage() {
  const greeting = getGreeting();
  const cards = sortByRelevance(mockContextCards);

  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-10 px-6 py-16 sm:px-8 sm:py-24"
    >
      <header className="flex flex-col gap-6">
        <span className="text-accent-primary text-sm font-semibold uppercase tracking-[0.3em]">
          EONARYS
        </span>
        <div className="flex flex-col gap-2">
          <h1 className="text-text-primary text-3xl font-semibold sm:text-4xl">{greeting}.</h1>
          <p className="text-text-muted text-lg">¿Qué tienes en mente?</p>
        </div>
        <label htmlFor="prompt" className="sr-only">
          ¿Qué tienes en mente?
        </label>
        <input
          id="prompt"
          type="text"
          disabled
          placeholder="Próximamente — EONARYS Advisor (ver docs/ROADMAP.md, fase 0.7)"
          aria-describedby="prompt-hint"
          className="border-border-subtle bg-background-glass text-text-primary placeholder:text-text-muted/70 w-full rounded-lg border px-4 py-3 disabled:cursor-not-allowed"
        />
        <p id="prompt-hint" className="text-text-muted text-xs">
          La conversación contextual llega en una fase posterior de EONARYS.
        </p>
      </header>

      <section aria-label="Contexto relevante" className="flex flex-col gap-4">
        {cards.map((card) => (
          <ContextCardView key={card.id} card={card} />
        ))}
      </section>

      <footer className="text-text-muted mt-auto pt-10 text-center text-sm">
        <p>EONARYS analiza. Tú decides.</p>
      </footer>
    </main>
  );
}
