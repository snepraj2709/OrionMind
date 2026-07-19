'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { queryDefaultOptions } from '@/config/query';

interface QueryProviderProps {
  children: ReactNode;
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: queryDefaultOptions,
  });
}

export function QueryProvider({ children }: QueryProviderProps) {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
