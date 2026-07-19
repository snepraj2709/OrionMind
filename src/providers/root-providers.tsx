'use client';

import type { ReactNode } from 'react';
import { Toaster } from 'sonner';

import { QueryProvider } from './query-provider';

interface RootProvidersProps {
  children: ReactNode;
}

export function RootProviders({ children }: RootProvidersProps) {
  return (
    <QueryProvider>
      {children}
      <Toaster closeButton position="bottom-right" theme="light" />
    </QueryProvider>
  );
}
