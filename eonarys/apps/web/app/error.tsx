'use client';

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console -- baseline error visibility for 0.1; replaced by real observability later.
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-text-primary text-2xl font-semibold">Algo salió mal</h1>
      <p className="text-text-muted">Ocurrió un error inesperado. Puedes intentar de nuevo.</p>
      <button
        type="button"
        onClick={reset}
        className="border-border-subtle bg-background-glass text-text-primary hover:border-accent-primary rounded-md border px-4 py-2"
      >
        Reintentar
      </button>
    </main>
  );
}
