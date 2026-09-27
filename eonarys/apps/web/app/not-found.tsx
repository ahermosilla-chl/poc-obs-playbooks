import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-text-primary text-2xl font-semibold">Página no encontrada</h1>
      <p className="text-text-muted">La página que buscas no existe.</p>
      <Link
        href="/"
        className="border-border-subtle bg-background-glass text-text-primary hover:border-accent-primary rounded-md border px-4 py-2"
      >
        Volver al inicio
      </Link>
    </main>
  );
}
