'use client';

import { ErrorFallback } from '@/components/feedback/error-fallback';

interface ErrorPageProps {
  reset: () => void;
}

export default function ErrorPage({ reset }: ErrorPageProps) {
  return (
    <ErrorFallback
      title="Something went wrong"
      description="Orion could not load this part of the application."
      onRetry={reset}
    />
  );
}
