import type { ReactNode } from 'react';

import {
  AppNavigation,
  AppShell,
  BrandMark,
  MobileNavigation,
  Sidebar,
} from '@/components/layout';
import { AppLink } from '@/components/navigation';
import { AuthProvider, UserMenu } from '@/features/auth';
import { routes } from '@/config/routes';
import { requireUser } from '@/services/auth';

interface ProtectedLayoutProps {
  children: ReactNode;
}

export default async function ProtectedLayout({
  children,
}: ProtectedLayoutProps) {
  const user = await requireUser();
  const pendingReviewCount = 3;

  return (
    <AuthProvider initialUser={user}>
      <AppShell
        mobileNavigation={
          <MobileNavigation
            brand={<BrandMark />}
            footer={<UserMenu name={user.name} />}
            utility={
              <AppLink
                aria-label={`${pendingReviewCount} items to review`}
                className="type-body-small text-muted-foreground gap-2"
                href={routes.approvals.path}
              >
                <span
                  aria-hidden="true"
                  className="bg-status-warning radius-pill size-2"
                />
                {pendingReviewCount} to review
              </AppLink>
            }
          >
            <AppNavigation reviewCount={pendingReviewCount} />
          </MobileNavigation>
        }
        sidebar={
          <Sidebar
            footer={<UserMenu name={user.name} />}
            header={<BrandMark />}
          >
            <AppNavigation reviewCount={pendingReviewCount} />
          </Sidebar>
        }
      >
        {children}
      </AppShell>
    </AuthProvider>
  );
}
