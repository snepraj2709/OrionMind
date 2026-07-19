'use client';

import { ErrorFallback } from '@/components/feedback/error-fallback';

interface GlobalErrorProps {
  reset: () => void;
}

export default function GlobalError({ reset }: GlobalErrorProps) {
  return (
    <html lang="en">
      <body>
        <ErrorFallback
          title="Orion is unavailable"
          description="The application could not recover from an unexpected error."
          onRetry={reset}
        />
      </body>
    </html>
  );
}
