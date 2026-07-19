'use client';

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
    <main className="page-shell" id="main-content">
      <div className="max-w-text space-y-4" role="alert">
        <div className="space-y-2">
          <h1 className="text-page-title">{title}</h1>
          <p className="text-muted-foreground">{description}</p>
        </div>
        {onRetry ? (
          <button
            className="text-button bg-primary text-primary-foreground focus-visible:ring-ring min-h-11 rounded-md px-4 py-2.5 font-semibold focus-visible:ring-2 focus-visible:outline-none"
            type="button"
            onClick={onRetry}
          >
            Try again
          </button>
        ) : null}
      </div>
    </main>
  );
}
