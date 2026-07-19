'use client';

import { Typography } from '@/components/design-system';
import { PageShell } from '@/components/layout';

interface ErrorFallbackProps {
  title: string;
  description: string;
  onRetry?: () => void;
}

export function ErrorFallback({
  title,
  description,
  onRetry,
}: ErrorFallbackProps) {
  return (
    <PageShell as="main" id="main-content">
      <div className="text-measure space-y-4" role="alert">
        <div className="space-y-2">
          <Typography as="h1" variant="pageTitle">
            {title}
          </Typography>
          <Typography className="text-muted-foreground" variant="body">
            {description}
          </Typography>
        </div>
        {onRetry ? (
          <button
            className="type-button bg-primary text-primary-foreground focus-visible:ring-ring min-touch-target radius-interactive px-4 py-3 focus-visible:ring-2 focus-visible:outline-none"
            type="button"
            onClick={onRetry}
          >
            Try again
          </button>
        ) : null}
      </div>
    </PageShell>
  );
}
