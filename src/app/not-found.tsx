'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { Typography } from '@/components/design-system';
import { PageLoader } from '@/components/feedback';
import { PageShell } from '@/components/layout';
import { routes } from '@/config/routes';
import { useAuth } from '@/features/auth';

export default function NotFound() {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === 'anonymous' || status === 'unconfigured') {
      router.replace(routes.home.path);
    }
  }, [router, status]);

  if (status !== 'authenticated') {
    return <PageLoader label="Returning home" />;
  }

  return (
    <PageShell as="main" id="main-content">
      <div className="text-measure space-y-2">
        <Typography as="h1" variant="pageTitle">
          Page not found
        </Typography>
        <Typography className="text-muted-foreground" variant="body">
          The requested Orion page does not exist.
        </Typography>
      </div>
    </PageShell>
  );
}
