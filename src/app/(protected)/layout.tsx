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
import { AuthProvider, UserMenu } from '@/features/auth';
import { requireUser } from '@/services/auth';
import { mockOrionStore } from '@/services/mock-orion-store';

interface ProtectedLayoutProps {
  children: ReactNode;
}

export default async function ProtectedLayout({
  children,
}: ProtectedLayoutProps) {
  const user = await requireUser();
  const pendingReviewCount = mockOrionStore.listPendingApprovals().length;

  return (
    <AuthProvider initialUser={user}>
      <AppShell
        mobileNavigation={
          <MobileNavigation
            brand={<BrandMark />}
            footer={<UserMenu name={user.name} />}
            utility={<ReviewQueueSummary initialCount={pendingReviewCount} />}
          >
            <ApprovalAwareNavigation initialCount={pendingReviewCount} />
          </MobileNavigation>
        }
        sidebar={
          <Sidebar
            footer={<UserMenu name={user.name} />}
            header={<BrandMark />}
          >
            <ApprovalAwareNavigation initialCount={pendingReviewCount} />
          </Sidebar>
        }
      >
        {children}
      </AppShell>
    </AuthProvider>
  );
}
