'use client';

import { AppButton } from '@/components/design-system';
import { PageErrorState } from '@/components/feedback';
import { PageShell } from '@/components/layout';

interface ProtectedRouteErrorProps {
  reset: () => void;
}

export default function ProtectedRouteError({
  reset,
}: ProtectedRouteErrorProps) {
  return (
    <PageShell>
      <PageErrorState
        action={<AppButton onClick={reset}>Try again</AppButton>}
        description="Orion could not load this page."
      />
    </PageShell>
  );
}
