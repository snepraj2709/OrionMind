'use client';

import { AppButton } from '@/components/design-system';
import { PageErrorState } from '@/components/feedback';
import { PublicShell } from '@/components/layout';

interface AuthenticationErrorProps {
  reset: () => void;
}

export default function AuthenticationError({
  reset,
}: AuthenticationErrorProps) {
  return (
    <PublicShell>
      <PageErrorState
        action={<AppButton onClick={reset}>Try again</AppButton>}
        description="Orion could not load authentication."
      />
    </PublicShell>
  );
}
