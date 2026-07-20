import type { ReactNode } from 'react';

import {
  AppShell,
  BrandMark,
  MobileNavigation,
  Sidebar,
} from '@/components/layout';
import {
  ApprovalAwareNavigation,
  ReviewQueueSummary,
} from '@/features/approvals';
import { ProtectedRoute, UserMenu } from '@/features/auth';
import { mockOrionStore } from '@/services/mock-orion-store';

interface ProtectedLayoutProps {
  children: ReactNode;
}

export default function ProtectedLayout({ children }: ProtectedLayoutProps) {
  const pendingReviewCount = mockOrionStore.listPendingApprovals().length;

  return (
    <ProtectedRoute>
      <AppShell
        mobileNavigation={
          <MobileNavigation
            brand={<BrandMark />}
            footer={<UserMenu />}
            utility={<ReviewQueueSummary initialCount={pendingReviewCount} />}
          >
            <ApprovalAwareNavigation initialCount={pendingReviewCount} />
          </MobileNavigation>
        }
        sidebar={
          <Sidebar footer={<UserMenu />} header={<BrandMark />}>
            <ApprovalAwareNavigation initialCount={pendingReviewCount} />
          </Sidebar>
        }
      >
        {children}
      </AppShell>
    </ProtectedRoute>
  );
}
