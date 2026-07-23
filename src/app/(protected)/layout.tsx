import type { ReactNode } from 'react';

import {
  AppShell,
  BrandMark,
  MobileNavigation,
  Sidebar,
} from '@/components/layout';
import { ReviewAwareNavigation, ReviewQueueSummary } from '@/features/review';
import { ProtectedRoute, UserMenu } from '@/features/auth';

interface ProtectedLayoutProps {
  children: ReactNode;
}

export default function ProtectedLayout({ children }: ProtectedLayoutProps) {
  return (
    <ProtectedRoute>
      <AppShell
        mobileNavigation={
          <MobileNavigation
            brand={<BrandMark />}
            footer={<UserMenu />}
            utility={<ReviewQueueSummary />}
          >
            <ReviewAwareNavigation />
          </MobileNavigation>
        }
        sidebar={
          <Sidebar footer={<UserMenu />} header={<BrandMark />}>
            <ReviewAwareNavigation />
          </Sidebar>
        }
      >
        {children}
      </AppShell>
    </ProtectedRoute>
  );
}
