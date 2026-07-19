import type { ReactNode } from 'react';

import { Typography } from '@/components/design-system';
import {
  AppNavigation,
  AppShell,
  BrandMark,
  MobileNavigation,
  Sidebar,
} from '@/components/layout';
import { AuthProvider, SignOutButton } from '@/features/auth';
import { requireUser } from '@/services/auth';

interface ProtectedLayoutProps {
  children: ReactNode;
}

export default async function ProtectedLayout({
  children,
}: ProtectedLayoutProps) {
  const user = await requireUser();

  return (
    <AuthProvider initialUser={user}>
      <AppShell
        mobileNavigation={
          <MobileNavigation brand={<BrandMark />}>
            <AppNavigation />
          </MobileNavigation>
        }
        sidebar={
          <Sidebar
            footer={
              <div className="space-y-3">
                <div className="min-w-0 px-3">
                  <Typography className="truncate" variant="metadata">
                    {user.name}
                  </Typography>
                  <Typography
                    className="text-muted-foreground truncate"
                    variant="bodySmall"
                  >
                    {user.email}
                  </Typography>
                </div>
                <SignOutButton />
              </div>
            }
            header={<BrandMark />}
          >
            <AppNavigation />
          </Sidebar>
        }
      >
        {children}
      </AppShell>
    </AuthProvider>
  );
}
