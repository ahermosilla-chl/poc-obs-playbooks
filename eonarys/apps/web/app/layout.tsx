import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'EONARYS',
  description: 'Tu vida. En contexto.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="bg-background-base text-text-primary min-h-screen font-sans antialiased">
        <a
          href="#main-content"
          className="focus:bg-accent-primary focus:text-background-base sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:px-4 focus:py-2"
        >
          Saltar al contenido principal
        </a>
        {children}
      </body>
    </html>
  );
}
