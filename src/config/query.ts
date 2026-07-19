import type { DefaultOptions } from '@tanstack/react-query';

export const queryDefaultOptions = {
  queries: {
    refetchOnWindowFocus: false,
    retry: 1,
    staleTime: 30_000,
  },
  mutations: {
    retry: 0,
  },
} satisfies DefaultOptions;
